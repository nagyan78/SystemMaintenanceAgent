import json

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.schemas.quality import QualityEvaluation


class QualityRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def upsert(self, evaluation: QualityEvaluation) -> QualityEvaluation:
        payload = evaluation.model_dump(exclude={"id"})
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO quality_evaluation (
                    version_id, workflow_id, analysis_run_id, evaluation_role,
                    score_version, total_score, available_points, coverage_ratio,
                    dimensions, available_dimensions, metrics, detector_versions,
                    risks, narrative
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    workflow_id, analysis_run_id, version_id,
                    score_version, evaluation_role
                ) DO UPDATE SET
                    total_score = excluded.total_score,
                    available_points = excluded.available_points,
                    coverage_ratio = excluded.coverage_ratio,
                    dimensions = excluded.dimensions,
                    available_dimensions = excluded.available_dimensions,
                    metrics = excluded.metrics,
                    detector_versions = excluded.detector_versions,
                    risks = excluded.risks,
                    narrative = excluded.narrative,
                    updated_time = CURRENT_TIMESTAMP
                """,
                (
                    payload["version_id"],
                    payload["workflow_id"],
                    payload["analysis_run_id"],
                    payload["evaluation_role"],
                    payload["score_version"],
                    payload["total_score"],
                    payload["available_points"],
                    payload["coverage_ratio"],
                    _dump(payload["dimensions"]),
                    _dump(payload["available_dimensions"]),
                    _dump(payload["metrics"]),
                    _dump(payload["detector_versions"]),
                    _dump(payload["risks"]),
                    payload["narrative"],
                ),
            )
            row = connection.execute(
                """
                SELECT id FROM quality_evaluation
                WHERE workflow_id = ? AND analysis_run_id = ?
                  AND version_id = ? AND score_version = ?
                  AND evaluation_role = ?
                """,
                (
                    payload["workflow_id"],
                    payload["analysis_run_id"],
                    payload["version_id"],
                    payload["score_version"],
                    payload["evaluation_role"],
                ),
            ).fetchone()
        return evaluation.model_copy(update={"id": int(row["id"])})

    def get(self, evaluation_id: int) -> QualityEvaluation | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                "SELECT * FROM quality_evaluation WHERE id = ?",
                (evaluation_id,),
            ).fetchone()
        return _from_row(dict(row)) if row else None

    def get_for_role(
        self,
        *,
        workflow_id: str,
        analysis_run_id: str,
        version_id: int,
        evaluation_role: str,
        score_version: str = "quality-v1",
    ) -> QualityEvaluation | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT * FROM quality_evaluation
                WHERE workflow_id = ? AND analysis_run_id = ?
                  AND version_id = ? AND evaluation_role = ?
                  AND score_version = ?
                """,
                (
                    workflow_id,
                    analysis_run_id,
                    version_id,
                    evaluation_role,
                    score_version,
                ),
            ).fetchone()
        return _from_row(dict(row)) if row else None


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _from_row(row: dict) -> QualityEvaluation:
    for key in (
        "dimensions",
        "available_dimensions",
        "metrics",
        "detector_versions",
        "risks",
    ):
        row[key] = json.loads(row[key])
    return QualityEvaluation.model_validate(row)
