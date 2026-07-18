from typing import Any

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.quality_repo import QualityRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository


class WorkflowEvidenceRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_report_evidence(
        self,
        *,
        workflow_id: str,
        analysis_run_id: str,
        analyzed_version_id: int,
        result_version_id: int | None,
    ) -> dict[str, Any]:
        quality = QualityRepository(self.settings)
        before = quality.get_for_role(
            workflow_id=workflow_id,
            analysis_run_id=analysis_run_id,
            version_id=analyzed_version_id,
            evaluation_role="baseline",
        ) or quality.get_for_role(
            workflow_id=workflow_id,
            analysis_run_id=analysis_run_id,
            version_id=analyzed_version_id,
            evaluation_role="verify_base",
        )
        after = None
        if result_version_id is not None:
            after = quality.get_for_role(
                workflow_id=workflow_id,
                analysis_run_id=analysis_run_id,
                version_id=result_version_id,
                evaluation_role="result",
            ) or quality.get_for_role(
                workflow_id=workflow_id,
                analysis_run_id=analysis_run_id,
                version_id=result_version_id,
                evaluation_role="verify_result",
            )
        return {
            "issues": DiagnosisRepository(self.settings).list_for_run(analysis_run_id),
            "suggestions": SuggestionRepository(self.settings).list_for_run(
                analysis_run_id
            ),
            "operations": OperationLogRepository(self.settings).list_for_run(
                analysis_run_id
            ),
            "evaluation_before": before,
            "evaluation_after": after,
        }
