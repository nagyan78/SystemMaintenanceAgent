from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.db import connect, sqlite_path_from_url


BUSINESS_TABLES = (
    "evaluation_baseline", "agent_evaluation", "agent_event", "run_issue", "agent_work_item", "agent_run",
    "tool_cache", "agent_memory", "diagnosis_triage", "category_reference", "workflow_event",
    "version_execution_record", "report_artifact", "operation_log", "adjustment_suggestion",
    "review_batch", "diagnosis_issue", "category_node", "taxonomy_version", "task_record", "uploaded_file",
)


class MaintenanceCleanupService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def preview(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        scope = self._resolve_scope(request_payload)
        result = self._calculate(scope)
        preview_id = f"cleanup_{uuid4().hex[:16]}"
        result["filesystem_paths"] = self._collect_paths_for_resolved(result["resolved_scope"])
        result["database_backup_path"] = str(self._planned_backup_path(preview_id))
        scope_hash = self._hash({"scope": scope, "result": result})
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        with connect(self.settings) as connection:
            connection.execute(
                """INSERT INTO maintenance_cleanup_preview(id,request_payload,resolved_scope,result_payload,scope_hash,expires_time)
                   VALUES(?,?,?,?,?,?)""",
                (preview_id, json.dumps(request_payload, ensure_ascii=False), json.dumps(scope, ensure_ascii=False),
                 json.dumps(result, ensure_ascii=False), scope_hash, expires.isoformat()),
            )
        return {"cleanup_preview_id": preview_id, "expires_time": expires.isoformat(), **result}

    def execute(self, preview_id: str, confirmation: str) -> dict[str, Any]:
        with connect(self.settings) as connection:
            row = connection.execute("SELECT * FROM maintenance_cleanup_preview WHERE id=?", (preview_id,)).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("清理预览不存在或已使用。")
        if datetime.fromisoformat(row["expires_time"]) <= datetime.now(timezone.utc):
            raise ValueError("清理预览已过期，请重新预览。")
        request_payload = json.loads(row["request_payload"])
        expected = "DELETE ALL" if request_payload.get("all_business_data") else "CONFIRM"
        if confirmation != expected:
            raise ValueError(f"确认文字不正确，请输入 {expected}。")
        scope = self._resolve_scope(request_payload)
        current = self._calculate(scope)
        current["filesystem_paths"] = self._collect_paths_for_resolved(current["resolved_scope"])
        current["database_backup_path"] = str(self._planned_backup_path(preview_id))
        if self._hash({"scope": scope, "result": current}) != row["scope_hash"]:
            raise ValueError("清理范围已变化，旧预览失效，请重新预览。")
        if current["blocking_reasons"]:
            raise ValueError("；".join(current["blocking_reasons"]))
        backup_path = self._backup_database(self._planned_backup_path(preview_id))
        paths = current["filesystem_paths"]
        version_ids = current["resolved_scope"]["version_ids"]
        deleted = self._delete_database(scope)
        file_pending = self._delete_files(paths)
        vector_pending = self._delete_vectors(version_ids)
        pending = [*file_pending, *vector_pending]
        with connect(self.settings) as connection:
            connection.execute("UPDATE maintenance_cleanup_preview SET status='executed' WHERE id=?", (preview_id,))
            connection.execute(
                """INSERT INTO maintenance_cleanup_audit(
                       cleanup_preview_id,request_payload,resolved_scope,deleted_payload,
                       backup_path,pending_payload,status
                   ) VALUES(?,?,?,?,?,?,'completed')""",
                (preview_id, json.dumps(request_payload, ensure_ascii=False),
                 json.dumps(current["resolved_scope"], ensure_ascii=False),
                 json.dumps(deleted, ensure_ascii=False), backup_path,
                 json.dumps(pending, ensure_ascii=False)),
            )
        return {"cleanup_preview_id": preview_id, "deleted": deleted,
                "filesystem_deleted": len(paths) - len(file_pending), "pending_file_cleanup": pending,
                "database_backup_path": backup_path}

    def _resolve_scope(self, payload: dict[str, Any]) -> dict[str, Any]:
        with connect(self.settings) as connection:
            if payload.get("all_business_data"):
                file_ids = [int(row[0]) for row in connection.execute("SELECT id FROM uploaded_file")]
                workflow_ids = [str(row[0]) for row in connection.execute("SELECT id FROM task_record")]
                review_ids = [str(row[0]) for row in connection.execute("SELECT id FROM review_batch")]
            else:
                file_ids = sorted({int(item) for item in payload.get("file_ids", [])})
                workflow_ids = {str(item) for item in payload.get("workflow_ids", [])}
                if payload.get("failed_workflows"):
                    workflow_ids |= {str(row[0]) for row in connection.execute("SELECT id FROM task_record WHERE status='failed'")}
                if payload.get("incomplete_workflows"):
                    workflow_ids |= {str(row[0]) for row in connection.execute("SELECT id FROM task_record WHERE status IN ('pending','waiting') OR progress=0")}
                workflow_ids = sorted(workflow_ids)
                review_ids = sorted({str(item) for item in payload.get("review_batch_ids", [])})
        return {"all_business_data": bool(payload.get("all_business_data")),
                "force_cancel_running": bool(payload.get("force_cancel_running")), "file_ids": file_ids,
                "workflow_ids": workflow_ids, "review_batch_ids": review_ids}

    def _calculate(self, scope: dict[str, Any]) -> dict[str, Any]:
        file_ids, workflow_ids, review_ids = scope["file_ids"], scope["workflow_ids"], scope["review_batch_ids"]
        with connect(self.settings) as c:
            if file_ids:
                q = self._marks(file_ids)
                workflow_ids = sorted(set(workflow_ids) | {str(r[0]) for r in c.execute(f"SELECT id FROM task_record WHERE file_id IN ({q})", file_ids)})
                review_ids = sorted(set(review_ids) | {str(r[0]) for r in c.execute(f"SELECT id FROM review_batch WHERE file_id IN ({q})", file_ids)})
            if workflow_ids:
                workflow_run_ids_for_scope = [str(r[0]) for r in c.execute(f"SELECT workflow_id FROM task_record WHERE id IN ({self._marks(workflow_ids)}) AND workflow_id IS NOT NULL", workflow_ids)]
                related = {str(r[0]) for r in c.execute(f"SELECT id FROM review_batch WHERE task_id IN ({self._marks(workflow_ids)})", workflow_ids)}
                if workflow_run_ids_for_scope:
                    related |= {str(r[0]) for r in c.execute(f"SELECT id FROM review_batch WHERE workflow_id IN ({self._marks(workflow_run_ids_for_scope)})", workflow_run_ids_for_scope)}
                review_ids = sorted(set(review_ids) | related)
            version_ids = [int(r[0]) for r in c.execute(f"SELECT id FROM taxonomy_version WHERE file_id IN ({self._marks(file_ids)})", file_ids)] if file_ids else []
            if workflow_ids and not file_ids:
                version_ids = sorted({int(r[0]) for r in c.execute(f"SELECT version_id FROM task_record WHERE id IN ({self._marks(workflow_ids)}) AND version_id IS NOT NULL", workflow_ids)})
            workflow_run_ids = [str(r[0]) for r in c.execute(f"SELECT workflow_id FROM task_record WHERE id IN ({self._marks(workflow_ids)}) AND workflow_id IS NOT NULL", workflow_ids)] if workflow_ids else []
            suggestion_ids = self._count(c, "adjustment_suggestion", "review_batch_id", review_ids)
            issue_count = self._count(c, "diagnosis_issue", "version_id", version_ids)
            task_count = self._count(c, "task_record", "id", workflow_ids)
            batch_count = self._count(c, "review_batch", "id", review_ids)
            decisions = self._count(c, "adjustment_suggestion", "review_batch_id", review_ids, "status NOT IN ('pending','edited')")
            previews = self._count(c, "review_batch", "id", review_ids, "preview_hash IS NOT NULL")
            executions = self._count(c, "version_execution_record", "review_batch_id", review_ids)
            nodes = self._count(c, "category_node", "version_id", version_ids)
            reports = self._count(c, "report_artifact", "version_id", version_ids)
            vectors = self._count(c, "taxonomy_version", "id", version_ids, "vector_index_generation>0")
            blocking: list[str] = []
            if workflow_ids:
                rows = c.execute(f"SELECT id FROM task_record WHERE id IN ({self._marks(workflow_ids)}) AND status IN ('running','waiting_review')", workflow_ids).fetchall()
                if rows and not scope.get("force_cancel_running"):
                    blocking.append(f"运行中的任务必须先取消：{', '.join(str(r[0]) for r in rows)}")
            direct_review_ids = [item for item in review_ids if item not in self._review_ids_for_files(c, file_ids)]
            if direct_review_ids:
                rows = c.execute(f"SELECT id FROM review_batch WHERE id IN ({self._marks(direct_review_ids)}) AND execution_status='executed'", direct_review_ids).fetchall()
                if rows: blocking.append("已执行审核批次不能单独删除，必须删除整个文件及派生数据。")
            if version_ids and not file_ids:
                shared = c.execute(
                    f"SELECT COUNT(*) FROM task_record WHERE version_id IN ({self._marks(version_ids)}) AND id NOT IN ({self._marks(workflow_ids)})",
                    [*version_ids, *workflow_ids],
                ).fetchone()[0] if workflow_ids else 0
                external_batches = c.execute(
                    f"SELECT COUNT(*) FROM review_batch WHERE version_id IN ({self._marks(version_ids)}) AND id NOT IN ({self._marks(review_ids)})",
                    [*version_ids, *review_ids],
                ).fetchone()[0] if review_ids else self._count(c, "review_batch", "version_id", version_ids)
                descendants = c.execute(
                    f"SELECT COUNT(*) FROM taxonomy_version WHERE parent_version_id IN ({self._marks(version_ids)}) AND id NOT IN ({self._marks(version_ids)})",
                    [*version_ids, *version_ids],
                ).fetchone()[0]
                if shared or external_batches or descendants:
                    blocking.append("任务版本仍被其他任务或审核批次引用，请改为删除整个文件及全部派生数据。")
                released = self._count(c, "taxonomy_version", "id", version_ids, "lifecycle_status='released'")
                if released: blocking.append("released版本不能单独删除。")
        return {"task_count": task_count, "diagnosis_issue_count": issue_count,
                "suggestion_count": suggestion_ids, "review_batch_count": batch_count,
                "review_decision_count": decisions, "execution_preview_count": previews,
                "execution_record_count": executions, "version_count": len(version_ids),
                "node_snapshot_count": nodes, "report_count": reports,
                "uploaded_file_count": len(file_ids), "vector_index_count": vectors,
                "blocking_reasons": blocking,
                "resolved_scope": {**scope, "workflow_ids": workflow_ids, "workflow_run_ids": workflow_run_ids,
                                   "review_batch_ids": review_ids, "version_ids": version_ids}}

    def _delete_database(self, scope: dict[str, Any]) -> dict[str, int]:
        calculated = self._calculate(scope)
        resolved = calculated["resolved_scope"]
        files, workflows, reviews, versions = (resolved[key] for key in ("file_ids", "workflow_ids", "review_batch_ids", "version_ids"))
        workflow_runs = resolved["workflow_run_ids"]
        deleted: dict[str, int] = {}
        with connect(self.settings) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                if scope.get("force_cancel_running") and workflows:
                    c.execute(
                        f"UPDATE task_record SET status='cancelled',current_step='cancelled',end_time=? "
                        f"WHERE id IN ({self._marks(workflows)}) AND status IN ('pending','running','waiting_review','waiting')",
                        [datetime.now(timezone.utc).isoformat(), *workflows],
                    )
                    if workflow_runs:
                        c.execute(
                            f"UPDATE agent_run SET status='cancelled',updated_time=? WHERE workflow_id IN ({self._marks(workflow_runs)}) "
                            "AND status NOT IN ('completed','failed','cancelled')",
                            [datetime.now(timezone.utc).isoformat(), *workflow_runs],
                        )
                if scope["all_business_data"]:
                    for table in BUSINESS_TABLES:
                        deleted[table] = c.execute(f"DELETE FROM {table}").rowcount
                else:
                    issue_ids = [int(r[0]) for r in c.execute(f"SELECT issue_id FROM adjustment_suggestion WHERE review_batch_id IN ({self._marks(reviews)})", reviews)] if reviews else []
                    run_ids = [str(r[0]) for r in c.execute(f"SELECT id FROM agent_run WHERE workflow_id IN ({self._marks(workflow_runs)})", workflow_runs)] if workflow_runs else []
                    for table, column, values in (
                        ("version_execution_record", "review_batch_id", reviews), ("adjustment_suggestion", "review_batch_id", reviews),
                        ("review_batch", "id", reviews), ("workflow_event", "task_id", workflows),
                        ("agent_event", "workflow_id", workflow_runs), ("run_issue", "run_id", run_ids),
                        ("agent_work_item", "run_id", run_ids),
                        ("agent_run", "workflow_id", workflow_runs), ("agent_memory", "source_workflow_id", workflow_runs),
                        ("diagnosis_triage", "workflow_id", workflow_runs), ("tool_cache", "workflow_id", workflow_runs),
                        ("task_record", "id", workflows),
                        ("report_artifact", "version_id", versions), ("category_reference", "version_id", versions),
                        ("operation_log", "version_id", versions), ("diagnosis_issue", "version_id", versions),
                        ("category_node", "version_id", versions), ("taxonomy_version", "id", versions),
                        ("uploaded_file", "id", files),
                    ):
                        if values:
                            deleted[table] = deleted.get(table, 0) + c.execute(f"DELETE FROM {table} WHERE {column} IN ({self._marks(values)})", values).rowcount
                    if issue_ids and not versions:
                        deleted["diagnosis_issue"] = c.execute(
                            f"DELETE FROM diagnosis_issue WHERE id IN ({self._marks(issue_ids)}) AND NOT EXISTS (SELECT 1 FROM adjustment_suggestion s WHERE s.issue_id=diagnosis_issue.id)", issue_ids).rowcount
                c.commit()
            except Exception:
                c.rollback()
                raise
        return deleted

    def _collect_paths(self, scope: dict[str, Any]) -> list[str]:
        return self._collect_paths_for_resolved(self._calculate(scope)["resolved_scope"])

    def _collect_paths_for_resolved(self, calculated: dict[str, Any]) -> list[str]:
        paths: set[str] = set()
        with connect(self.settings) as c:
            for table, column, values, fields in (
                ("uploaded_file", "id", calculated["file_ids"], ("file_path",)),
                ("taxonomy_version", "id", calculated["version_ids"], ("snapshot_path", "export_path")),
                ("report_artifact", "version_id", calculated["version_ids"], ("report_path",)),
            ):
                if not values: continue
                for row in c.execute(f"SELECT {','.join(fields)} FROM {table} WHERE {column} IN ({self._marks(values)})", values):
                    paths.update(str(value) for value in row if value)
        return sorted(paths)

    def _delete_files(self, paths: list[str]) -> list[str]:
        pending: list[str] = []
        for raw in paths:
            path = Path(raw)
            try:
                if path.exists() and path.is_file(): path.unlink()
            except OSError as exc:
                pending.append(raw)
                with connect(self.settings) as c:
                    c.execute("INSERT INTO pending_file_cleanup(path,reason) VALUES(?,?)", (raw, str(exc)))
        return pending

    def _delete_vectors(self, version_ids: list[int]) -> list[str]:
        if not version_ids:
            return []
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import FieldCondition, Filter, MatchAny
            client = QdrantClient(url=self.settings.qdrant_url, timeout=3)
            if client.collection_exists(self.settings.qdrant_collection):
                client.delete(collection_name=self.settings.qdrant_collection,
                              points_selector=Filter(must=[FieldCondition(key="version_id", match=MatchAny(any=version_ids))]))
            return []
        except Exception as exc:
            marker = f"qdrant://{self.settings.qdrant_collection}/versions/{','.join(map(str, version_ids))}"
            with connect(self.settings) as c:
                c.execute("INSERT INTO pending_file_cleanup(path,reason) VALUES(?,?)", (marker, str(exc)))
            return [marker]

    def _planned_backup_path(self, preview_id: str) -> Path:
        source = sqlite_path_from_url(self.settings.database_url)
        return source.parent / "backups" / f"app_before_{preview_id}.db"

    def _backup_database(self, target: Path) -> str:
        source = sqlite_path_from_url(self.settings.database_url)
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst: src.backup(dst)
        return str(target)

    @staticmethod
    def _marks(values: list[Any]) -> str: return ",".join("?" for _ in values) or "NULL"
    @classmethod
    def _count(cls, c, table: str, column: str, values: list[Any], extra: str = "") -> int:
        if not values: return 0
        where = f"{column} IN ({cls._marks(values)})" + (f" AND {extra}" if extra else "")
        return int(c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", values).fetchone()[0])
    @classmethod
    def _review_ids_for_files(cls, c, file_ids: list[int]) -> set[str]:
        if not file_ids: return set()
        return {str(r[0]) for r in c.execute(f"SELECT id FROM review_batch WHERE file_id IN ({cls._marks(file_ids)})", file_ids)}
    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
