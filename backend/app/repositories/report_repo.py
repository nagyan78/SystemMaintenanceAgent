from backend.app.config import Settings
from backend.app.db import connect


class ReportRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def save(self, *, version_id: int, report_type: str, report_path: str,
             review_batch_id: str | None = None, workflow_id: str | None = None,
             run_id: str | None = None, fact_payload: str = "{}") -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """INSERT INTO report_artifact(version_id,review_batch_id,report_type,report_path,workflow_id,run_id,fact_payload)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(version_id,report_type) DO UPDATE SET
                   review_batch_id=excluded.review_batch_id,report_path=excluded.report_path,
                   workflow_id=excluded.workflow_id,run_id=excluded.run_id,
                   fact_payload=excluded.fact_payload,status='generated',created_time=CURRENT_TIMESTAMP""",
                (version_id, review_batch_id, report_type, report_path, workflow_id, run_id, fact_payload),
            )

    def get(self, version_id: int, report_type: str) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                "SELECT * FROM report_artifact WHERE version_id=? AND report_type=?",
                (version_id, report_type),
            ).fetchone()
        return dict(row) if row else None
