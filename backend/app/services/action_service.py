import json
from typing import Any

from backend.app.config import Settings
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.suggestion import ActionValidationResult, AdjustmentSuggestion, SuggestionRecord
from backend.app.tools.validation_tools import validate_suggestion_action


class ActionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.suggestion_repo = SuggestionRepository(settings)
        self.log_repo = OperationLogRepository(settings)
        self.taxonomy_repo = TaxonomyRepository(settings)

    def validate_approved_actions(self, review_batch_id: str) -> list[ActionValidationResult]:
        approved = [
            item
            for item in self.suggestion_repo.list_suggestions(review_batch_id=review_batch_id)
            if item.status == "approved"
        ]
        return [
            validate_suggestion_action(
                AdjustmentSuggestion.model_validate(item.model_dump(exclude={"id", "review_batch_id"})),
                self.settings,
            ).model_copy(update={"suggestion_id": item.id})
            for item in approved
        ]
