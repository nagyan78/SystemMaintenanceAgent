from typing import Any

from backend.app.config import Settings
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion, SuggestionRecord
from backend.app.services.action_service import ActionService
from backend.app.services.version_service import VersionService
from backend.app.tools.validation_tools import validate_suggestion_action


class ReviewService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.suggestion_repo = SuggestionRepository(settings)
        self.log_repo = OperationLogRepository(settings)

    def list_review_batch(self, review_batch_id: str) -> list[SuggestionRecord]:
        return self.suggestion_repo.list_suggestions(review_batch_id=review_batch_id)

    def approve_suggestion(self, suggestion_id: int, operator: str = "local_user") -> SuggestionRecord:
        suggestion = self._require_mutable_suggestion(suggestion_id)
        self.suggestion_repo.update_status(suggestion_id, "approved")
        self._log(suggestion, operator, "approve_suggestion")
        return self.suggestion_repo.get_suggestion(suggestion_id) or suggestion

    def reject_suggestion(
        self,
        suggestion_id: int,
        operator: str = "local_user",
        reject_reason: str | None = None,
    ) -> SuggestionRecord:
        suggestion = self._require_mutable_suggestion(suggestion_id)
        self.suggestion_repo.update_status(suggestion_id, "rejected")
        self._log(
            suggestion,
            operator,
            "reject_suggestion",
            {"reject_reason": reject_reason or ""},
        )
        return self.suggestion_repo.get_suggestion(suggestion_id) or suggestion

    def edit_suggestion(
        self,
        suggestion_id: int,
        edited: AdjustmentSuggestion,
        operator: str = "local_user",
    ) -> SuggestionRecord:
        current = self._require_mutable_suggestion(suggestion_id)
        validation = validate_suggestion_action(edited, self.settings)
        if not validation.valid:
            raise ValueError(validation.reason)
        self.suggestion_repo.update_suggestion(suggestion_id, edited)
        updated = self.suggestion_repo.get_suggestion(suggestion_id)
        self._log(updated or current, operator, "edit_suggestion")
        return updated or current

    def batch_approve(
        self,
        suggestion_ids: list[int],
        operator: str = "local_user",
    ) -> list[SuggestionRecord]:
        suggestions = self.suggestion_repo.list_by_ids(suggestion_ids)
        if len(suggestions) != len(set(suggestion_ids)):
            raise ValueError("部分 suggestion_id 不存在。")
        for suggestion in suggestions:
            if suggestion.status != "pending":
                raise ValueError("批量接受只允许 pending 建议。")
            if suggestion.risk_level != "low":
                raise ValueError("批量接受只允许 low 风险建议。")
        for suggestion in suggestions:
            self.suggestion_repo.update_status(suggestion.id, "approved")
            self._log(suggestion, operator, "batch_approve_suggestion")
        return self.suggestion_repo.list_by_ids(suggestion_ids)

    def apply_workflow_decision(self, review_batch_id: str, decision: dict[str, Any]) -> int:
        operator = decision.get("operator") or "local_user"
        approved_ids = [int(item) for item in decision.get("approved_suggestion_ids", [])]
        rejected_ids = [int(item) for item in decision.get("rejected_suggestion_ids", [])]
        edits = decision.get("edits", []) or []
        review_decision = decision.get("decision")

        batch_ids = {item.id for item in self.list_review_batch(review_batch_id)}
        if approved_ids or rejected_ids or edits:
            requested_ids = set(approved_ids) | set(rejected_ids) | {int(item["suggestion_id"]) for item in edits}
            if not requested_ids.issubset(batch_ids):
                raise ValueError("审核决策包含不属于当前批次的 suggestion_id。")

        for edit in edits:
            current = self.suggestion_repo.get_suggestion(int(edit["suggestion_id"]))
            if current is None:
                raise ValueError("编辑的 suggestion_id 不存在。")
            payload = {**current.model_dump(), **edit.get("suggestion", {})}
            payload.pop("id", None)
            payload.pop("review_batch_id", None)
            self.edit_suggestion(
                int(edit["suggestion_id"]),
                AdjustmentSuggestion.model_validate(payload),
                operator,
            )
        for suggestion_id in approved_ids:
            self.approve_suggestion(suggestion_id, operator)
        for suggestion_id in rejected_ids:
            self.reject_suggestion(suggestion_id, operator, decision.get("reject_reason"))
        if review_decision == "reject" and not rejected_ids:
            for suggestion in self.list_review_batch(review_batch_id):
                if suggestion.status in {"pending", "edited"}:
                    self.reject_suggestion(suggestion.id, operator, decision.get("reject_reason"))
        return len(approved_ids)

    def execute_approved_actions(self, review_batch_id: str, operator: str = "local_user") -> dict[str, Any]:
        suggestions = self.list_review_batch(review_batch_id)
        if not suggestions:
            raise ValueError("Review batch not found.")
        approved = [item for item in suggestions if item.status == "approved"]
        base_version = VersionRepository(self.settings).get_version(suggestions[0].version_id)
        if base_version is None:
            raise ValueError("Review batch base version not found.")
        latest_version = VersionRepository(self.settings).get_latest_for_file(int(base_version["file_id"]))
        if latest_version is None:
            raise ValueError("No version found for review batch file.")
        latest_version_id = int(latest_version["id"])
        if not approved:
            return {
                "review_batch_id": review_batch_id,
                "source_version_id": latest_version_id,
                "new_version_id": None,
                "new_version_no": None,
                "executed_count": 0,
                "failed_count": 0,
                "message": "没有已批准且待执行的建议。",
            }
        action_result = ActionService(self.settings).execute_suggestion_records(
            version_id=latest_version_id,
            review_batch_id=review_batch_id,
            approved=approved,
            operator=operator,
        )
        save_result = VersionService(self.settings).save_new_version(
            base_version_id=latest_version_id,
            review_batch_id=review_batch_id,
            action_batch_id=action_result.action_batch_id,
            nodes=action_result.nodes,
        )
        return {
            "review_batch_id": review_batch_id,
            "source_version_id": latest_version_id,
            "new_version_id": save_result.new_version_id,
            "new_version_no": save_result.new_version_no,
            "node_count": save_result.node_count,
            "executed_count": action_result.executed_count,
            "failed_count": action_result.failed_count,
            "quality_score": save_result.quality_score,
        }

    def _require_mutable_suggestion(self, suggestion_id: int) -> SuggestionRecord:
        suggestion = self.suggestion_repo.get_suggestion(suggestion_id)
        if suggestion is None:
            raise ValueError("suggestion_id 不存在。")
        if suggestion.status not in {"pending", "edited"}:
            raise ValueError("当前建议状态不允许审核操作。")
        return suggestion

    def _log(
        self,
        suggestion: SuggestionRecord,
        operator: str,
        operation_type: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        detail = {
            "suggestion_id": suggestion.id,
            "action_type": suggestion.action_type,
            "target_node_id": suggestion.target_node_id,
            **(extra or {}),
        }
        self.log_repo.create_log(
            version_id=suggestion.version_id,
            operator=operator,
            operation_type=operation_type,
            operation_detail=detail,
        )
