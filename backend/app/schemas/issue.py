from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class DiagnosisIssueRecord(BaseModel):
    issue_type: str
    node_id: int | None = None
    node_name: str | None = None
    description: str
    reason: str
    risk_level: str
    confidence: float
    status: str = "pending"


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
    sample_strategy: Literal["focused", "full_scan", "sampling"] = "focused"
    focus_issues: list[str] = Field(default_factory=list)
    estimated_candidates: int = 200


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


class ReportResult(BaseModel):
    version_id: int
    report_name: str
    report_path: Path
    status: str
