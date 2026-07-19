from backend.app.config import Settings
from backend.app.db import connect


class VersionRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def increment_vector_index_generation(self, version_id: int) -> int:
        with connect(self.settings) as connection:
            connection.execute("UPDATE taxonomy_version SET vector_index_generation=vector_index_generation+1 WHERE id=?", (version_id,))
            row=connection.execute("SELECT vector_index_generation FROM taxonomy_version WHERE id=?", (version_id,)).fetchone()
        if row is None: raise ValueError("version not found")
        return int(row[0])

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
        action_batch_id: str | None = None,
        verification_status: str = "not_verified",
        export_path: str | None = None,
        supersedes_version_id: int | None = None,
        lifecycle_status: str = "draft",
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_version (
                    file_id, version_no, description, quality_score, snapshot_path,
                    parent_version_id, source_workflow_id, action_batch_id,
                    verification_status, export_path, supersedes_version_id, lifecycle_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, version_no, description, quality_score, snapshot_path,
                 parent_version_id, source_workflow_id, action_batch_id,
                 verification_status, export_path, supersedes_version_id, lifecycle_status),
            )
            return int(cursor.lastrowid)

    def get_version(self, version_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, file_id, version_no, description, quality_score,
                       snapshot_path, vector_index_generation, parent_version_id,
                       source_workflow_id, action_batch_id, verification_status,
                       export_path, supersedes_version_id, lifecycle_status,
                       diagnosis_mode, diagnosis_model, verification_mode, verification_model, created_time
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
                       version.snapshot_path, version.parent_version_id,
                       version.source_workflow_id, version.action_batch_id,
                       version.verification_status, version.export_path, version.supersedes_version_id,
                       version.lifecycle_status, version.diagnosis_mode, version.diagnosis_model,
                       version.verification_mode, version.verification_model,
                       version.created_time,
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
                       snapshot_path, parent_version_id, source_workflow_id,
                       action_batch_id, verification_status, export_path, supersedes_version_id,
                       lifecycle_status, diagnosis_mode, diagnosis_model, verification_mode, verification_model, created_time
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
                       action_batch_id, verification_status, export_path, supersedes_version_id,
                       lifecycle_status, diagnosis_mode, diagnosis_model, verification_mode, verification_model, created_time
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
                "SELECT id FROM taxonomy_version WHERE action_batch_id = ? LIMIT 1",
                (action_batch_id,),
            ).fetchone()
        return self.get_version(int(row["id"])) if row else None

    def update_verification(
        self,
        version_id: int,
        *,
        status: str,
        quality_score: float | None = None,
        export_path: str | None = None,
    ) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE taxonomy_version
                   SET verification_status = ?,
                       quality_score = COALESCE(?, quality_score),
                       export_path = COALESCE(?, export_path)
                   WHERE id = ?""",
                (status, quality_score, export_path, version_id),
            )

    def update_quality_score(self, version_id: int, quality_score: float) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE taxonomy_version SET quality_score = ? WHERE id = ?",
                (quality_score, version_id),
            )

    def update_snapshot_path(self, version_id: int, snapshot_path: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE taxonomy_version SET snapshot_path=? WHERE id=?",
                (snapshot_path, version_id),
            )

    def update_lifecycle(self, version_id: int, status: str) -> None:
        allowed = {"draft", "verifying", "passed", "partial", "failed", "released", "superseded"}
        if status not in allowed:
            raise ValueError("无效的版本生命周期状态。")
        with connect(self.settings) as connection:
            connection.execute("UPDATE taxonomy_version SET lifecycle_status=? WHERE id=?", (status, version_id))

    def update_model_metadata(
        self, version_id: int, *, diagnosis_mode: str | None = None,
        diagnosis_model: str | None = None, verification_mode: str | None = None,
        verification_model: str | None = None,
    ) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE taxonomy_version SET diagnosis_mode=COALESCE(?,diagnosis_mode),
                       diagnosis_model=COALESCE(?,diagnosis_model), verification_mode=COALESCE(?,verification_mode),
                       verification_model=COALESCE(?,verification_model) WHERE id=?""",
                (diagnosis_mode, diagnosis_model, verification_mode, verification_model, version_id),
            )

    def release(self, version_id: int) -> None:
        version = self.get_version(version_id)
        if not version or version.get("lifecycle_status") != "passed":
            raise ValueError("只有 passed 版本可以发布。")
        with connect(self.settings) as connection:
            connection.execute("UPDATE taxonomy_version SET lifecycle_status='superseded' WHERE file_id=? AND lifecycle_status='released'", (version["file_id"],))
            connection.execute("UPDATE taxonomy_version SET lifecycle_status='released' WHERE id=?", (version_id,))
