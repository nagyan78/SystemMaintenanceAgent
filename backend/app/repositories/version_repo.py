from backend.app.config import Settings
from backend.app.db import connect


class VersionRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_version(
        self,
        *,
        file_id: int,
        version_no: str,
        description: str | None = None,
        quality_score: float | None = None,
        snapshot_path: str | None = None,
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_version (
                    file_id, version_no, description, quality_score, snapshot_path
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_id, version_no, description, quality_score, snapshot_path),
            )
            return int(cursor.lastrowid)

    def get_version(self, version_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, created_time
                FROM taxonomy_version
                WHERE id = ?
                """,
                (version_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_file_and_no(self, file_id: int, version_no: str) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, created_time
                FROM taxonomy_version
                WHERE file_id = ? AND version_no = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (file_id, version_no),
            ).fetchone()
        return dict(row) if row else None
