from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class DiagnosisIssueRecord(BaseModel):
    issue_type: str
    node_id: int | None = None
    node_name: str | None = None
    subject_node_id: int | None = None
    subject_node_name: str | None = None
    subject_path: str | None = None
    description: str
    reason: str
    risk_level: str
    confidence: float
    status: str = "pending"
    path: str | None = None
    evidence: str | None = None
    source: str = "structure_rule"


class StructureDiagnosisResult(BaseModel):
    version_id: int
    status: str
    issue_count: int
    summary: dict[str, int]


class IndexResult(BaseModel):
    version_id: int
    status: str
    indexed_count: int = 0
    error_message: str | None = None


class DiagnosisPlan(BaseModel):
    priority_subtrees: list[str] = Field(default_factory=list)
    priority_subtree_ids: list[int] = Field(default_factory=list)
    sample_strategy: Literal["focused", "full_scan", "sampling"] = "sampling"
    focus_issues: list[str] = Field(default_factory=list)
    estimated_candidates: int = 200


class DiagnosisCoverage(BaseModel):
    """Stable, shared coverage facts for API, report and acceptance checks."""

    total_nodes: int = 0
    rule_scanned_nodes: int = 0
    rule_issue_count: int = 0
    candidate_count: int = 0
    deep_diagnosed_count: int = 0
    ai_issue_count: int = 0
    reasonable_count: int = 0
    problem_count: int = 0
    ai_content_sample_score: float | None = None
    sample_seed: int | None = None
    sample_assessments: list[dict[str, Any]] = Field(default_factory=list)
    skipped_count: int = 0
    failed_count: int = 0
    unexamined_reasons: dict[str, int] = Field(default_factory=dict)
    model_calls: int = 0
    tokens_used: int = 0
    wall_seconds: float = 0
    plan_revision: int = 1
    stop_reason: str | None = None
    rules_complete: bool = False
    ai_complete: bool = False
    coverage_complete: bool = False
    completion_status: Literal["completed", "partial", "failed"] = "completed"
    run_id: str | None = None
    workflow_id: str | None = None
    plan: dict[str, Any] = Field(default_factory=dict)


class ContentDiagnosisOutput(BaseModel):
    is_issue: bool
    issue_type: Literal[
        "synonym_pollution",
        "semantic_duplicate",
        "bad_parent_child_relation",
        "inconsistent_granularity",
        "naming_irregular",
    ] | None = None
    abnormal_synonyms: list[str] = Field(default_factory=list)
    reason: str = ""
    risk_level: Literal["low", "medium", "high"] = "low"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContentIssue(DiagnosisIssueRecord):
    issue_id: str | None = None


class ContentSampleAssessment(BaseModel):
    conclusion: Literal["reasonable", "problem", "uncertain"]
    node_id: int
    node_name: str | None = None
    reason: str
    issue: ContentIssue | None = None


class ReportResult(BaseModel):
    version_id: int
    report_name: str
    report_path: Path
    status: str
