"""Calculate explainable health scores for the product taxonomy."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


def evaluate_system(df: pd.DataFrame, issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Return score details from 0 to 100 based on detected issues."""

    total_nodes = max(len(df), 1)
    issue_counts = Counter(issue["issue_type"] for issue in issues)

    structure_penalty = (
        issue_counts["deep_node"] * 2
        + issue_counts["wide_node"] * 5
        + issue_counts["unbalanced_branch"] * 3
        + issue_counts["orphan_node"] * 8
    )
    content_penalty = (
        issue_counts["duplicate_category_name"] * 1
        + issue_counts["duplicate_sibling_name"] * 5
        + issue_counts["same_name_parent_child"] * 5
        + issue_counts["suspicious_parent_child"] * 3
    )
    synonym_penalty = (
        issue_counts["missing_synonyms"] * 1
        + issue_counts["suspicious_synonym"] * 4
    )

    duplicate_nodes = issue_counts["duplicate_category_name"] + issue_counts["duplicate_sibling_name"]
    suspicious_mounts = issue_counts["suspicious_parent_child"]

    structure_score = _bounded_score(100 - structure_penalty / total_nodes * 100)
    content_score = _bounded_score(100 - content_penalty / total_nodes * 100)
    synonym_score = _bounded_score(100 - synonym_penalty / total_nodes * 100)
    redundancy_score = _bounded_score(100 - duplicate_nodes / total_nodes * 100)
    total_score = round(
        structure_score * 0.3
        + content_score * 0.3
        + synonym_score * 0.2
        + redundancy_score * 0.2,
        2,
    )

    return {
        "scores": {
            "structure_score": structure_score,
            "content_score": content_score,
            "synonym_score": synonym_score,
            "redundancy_score": redundancy_score,
            "total_score": total_score,
        },
        "metrics": {
            "total_nodes": len(df),
            "synonym_coverage_rate": round((df["synonyms"].astype(str).str.strip() != "").mean(), 4),
            "redundant_node_ratio": round(duplicate_nodes / total_nodes, 4),
            "suspicious_mount_ratio": round(suspicious_mounts / total_nodes, 4),
            "issue_counts": dict(issue_counts),
        },
        "formulas": {
            "structure_score": "100 - (deep*2 + wide*5 + unbalanced*3 + orphan*8) / total_nodes * 100",
            "content_score": "100 - (global_duplicate*1 + sibling_duplicate*5 + parent_child_same*5 + suspicious_parent_child*3) / total_nodes * 100",
            "synonym_score": "100 - (missing_synonyms*1 + suspicious_synonym*4) / total_nodes * 100",
            "redundancy_score": "100 - duplicate_related_issue_count / total_nodes * 100",
            "total_score": "structure*0.3 + content*0.3 + synonym*0.2 + redundancy*0.2",
        },
    }


def _bounded_score(value: float) -> float:
    """Clamp and round a score into the 0-100 range."""

    return round(max(0, min(100, value)), 2)
