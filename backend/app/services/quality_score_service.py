from dataclasses import dataclass
from typing import Any, Iterable

from backend.app.domain.issue_types import get_issue_type


ISSUE_TYPE_PENALTY_POINTS: dict[str, float] = {
    "missing_parent": 10.0,
    "duplicate_sibling": 10.0,
    "semantic_duplicate": 10.0,
    "semantic_misplacement": 10.0,
    "excessive_depth": 5.0,
    "excessive_width": 5.0,
    "parent_child_redundancy": 5.0,
    "inconsistent_dimension": 5.0,
    "naming_nonstandard": 5.0,
    "synonym_conflict": 5.0,
    "synonym_overlap": 5.0,
    "unknown": 5.0,
    "synonym_format": 1.0,
    "synonym_typo": 1.0,
}

RISK_PENALTY_POINTS = {"low": 1.0, "medium": 5.0, "high": 10.0}
MIN_NORMALIZATION_NODES = 1_000


@dataclass(frozen=True)
class QualityScoreResult:
    score: float
    total_nodes: int
    active_issue_count: int
    affected_node_count: int
    weighted_error_count: float
    weighted_error_rate: float
    verdict: str


@dataclass(frozen=True)
class CompositeQualityScoreResult:
    structure_score: float
    content_rule_score: float
    ai_content_sample_score: float | None
    overall_quality_score: float | None


def calculate_quality_score(total_nodes: int, issues: Iterable[dict[str, Any]]) -> QualityScoreResult:
    """Deduct risk-weighted points per thousand nodes.

    Resolved and false-positive records do not affect the score. Deferred,
    non-executable and incomplete AI records remain active. A node is charged
    only for its most serious active issue so overlapping detectors do not
    multiply the same damaged taxonomy location. Files smaller than one
    thousand nodes use a one-thousand-node normalization floor so a single
    defect does not dominate a small fixture.
    """
    active = [item for item in issues if str(item.get("status") or "pending") not in {"resolved", "false_positive"}]
    by_subject: dict[str, float] = {}
    for index, issue in enumerate(active):
        node_id = issue.get("subject_node_id") or issue.get("node_id")
        subject = f"node:{node_id}" if node_id is not None else f"issue:{issue.get('id', index)}"
        issue_type = str(issue.get("issue_type_code") or issue.get("issue_type") or "unknown")
        weight = RISK_PENALTY_POINTS.get(
            str(issue.get("risk_level") or ""),
            ISSUE_TYPE_PENALTY_POINTS.get(issue_type, 5.0),
        )
        by_subject[subject] = max(by_subject.get(subject, 0.0), weight)

    weighted = round(sum(by_subject.values()), 4)
    if total_nodes <= 0:
        score = 0.0
        rate = 0.0
    else:
        normalization_nodes = max(total_nodes, MIN_NORMALIZATION_NODES)
        rate = weighted / normalization_nodes
        score = round(max(0.0, 100.0 - 1000.0 * rate), 2)
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


def calculate_composite_quality_score(
    total_nodes: int,
    issues: Iterable[dict[str, Any]],
    *,
    ai_content_sample_score: float | None,
) -> CompositeQualityScoreResult:
    records = list(issues)
    structure = [
        item for item in records
        if get_issue_type(str(item.get("issue_type_code") or item.get("issue_type"))).category == "structure"
    ]
    content_rules = [
        item for item in records
        if get_issue_type(str(item.get("issue_type_code") or item.get("issue_type"))).category == "content"
        and str(item.get("source") or "") == "content_rule"
    ]
    structure_score = calculate_quality_score(total_nodes, structure).score
    content_rule_score = calculate_quality_score(total_nodes, content_rules).score
    overall = None
    if ai_content_sample_score is not None:
        overall = round(
            0.40 * structure_score
            + 0.10 * content_rule_score
            + 0.50 * float(ai_content_sample_score),
            2,
        )
    return CompositeQualityScoreResult(
        structure_score=structure_score,
        content_rule_score=content_rule_score,
        ai_content_sample_score=ai_content_sample_score,
        overall_quality_score=overall,
    )
