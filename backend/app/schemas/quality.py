from typing import Any, Literal

from pydantic import BaseModel, Field


EvaluationRole = Literal["baseline", "result", "verify_base", "verify_result"]


class QualityMetrics(BaseModel):
    structural_integrity: float = Field(ge=0, le=25)
    hierarchy_balance: float = Field(ge=0, le=20)
    semantic_consistency: float = Field(ge=0, le=20)
    redundancy: float = Field(ge=0, le=15)
    naming_quality: float = Field(ge=0, le=10)
    coverage_confidence: float = Field(ge=0, le=10)


class QualityEvaluation(BaseModel):
    id: int | None = None
    version_id: int
    workflow_id: str
    analysis_run_id: str
    evaluation_role: EvaluationRole
    score_version: str = "quality-v1"
    total_score: float = Field(ge=0, le=100)
    available_points: float = Field(ge=0, le=100)
    coverage_ratio: float = Field(ge=0, le=1)
    dimensions: QualityMetrics
    available_dimensions: dict[str, bool]
    metrics: dict[str, Any] = Field(default_factory=dict)
    detector_versions: dict[str, str] = Field(default_factory=dict)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    narrative: str = ""


class VerificationResult(BaseModel):
    status: Literal["passed", "partially_passed", "failed", "degraded"]
    resolved_fingerprints: list[str] = Field(default_factory=list)
    unresolved_fingerprints: list[str] = Field(default_factory=list)
    introduced_fingerprints: list[str] = Field(default_factory=list)
    quality_delta: float
    next_decision: Literal["finish", "ask_continue", "manual_intervention"]
    reason: str
