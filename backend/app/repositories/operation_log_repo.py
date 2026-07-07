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
        operator: str,
        operation_type: str,
        operation_detail: dict[str, Any],
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO operation_log (
                    version_id, operator, operation_type, operation_detail
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    version_id,
                    operator,
                    operation_type,
                    json.dumps(operation_detail, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)
