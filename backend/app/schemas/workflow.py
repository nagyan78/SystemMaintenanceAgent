from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator


WorkflowMode = Literal["import", "maintain", "verify"]


class StartWorkflowRequest(BaseModel):
    mode: WorkflowMode = "import"
    file_id: int | None = None
    base_version_id: int | None = None
    result_version_id: int | None = None
    affected_node_ids: list[int] = Field(default_factory=list)
    max_rounds: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def validate_scope(self) -> "StartWorkflowRequest":
        if self.mode == "import" and self.file_id is None:
            raise ValueError("import mode requires file_id")
        if self.mode == "maintain" and self.file_id is None and self.base_version_id is None:
            raise ValueError("maintain mode requires file_id or base_version_id")
        if self.mode == "verify" and (
            self.base_version_id is None or self.result_version_id is None
        ):
            raise ValueError("verify mode requires base_version_id and result_version_id")
        return self


class HumanReviewResume(BaseModel):
    interrupt_type: Literal["human_review"]
    interrupt_id: str
    decision: Literal["approve", "reject", "edit"]
    approved_suggestion_ids: list[int] = Field(default_factory=list)
    rejected_suggestion_ids: list[int] = Field(default_factory=list)
    edits: list[dict[str, Any]] = Field(default_factory=list)
    operator: str = "local_user"
    reject_reason: str | None = None


class ContinueResume(BaseModel):
    interrupt_type: Literal["continue_optimization"]
    interrupt_id: str
    decision: Literal["continue", "finish"]
    operator: str = "local_user"


ResumeWorkflowRequest = Annotated[
    HumanReviewResume | ContinueResume,
    Field(discriminator="interrupt_type"),
]
_RESUME_ADAPTER = TypeAdapter(ResumeWorkflowRequest)


def parse_resume_request(payload: dict[str, Any]) -> HumanReviewResume | ContinueResume:
    return _RESUME_ADAPTER.validate_python(payload)
