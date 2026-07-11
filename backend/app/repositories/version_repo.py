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
        parent_version_id: int | None = None,
        source_workflow_id: str | None = None,
        analysis_run_id: str | None = None,
        action_batch_id: str | None = None,
        vector_index_status: str = "unknown",
        vector_index_generation: int = 0,
        verification_status: str | None = None,
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_version (
                    file_id, version_no, description, quality_score, snapshot_path,
                    parent_version_id, source_workflow_id, analysis_run_id,
                    action_batch_id, vector_index_status,
                    vector_index_generation, verification_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    version_no,
                    description,
                    quality_score,
                    snapshot_path,
                    parent_version_id,
                    source_workflow_id,
                    analysis_run_id,
                    action_batch_id,
                    vector_index_status,
                    vector_index_generation,
                    verification_status,
                ),
            )
            return int(cursor.lastrowid)

    def create_next_version(
        self,
        *,
        file_id: int,
        description: str,
        parent_version_id: int,
        source_workflow_id: str | None,
        analysis_run_id: str | None,
        action_batch_id: str,
        quality_score: float | None = None,
    ) -> tuple[int, str, bool]:
        with connect(self.settings) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id, version_no FROM taxonomy_version WHERE action_batch_id = ?",
                (action_batch_id,),
            ).fetchone()
            if existing:
                return int(existing["id"]), str(existing["version_no"]), False
            rows = connection.execute(
                "SELECT version_no FROM taxonomy_version WHERE file_id = ?",
                (file_id,),
            ).fetchall()
            max_minor = max(
                (_minor_version(str(row["version_no"])) for row in rows),
                default=-1,
            )
            version_no = f"v1.{max_minor + 1}"
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_version (
                    file_id, version_no, description, quality_score,
                    parent_version_id, source_workflow_id, analysis_run_id,
                    action_batch_id, vector_index_status, vector_index_generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 0)
                """,
                (
                    file_id,
                    version_no,
                    description,
                    quality_score,
                    parent_version_id,
                    source_workflow_id,
                    analysis_run_id,
                    action_batch_id,
                ),
            )
            return int(cursor.lastrowid), version_no, True

    def get_version(self, version_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, parent_version_id, source_workflow_id,
                       analysis_run_id, action_batch_id, vector_index_status,
                       vector_index_generation, verification_status, created_time
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
            clauses.append("file_id = ?")
            params.append(file_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, parent_version_id, source_workflow_id,
                       analysis_run_id, action_batch_id, vector_index_status,
                       vector_index_generation, verification_status, created_time
                FROM taxonomy_version
                {where}
                ORDER BY id
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_for_file(self, file_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, parent_version_id, source_workflow_id,
                       analysis_run_id, action_batch_id, vector_index_status,
                       vector_index_generation, verification_status, created_time
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
                       snapshot_path, parent_version_id, source_workflow_id,
                       analysis_run_id, action_batch_id, vector_index_status,
                       vector_index_generation, verification_status, created_time
                FROM taxonomy_version
                WHERE file_id = ? AND version_no = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (file_id, version_no),
            ).fetchone()
        return dict(row) if row else None

    def get_by_action_batch(self, action_batch_id: str) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                "SELECT id FROM taxonomy_version WHERE action_batch_id = ?",
                (action_batch_id,),
            ).fetchone()
        return self.get_version(int(row["id"])) if row else None

    def is_descendant(self, base_version_id: int, result_version_id: int) -> bool:
        current = self.get_version(result_version_id)
        visited: set[int] = set()
        while current and current.get("parent_version_id") is not None:
            parent_id = int(current["parent_version_id"])
            if parent_id == base_version_id:
                return True
            if parent_id in visited:
                return False
            visited.add(parent_id)
            current = self.get_version(parent_id)
        return False

    def update_quality_score(self, version_id: int, quality_score: float) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE taxonomy_version SET quality_score = ? WHERE id = ?",
                (quality_score, version_id),
            )

    def update_vector_index_status(
        self,
        version_id: int,
        status: str,
        *,
        increment_generation: bool = False,
    ) -> None:
        generation_sql = (
            "vector_index_generation = vector_index_generation + 1,"
            if increment_generation
            else ""
        )
        with connect(self.settings) as connection:
            connection.execute(
                f"""
                UPDATE taxonomy_version
                SET {generation_sql} vector_index_status = ?
                WHERE id = ?
                """,
                (status, version_id),
            )

    def update_verification_status(self, version_id: int, status: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE taxonomy_version SET verification_status = ? WHERE id = ?",
                (status, version_id),
            )


def _minor_version(version_no: str) -> int:
    if not version_no.startswith("v1."):
        return -1
    try:
        return int(version_no.split(".", 1)[1])
    except ValueError:
        return -1
