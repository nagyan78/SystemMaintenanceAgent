from typing import Literal

from pydantic import BaseModel


class TaxonomyGraphState(BaseModel):
    file_id: int | None = None
    version_id: int | None = None
    task_id: str | None = None
    current_step: str | None = None
    structure_issue_count: int = 0
    content_issue_count: int = 0
    suggestion_count: int = 0
    approved_action_count: int = 0
    error_message: str | None = None
    status: Literal["pending", "running", "waiting_review", "completed", "failed"] = "pending"

