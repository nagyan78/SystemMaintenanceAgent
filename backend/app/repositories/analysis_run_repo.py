from uuid import uuid4

from backend.app.config import Settings
from backend.app.db import connect


class AnalysisRunRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_or_get(
        self,
        *,
        workflow_id: str,
        round_no: int,
        analyzed_version_id: int,
    ) -> str:
        with connect(self.settings) as connection:
            existing = connection.execute(
                "SELECT id FROM analysis_run WHERE workflow_id = ? AND round = ?",
                (workflow_id, round_no),
            ).fetchone()
            if existing:
                return str(existing["id"])
            run_id = f"analysis_{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO analysis_run (
                    id, workflow_id, round, analyzed_version_id, status
                ) VALUES (?, ?, ?, ?, 'running')
                """,
                (run_id, workflow_id, round_no, analyzed_version_id),
            )
            return run_id

    def get(self, analysis_run_id: str) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                "SELECT * FROM analysis_run WHERE id = ?",
                (analysis_run_id,),
            ).fetchone()
        return dict(row) if row else None
