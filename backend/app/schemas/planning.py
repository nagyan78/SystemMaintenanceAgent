from typing import Literal
from pydantic import BaseModel, Field, computed_field

IssueType = Literal["synonym_pollution", "semantic_duplicate", "bad_parent_child_relation", "inconsistent_granularity", "naming_irregular", "wide_node", "deep_level"]

class DiagnosisTarget(BaseModel):
    issue_type: IssueType
    priority_subtree_ids: list[int] = Field(default_factory=list)
    candidate_budget: int = Field(ge=1, le=1000)

class MaintenancePlan(BaseModel):
    id: str
    workflow_id: str
    base_version_id: int
    revision: int = Field(ge=1)
    strategy: Literal["focused", "sampling", "full_screening"]
    targets: list[DiagnosisTarget] = Field(min_length=1)
    max_model_calls: int = Field(ge=1)
    max_tokens: int = Field(ge=1)
    max_wall_seconds: int = Field(ge=1)
    max_rounds: int = Field(ge=1, le=5)
    target_quality_score: float = Field(ge=0, le=100)
    decision: Literal["initial", "expand", "shrink", "continue", "stop"] = "initial"
    stop_reason: str | None = None

class DiagnosisBatchFeedback(BaseModel):
    batch_id: str
    plan_revision: int
    subtree_id: int | None = None
    processed: int
    issues: int
    clean: int
    inconclusive: int
    failed: int
    model_calls: int
    tokens: int
    wall_seconds: float
    previous_hit_rate: float | None = None

    @computed_field
    @property
    def hit_rate(self) -> float:
        return self.issues / max(self.processed, 1)
