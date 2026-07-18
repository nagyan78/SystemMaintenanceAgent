import json
from typing import Any

from backend.app.config import Settings
from backend.app.db import connect


class OperationLogRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_log(
        self,
        *,
        version_id: int | None,
        workflow_id: str | None = None,
        analysis_run_id: str | None = None,
        operator: str,
        operation_type: str,
        operation_detail: dict[str, Any],
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO operation_log (
                    version_id, workflow_id, analysis_run_id, operator,
                    operation_type, operation_detail
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    workflow_id,
                    analysis_run_id,
                    operator,
                    operation_type,
                    json.dumps(operation_detail, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def list_for_run(self, analysis_run_id: str) -> list[dict[str, Any]]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, version_id, workflow_id, analysis_run_id, operator,
                       operation_type, operation_detail, created_time
                FROM operation_log
                WHERE analysis_run_id = ?
                ORDER BY id
                """,
                (analysis_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]
