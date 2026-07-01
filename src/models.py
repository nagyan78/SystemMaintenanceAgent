"""Shared data models used by checker modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class IssueResult:
    """A normalized diagnosis issue produced by rule checkers."""

    issue_type: str
    node_id: str
    node_name: str
    path: str
    severity: str
    reason: str
    suggestion: str
    confidence: float
    need_manual_review: bool

    def to_dict(self) -> dict[str, object]:
        """Return the issue as a plain dictionary for reports or exports."""

        return asdict(self)

