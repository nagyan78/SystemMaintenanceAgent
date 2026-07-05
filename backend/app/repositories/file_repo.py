from uuid import uuid4

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.services.excel_service import UploadedFileMetadata


class FileRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_uploaded_file(self, metadata: UploadedFileMetadata) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO uploaded_file (
                    file_name,
                    file_path,
                    file_size,
                    sheet_name,
                    row_count,
                    column_count,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.file_name,
                    str(metadata.file_path),
                    metadata.file_size,
                    metadata.sheet_name,
                    metadata.row_count,
                    metadata.column_count,
                    "uploaded",
                ),
            )
            return int(cursor.lastrowid)

    def list_files(self) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, file_name, file_path, file_size, sheet_name,
                       row_count, column_count, upload_time, status
                FROM uploaded_file
                ORDER BY id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_file(self, file_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_name, file_path, file_size, sheet_name,
                       row_count, column_count, upload_time, status
                FROM uploaded_file
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
        return dict(row) if row else None


class TaskRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_task(self, file_id: int, task_type: str) -> str:
        task_id = f"{task_type}_{uuid4().hex[:12]}"
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO task_record (
                    id,
                    file_id,
                    task_type,
                    status,
                    current_step,
                    progress
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, file_id, task_type, "pending", "uploaded", 0),
            )
        return task_id

