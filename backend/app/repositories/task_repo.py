import json
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.db import connect


class TaskRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_task(self, file_id: int, task_type: str) -> str:
        task_id = f"{task_type}_{uuid4().hex[:12]}"
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO task_record (
                    id, file_id, task_type, status, current_step, progress
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, file_id, task_type, "pending", "uploaded", 0),
            )
        return task_id

    def create_workflow_task(
        self,
        *,
        file_id: int,
        workflow_id: str,
        thread_id: str,
        enable_ai_analysis: bool = False,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> str:
        task_id = f"workflow_{uuid4().hex[:12]}"
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO task_record (
                    id, file_id, task_type, status, current_step, progress,
                    workflow_id, thread_id, enable_ai_analysis, model_provider, model_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    file_id,
                    "taxonomy_workflow",
                    "running",
                    "parse_excel",
                    0,
                    workflow_id,
                    thread_id,
                    int(enable_ai_analysis),
                    model_provider,
                    model_name,
                ),
            )
        return task_id

    def create_diagnosis_task(
        self,
        *,
        file_id: int,
        version_id: int,
        enable_ai_analysis: bool,
        model_provider: str | None,
        model_name: str | None,
    ) -> str:
        task_id = f"diagnosis_{uuid4().hex[:12]}"
        workflow_id = task_id
        thread_id = f"taxonomy_workflow:{workflow_id}"
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO task_record (
                    id, file_id, task_type, status, current_step, progress,
                    version_id, enable_ai_analysis, model_provider, model_name
                    , start_time, workflow_id, thread_id
                ) VALUES (?, ?, 'diagnosis', 'running', 'rule_detection', 10, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (task_id, file_id, version_id, int(enable_ai_analysis), model_provider, model_name,
                 workflow_id, thread_id),
            )
        return task_id

    def attach_primary_run(self, task_id: str, run_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE task_record SET primary_run_id=?,updated_time=CURRENT_TIMESTAMP WHERE id=?",
                (run_id, task_id),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, task_type, status, current_step, progress,
                       error_message, workflow_id, thread_id, version_id,
                       interrupt_payload, result_payload, enable_ai_analysis,
                       model_provider, model_name, created_time, updated_time
                       , start_time, end_time, primary_run_id
                FROM task_record
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, *, file_id: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        if file_id is not None:
            clauses.append("task.file_id = ?")
            params.append(file_id)
        if status:
            clauses.append("task.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""SELECT task.id,task.file_id,file.file_name,task.task_type,task.status,
                           task.current_step,task.progress,task.version_id,task.workflow_id,
                           task.result_payload,task.error_message,task.created_time,task.updated_time,
                            task.start_time,task.end_time,batch.id review_batch_id,
                            batch.status review_status,batch.execution_status,batch.new_version_id,
                            (SELECT COUNT(*) FROM diagnosis_issue issue WHERE issue.version_id=task.version_id) issue_count,
                            (SELECT COUNT(*) FROM adjustment_suggestion suggestion WHERE suggestion.review_batch_id=batch.id) suggestion_count,
                            (SELECT verification_status FROM taxonomy_version output_version WHERE output_version.id=batch.new_version_id) verification_status,
                            EXISTS(SELECT 1 FROM report_artifact report WHERE report.version_id=task.version_id AND report.report_type='draft') draft_report_available,
                            EXISTS(SELECT 1 FROM report_artifact report WHERE report.version_id=COALESCE(batch.new_version_id,task.version_id) AND report.report_type='final') final_report_available
                    FROM task_record task
                    LEFT JOIN uploaded_file file ON file.id=task.file_id
                    LEFT JOIN review_batch batch ON batch.task_id=task.id
                    {where} ORDER BY task.created_time DESC""", params
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_diagnosis_for_version(self, version_id: int) -> dict[str, Any] | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, status, current_step, progress, version_id,
                       error_message, result_payload, enable_ai_analysis, model_provider, model_name,
                       created_time, updated_time
                       , start_time, end_time, workflow_id, thread_id, primary_run_id
                FROM task_record
                WHERE task_type = 'diagnosis' AND version_id = ?
                ORDER BY created_time DESC, id DESC LIMIT 1
                """,
                (version_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_for_version(self, version_id: int) -> dict[str, Any] | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """SELECT id,file_id,task_type,status,current_step,progress,version_id,
                          error_message,result_payload,enable_ai_analysis,model_provider,model_name,
                          created_time,updated_time,start_time,end_time,workflow_id,thread_id,primary_run_id
                   FROM task_record WHERE version_id=?
                   ORDER BY created_time DESC,id DESC LIMIT 1""",
                (version_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_task(
        self,
        *,
        task_id: str,
        status: str | None = None,
        current_step: str | None = None,
        progress: int | None = None,
        version_id: int | None = None,
        error_message: str | None = None,
        result_payload: dict[str, Any] | None = None,
        interrupt_payload: dict[str, Any] | None = None,
    ) -> None:
        current = self.get_task(task_id)
        if current is None:
            return
        terminal_statuses = {"completed", "partial", "completed_degraded", "failed", "cancelled"}
        requested_status = status if status is not None else current["status"]
        if current["status"] in terminal_statuses and requested_status != current["status"]:
            # Terminal states may only be changed by creating/recovering a new run.
            requested_status = current["status"]
            current_step = current["current_step"]
            progress = current["progress"]
        payload = _loads(current.get("result_payload"))
        if result_payload:
            payload.update(_json_ready(result_payload))
        updates = {
            "status": requested_status,
            "current_step": current_step
            if current_step is not None
            else current["current_step"],
            "progress": progress if progress is not None else current["progress"],
            "version_id": version_id
            if version_id is not None
            else current.get("version_id"),
            "error_message": error_message if error_message is not None else current.get("error_message"),
            "result_payload": json.dumps(payload, ensure_ascii=False),
            "interrupt_payload": json.dumps(
                _json_ready(interrupt_payload), ensure_ascii=False
            )
            if interrupt_payload is not None
            else current.get("interrupt_payload"),
            "updated_time": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
                timespec="seconds"
            ),
        }
        with connect(self.settings) as connection:
            connection.execute(
                """
                UPDATE task_record
                SET status = ?,
                    current_step = ?,
                    progress = ?,
                    version_id = ?,
                    error_message = ?,
                    result_payload = ?,
                    interrupt_payload = ?,
                    updated_time = ?,
                    end_time = CASE WHEN ? IN ('completed', 'partial', 'completed_degraded', 'failed', 'cancelled') THEN COALESCE(end_time, ?) ELSE end_time END
                WHERE id = ?
                """,
                (
                    updates["status"],
                    updates["current_step"],
                    updates["progress"],
                    updates["version_id"],
                    updates["error_message"],
                    updates["result_payload"],
                    updates["interrupt_payload"],
                    updates["updated_time"],
                    updates["status"],
                    updates["updated_time"],
                    task_id,
                ),
            )

    def list_events(
        self,
        workflow_id: str,
        after_id: int | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return workflow_event rows for a workflow, newest last.

        Used by the SSE stream to fetch events that arrived after a cursor.
        """
        with connect(self.settings) as connection:
            if after_id is None:
                rows = connection.execute(
                    """
                    SELECT id, workflow_id, thread_id, task_id, node_name,
                           event_type, status, progress, message, payload,
                           created_time
                    FROM workflow_event
                    WHERE workflow_id = ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (workflow_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, workflow_id, thread_id, task_id, node_name,
                           event_type, status, progress, message, payload,
                           created_time
                    FROM workflow_event
                    WHERE workflow_id = ? AND id > ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (workflow_id, after_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def record_event(
        self,
        *,
        workflow_id: str,
        thread_id: str,
        task_id: str | None,
        node_name: str | None,
        event_type: str,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO workflow_event (
                    workflow_id, thread_id, task_id, node_name, event_type,
                    status, progress, message, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    thread_id,
                    task_id,
                    node_name,
                    event_type,
                    status,
                    progress,
                    message,
                    json.dumps(_json_ready(payload or {}), ensure_ascii=False),
                ),
            )


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump())
    if hasattr(value, "__fspath__"):
        return value.__fspath__()
    return value
