from typing import Any, Literal

from pydantic import BaseModel, Field

AgentRunStatus = Literal["pending", "running", "completed", "completed_degraded", "failed", "cancelled"]
WorkItemStatus = Literal["pending", "running", "succeeded", "clean", "inconclusive", "retryable_failed", "permanent_failed", "skipped", "cancelled"]


class AgentRunRecord(BaseModel):
    id: str | None = None
    workflow_id: str
    agent_type: str
    version_id: int
    plan_revision: int = 1
    status: AgentRunStatus = "pending"
    model_profile: str = "default"
    budget: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)


class AgentWorkItemRecord(BaseModel):
    id: str | None = None
    run_id: str
    subject_type: str
    subject_id: str
    status: WorkItemStatus = "pending"
    attempt: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
