from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.repositories.task_repo import TaskRepository
from backend.app.services.excel_service import UploadedFileMetadata


class FileRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_uploaded_file(self, metadata: UploadedFileMetadata) -> int:
        upload_time = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
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
                    upload_time,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.file_name,
                    str(metadata.file_path),
                    metadata.file_size,
                    metadata.sheet_name,
                    metadata.row_count,
                    metadata.column_count,
                    upload_time,
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
