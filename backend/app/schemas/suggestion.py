from typing import Any, Literal

from pydantic import BaseModel, Field


ActionType = Literal[
    "add_node",
    "move_node",
    "rename_node",
    "merge_node",
    "clean_synonym",
    "update_synonyms",
    "review_only",
    "split_subtree",
    "deprecate_node",
    "delete_leaf_node",
    "collapse_intermediate_node",
    "mark_as_valid",
]
RiskLevel = Literal["low", "medium", "high"]
SuggestionStatus = Literal["pending", "approved", "rejected", "deferred", "edited", "executed", "failed"]


class AdjustmentSuggestion(BaseModel):
    issue_id: int
    version_id: int
    action_type: ActionType
    target_node_id: int | None = None
    target_node_name: str | None = None
    old_parent_id: int | None = None
    new_parent_id: int | None = None
    old_name: str | None = None
    new_name: str | None = None
    action_payload: dict[str, Any] = Field(default_factory=dict)
    reason: str
    suggestion: str
    risk_level: RiskLevel
    confidence: float = Field(ge=0.0, le=1.0)
    need_confirm: bool = True
    status: SuggestionStatus = "pending"


class SuggestionRecord(AdjustmentSuggestion):
    id: int
    review_batch_id: str | None = None
    work_item_id: str | None = None
    analysis_run_id: str | None = None
    change_preview: dict[str, Any] = Field(default_factory=dict)
    consistency_status: str = "unchecked"
    consistency_reason: str | None = None
    is_manual: bool = False
    regenerated_at: str | None = None
    generator_version: str | None = None


class SuggestionGenerationResult(BaseModel):
    version_id: int
    review_batch_id: str | None = None
    generated_count: int
    suggestions: list[SuggestionRecord] = Field(default_factory=list)


class ActionValidationResult(BaseModel):
    valid: bool
    reason: str = ""
    suggestion_id: int | None = None
