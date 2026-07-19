from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class ModelEndpoint(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    model: str
    base_url: str = ""
    api_key_env: str = ""
    timeout_seconds: int = 60
    client: Any | None = None

class ModelProfile(BaseModel):
    task_type: Literal["planning", "diagnosis", "suggestion", "evaluation", "report"]
    primary: ModelEndpoint
    fallback: ModelEndpoint | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    max_attempts: int = Field(default=3, ge=1, le=5)

class ModelBudget(BaseModel):
    max_calls: int
    max_tokens: int
    max_cost_units: float = 0

class ModelUsage(BaseModel):
    calls: int = 0
    tokens: int = 0
    fallback_calls: int = 0
