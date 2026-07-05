from pathlib import Path

from pydantic import BaseModel


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


class ReportResult(BaseModel):
    version_id: int
    report_name: str
    report_path: Path
    status: str
