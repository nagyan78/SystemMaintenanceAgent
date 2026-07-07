from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


WorkflowStatus = Literal[
    "pending",
    "running",
    "waiting_review",
    "completed",
    "failed",
    "cancelled",
]

ReviewDecision = Literal["approve", "reject", "edit"]


class TaxonomyGraphState(BaseModel):
    workflow_id: str
    thread_id: str
    task_id: str | None = None

    file_id: int | None = None
    file_path: str | None = None
    file_name: str | None = None

    base_version_id: int | None = None
    current_version_id: int | None = None
    new_version_id: int | None = None
    version_no: str | None = None

    status: WorkflowStatus = "pending"
    current_step: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    completed_steps: list[str] = Field(default_factory=list)

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

    report_id: int | None = None
    report_path: str | None = None
    export_path: str | None = None

    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_waiting_review_state(self) -> "TaxonomyGraphState":
        if self.status == "waiting_review" and not self.review_batch_id:
            raise ValueError("waiting_review state requires review_batch_id.")
        return self
