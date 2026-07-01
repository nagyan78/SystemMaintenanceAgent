"""Evaluation helpers for taxonomy quality and Agent maintenance effect."""

from __future__ import annotations

import pandas as pd

from .models import IssueResult


def evaluate_taxonomy_quality(df: pd.DataFrame, all_issues: list[IssueResult]) -> dict[str, object]:
    """Evaluate the static quality of the current product taxonomy.

    This function evaluates the taxonomy itself. It does not evaluate whether
    the Agent improved the taxonomy, because that requires before/after results.
    """

    return {
        "evaluation_type": "taxonomy_quality",
        "total_nodes": int(len(df)),
        "issue_count": len(all_issues),
        "dimensions": {
            "structure_rationality": "pending_full_rules",
            "content_accuracy": "pending_full_rules",
            "synonym_coverage": "pending_full_rules",
            "integrity_and_maintainability": "pending_full_rules",
        },
        "status": "first_round_rules_only",
    }


def evaluate_agent_maintenance_effect(
    before_result: dict[str, object],
    after_result: dict[str, object],
) -> dict[str, object]:
    """Evaluate whether Agent maintenance improved the taxonomy.

    This is intentionally separate from taxonomy quality evaluation. It requires
    before/after diagnosis or version-comparison results.
    """

    return {
        "evaluation_type": "agent_maintenance_effect",
        "before_result_available": bool(before_result),
        "after_result_available": bool(after_result),
        "status": "requires_before_after_metrics",
    }
