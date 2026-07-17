from backend.app.config import Settings
from backend.app.db import connect
import json


class ReviewBatchRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(self, *, batch_id: str, file_id: int, version_id: int,
               task_id: str | None = None, workflow_id: str | None = None,
               source_review_batch_id: str | None = None) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """INSERT OR IGNORE INTO review_batch(
                       id,file_id,version_id,task_id,workflow_id,status,execution_status,source_review_batch_id
                   ) VALUES(?,?,?,?,?,'in_review','blocked',?)""",
                (batch_id, file_id, version_id, task_id, workflow_id, source_review_batch_id),
            )

    def mark_superseded(self, batch_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute("UPDATE review_batch SET batch_kind='superseded',updated_time=CURRENT_TIMESTAMP WHERE id=?", (batch_id,))

    def attach_task(self, batch_id: str, *, task_id: str, workflow_id: str | None) -> None:
        """Attach a regenerated/current batch to its workflow and retire older task batches."""
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE review_batch SET task_id=?,workflow_id=?,batch_kind='current',
                   updated_time=CURRENT_TIMESTAMP WHERE id=?""",
                (task_id, workflow_id, batch_id),
            )
            connection.execute(
                """UPDATE review_batch SET batch_kind='superseded',updated_time=CURRENT_TIMESTAMP
                   WHERE task_id=? AND id<>?""",
                (task_id, batch_id),
            )

    def get(self, batch_id: str) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(self._select() + " WHERE batch.id = ?", (batch_id,)).fetchone()
        return self._with_capabilities(dict(row)) if row else None

    def get_for_task(self, task_id: str) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                self._select() + " WHERE batch.task_id = ? ORDER BY batch.created_time DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        return self._with_capabilities(dict(row)) if row else None

    def list(self, *, status: str | None = None, file_id: int | None = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("batch.status = ?")
            params.append(status)
        if file_id is not None:
            clauses.append("batch.file_id = ?")
            params.append(file_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.settings) as connection:
            rows = connection.execute(self._select() + where + " ORDER BY batch.created_time DESC", params).fetchall()
        return [self._with_capabilities(dict(row)) for row in rows]

    def refresh_status(self, batch_id: str) -> dict:
        with connect(self.settings) as connection:
            counts = connection.execute(
                """SELECT COUNT(*) total,
                          SUM(status IN ('pending','edited')) open_count,
                          SUM(status='approved') approved_count,
                          SUM(status='rejected') rejected_count,
                          SUM(status='deferred') deferred_count,
                          SUM(status='executed') executed_count
                   FROM adjustment_suggestion WHERE review_batch_id=?""", (batch_id,)
            ).fetchone()
            open_count = int(counts["open_count"] or 0)
            approved_count = int(counts["approved_count"] or 0)
            existing = connection.execute(
                "SELECT preview_hash,execution_status,status FROM review_batch WHERE id=?", (batch_id,)
            ).fetchone()
            executed = bool(existing and existing["status"] == "executed")
            preview_ready = bool(existing and existing["preview_hash"] and existing["execution_status"] == "ready")
            if executed:
                status, execution, workflow_state = "executed", "executed", "executed"
            elif open_count:
                status = "in_review"
                execution = "stale" if existing and existing["preview_hash"] else "blocked"
                workflow_state = "reviewing"
            elif preview_ready:
                status, execution, workflow_state = "preview_ready", "ready", "preview_passed"
            else:
                status = "reviewed"
                execution = "stale" if existing and existing["preview_hash"] else "missing"
                workflow_state = "review_completed"
            connection.execute(
                """UPDATE review_batch SET status=?, execution_status=?, updated_time=CURRENT_TIMESTAMP,
                       workflow_state=?, completed_time=CASE WHEN ?=0 THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?""",
                (status, execution, workflow_state, open_count, batch_id),
            )
        return self.get(batch_id) or {"id": batch_id, "status": status, "execution_status": execution}

    def mark_executed(self, batch_id: str, new_version_id: int) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE review_batch SET status='executed',execution_status='executed',workflow_state='executed',
                       new_version_id=?,updated_time=CURRENT_TIMESTAMP,completed_time=CURRENT_TIMESTAMP WHERE id=?""",
                (new_version_id, batch_id),
            )

    def save_preview(self, batch_id: str, *, review_hash: str, payload: dict,
                     base_version_id: int, base_generation: int, valid: bool) -> dict:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE review_batch SET preview_hash=?,preview_payload=?,preview_base_version_id=?,
                   preview_base_generation=?,preview_created_time=CURRENT_TIMESTAMP,
                   workflow_state=?,execution_status=?,updated_time=CURRENT_TIMESTAMP WHERE id=?""",
                (review_hash, json.dumps(payload, ensure_ascii=False), base_version_id, base_generation,
                 "preview_passed" if valid else "review_completed",
                 "ready" if valid else "blocked", batch_id),
            )
            connection.execute(
                "UPDATE review_batch SET status=? WHERE id=?",
                ("preview_ready" if valid else "reviewed", batch_id),
            )
        return self.get(batch_id) or {}

    def invalidate_preview(self, batch_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE review_batch SET
                   workflow_state=CASE WHEN status IN ('reviewed','preview_ready') THEN 'review_completed' ELSE 'reviewing' END,
                   status=CASE WHEN status='preview_ready' THEN 'reviewed' ELSE status END,
                   execution_status=CASE WHEN preview_hash IS NOT NULL THEN 'stale' ELSE 'blocked' END,
                   updated_time=CURRENT_TIMESTAMP WHERE id=?""", (batch_id,),
            )

    def mark_executing(self, batch_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE review_batch SET status='executing',execution_status='executing',updated_time=CURRENT_TIMESTAMP WHERE id=?",
                (batch_id,),
            )

    def mark_failed(self, batch_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE review_batch SET status='failed',execution_status='failed',updated_time=CURRENT_TIMESTAMP WHERE id=?",
                (batch_id,),
            )

    @staticmethod
    def _with_capabilities(batch: dict) -> dict:
        pending = int(batch.get("pending_count") or 0)
        approved = int(batch.get("approved_count") or 0)
        status = str(batch.get("status") or "in_review")
        preview_status = str(batch.get("execution_status") or "blocked")
        can_generate = pending == 0 and approved > 0 and status not in {"executing", "executed", "failed"}
        can_execute = status == "preview_ready" and preview_status == "ready" and bool(batch.get("preview_hash"))
        if status == "executed":
            blocked_reason = "该审核批次已执行完成"
        elif status == "executing":
            blocked_reason = "正在执行修改"
        elif status == "failed":
            blocked_reason = "执行失败，请检查执行记录"
        elif pending:
            blocked_reason = f"还有 {pending} 条建议尚未审核"
        elif approved == 0:
            blocked_reason = "当前没有可执行修改"
        elif preview_status == "stale":
            blocked_reason = "旧执行预览已失效，请重新生成预览"
        elif not can_execute:
            blocked_reason = "请先生成并通过执行预览"
        else:
            blocked_reason = None
        return {**batch, "review_status": status, "preview_status": preview_status,
                "can_generate_preview": can_generate, "can_execute": can_execute,
                "blocked_reason": blocked_reason}

    @staticmethod
    def _select() -> str:
        return """SELECT batch.*, file.file_name, version.version_no,
                  (SELECT COUNT(*) FROM adjustment_suggestion s WHERE s.review_batch_id=batch.id) suggestion_count,
                  (SELECT COUNT(*) FROM adjustment_suggestion s WHERE s.review_batch_id=batch.id AND s.status IN ('pending','edited')) pending_count,
                  (SELECT COUNT(*) FROM adjustment_suggestion s WHERE s.review_batch_id=batch.id AND s.status='approved') approved_count,
                  (SELECT COUNT(*) FROM adjustment_suggestion s WHERE s.review_batch_id=batch.id AND s.status='rejected') rejected_count,
                  (SELECT COUNT(*) FROM adjustment_suggestion s WHERE s.review_batch_id=batch.id AND s.status='deferred') deferred_count,
                  (SELECT COUNT(*) FROM adjustment_suggestion s WHERE s.review_batch_id=batch.id AND s.status='executed') executed_count
                  FROM review_batch batch
                  JOIN uploaded_file file ON file.id=batch.file_id
                  JOIN taxonomy_version version ON version.id=batch.version_id"""
