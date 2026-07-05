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
    ) -> str:
        task_id = f"workflow_{uuid4().hex[:12]}"
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO task_record (
                    id, file_id, task_type, status, current_step, progress,
                    workflow_id, thread_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, task_type, status, current_step, progress,
                       error_message, workflow_id, thread_id, version_id,
                       interrupt_payload, result_payload, created_time, updated_time
                FROM task_record
                WHERE id = ?
                """,
                (task_id,),
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
        payload = _loads(current.get("result_payload"))
        if result_payload:
            payload.update(_json_ready(result_payload))
        updates = {
            "status": status if status is not None else current["status"],
            "current_step": current_step
            if current_step is not None
            else current["current_step"],
            "progress": progress if progress is not None else current["progress"],
            "version_id": version_id
            if version_id is not None
            else current.get("version_id"),
            "error_message": error_message,
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
                    updated_time = ?
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
                    task_id,
                ),
            )

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
