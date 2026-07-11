from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


WorkflowStatus = Literal[
    "pending",
    "running",
    "waiting_review",
    "waiting_continue",
    "waiting_manual_intervention",
    "completed",
    "completed_degraded",
    "failed",
    "cancelled",
]

ReviewDecision = Literal["approve", "reject", "edit"]


class TaxonomyGraphState(BaseModel):
    workflow_id: str
    thread_id: str
    task_id: str | None = None
    workflow_mode: Literal["import", "maintain", "verify"] = "import"

    file_id: int | None = None
    file_path: str | None = None
    file_name: str | None = None

    base_version_id: int | None = None
    current_version_id: int | None = None
    new_version_id: int | None = None
    result_version_id: int | None = None
    version_no: str | None = None

    status: WorkflowStatus = "pending"
    current_step: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    completed_steps: list[str] = Field(default_factory=list)
    analysis_run_id: str | None = None
    evaluation_before_id: int | None = None
    evaluation_after_id: int | None = None
    verification_payload: dict[str, Any] | None = None
    round: int = Field(default=1, ge=1)
    max_rounds: int = Field(default=2, ge=1, le=5)
    affected_node_ids: list[int] = Field(default_factory=list)
    budget_summary: dict[str, Any] = Field(default_factory=dict)

    row_count: int = 0
    column_count: int = 0
    node_count: int = 0
    max_depth: int = 0
    max_children_count: int = 0
    vector_index_status: str | None = None
    vector_index_count: int = 0
    structure_issue_count: int = 0
    structure_issue_summary: dict[str, int] = Field(default_factory=dict)
    content_issue_count: int = 0
    diagnosis_plan: dict[str, Any] | None = None
    suggestion_count: int = 0
    approved_action_count: int = 0
    executed_action_count: int = 0
    failed_action_count: int = 0
    action_batch_id: str | None = None
    executed_nodes: list[dict[str, Any]] = Field(default_factory=list)

    review_batch_id: str | None = None
    review_decision: ReviewDecision | None = None
    review_payload: dict[str, Any] | None = None
    interrupt_type: Literal["human_review", "continue_optimization"] | None = None
    interrupt_id: str | None = None

    report_id: int | None = None
    report_path: str | None = None
    export_path: str | None = None

    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_waiting_review_state(self) -> "TaxonomyGraphState":
        if self.status == "waiting_review" and not self.review_batch_id:
            raise ValueError("waiting_review state requires review_batch_id.")
        if self.status == "waiting_continue" and (
            self.interrupt_type != "continue_optimization" or not self.interrupt_id
        ):
            raise ValueError(
                "waiting_continue state requires continue_optimization interrupt."
            )
        return self
