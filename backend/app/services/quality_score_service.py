from dataclasses import dataclass
from typing import Any, Iterable


ISSUE_TYPE_WEIGHTS: dict[str, float] = {
    "missing_parent": 1.0,
    "duplicate_sibling": 1.0,
    "semantic_duplicate": 1.0,
    "semantic_misplacement": 1.0,
    "excessive_depth": 0.6,
    "excessive_width": 0.6,
    "parent_child_redundancy": 0.6,
    "inconsistent_dimension": 0.6,
    "naming_nonstandard": 0.6,
    "synonym_conflict": 0.6,
    "synonym_overlap": 0.6,
    "unknown": 0.6,
    "synonym_format": 0.2,
    "synonym_typo": 0.2,
}


@dataclass(frozen=True)
class QualityScoreResult:
    score: float
    total_nodes: int
    active_issue_count: int
    affected_node_count: int
    weighted_error_count: float
    weighted_error_rate: float
    verdict: str


def calculate_quality_score(total_nodes: int, issues: Iterable[dict[str, Any]]) -> QualityScoreResult:
    """Score the share of affected nodes without hiding defects through rounding.

    Resolved and false-positive records do not affect the score. Deferred,
    non-executable and incomplete AI records remain active. A node is charged
    only for its most serious active issue so overlapping detectors do not
    multiply the same damaged taxonomy location.
    """
    active = [item for item in issues if str(item.get("status") or "pending") not in {"resolved", "false_positive"}]
    by_subject: dict[str, float] = {}
    for index, issue in enumerate(active):
        node_id = issue.get("subject_node_id") or issue.get("node_id")
        subject = f"node:{node_id}" if node_id is not None else f"issue:{issue.get('id', index)}"
        issue_type = str(issue.get("issue_type_code") or issue.get("issue_type") or "unknown")
        weight = ISSUE_TYPE_WEIGHTS.get(issue_type, 0.6)
        by_subject[subject] = max(by_subject.get(subject, 0.0), weight)

    weighted = round(sum(by_subject.values()), 4)
    if total_nodes <= 0:
        score = 0.0
        rate = 0.0
    else:
        rate = weighted / total_nodes
        score = round(max(0.0, 100.0 * (1.0 - rate)), 2)
        if active and score >= 100.0:
            score = 99.99
    return QualityScoreResult(
        score=score,
        total_nodes=total_nodes,
        active_issue_count=len(active),
        affected_node_count=len(by_subject),
        weighted_error_count=weighted,
        weighted_error_rate=round(rate, 8),
        verdict="质量通过" if not active else "需要整改",
    )
