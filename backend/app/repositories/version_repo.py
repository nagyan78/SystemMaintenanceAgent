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

    def list_versions(self, file_id: int | None = None) -> list[dict]:
        clauses = []
        params: list[object] = []
        if file_id is not None:
            clauses.append("version.file_id = ?")
            params.append(file_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT version.id, version.file_id, version.version_no,
                       version.description, version.quality_score,
                       version.snapshot_path, version.created_time,
                       (SELECT COUNT(*) FROM category_node node WHERE node.version_id = version.id) AS node_count
                FROM taxonomy_version version
                {where}
                ORDER BY version.id
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_for_file(self, file_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, created_time
                FROM taxonomy_version
                WHERE file_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (file_id,),
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

    def update_quality_score(self, version_id: int, quality_score: float) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE taxonomy_version SET quality_score = ? WHERE id = ?",
                (quality_score, version_id),
            )
