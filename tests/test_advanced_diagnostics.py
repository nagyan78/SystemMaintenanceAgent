"""Tests for advanced rule diagnostics."""

from __future__ import annotations

import pandas as pd

from src.advanced.diagnostics import run_rule_diagnostics
from src.advanced.tree_builder import enrich_tree_fields


def _chain_rows(length: int) -> list[dict[str, str]]:
    rows = []
    for index in range(1, length + 1):
        rows.append(
            {
                "category_id": f"n{index}",
                "category_name": f"Node {index}",
                "parent_id": "" if index == 1 else f"n{index - 1}",
            }
        )
    return rows


def test_tree_height_uses_leaf_depth_with_minimum_threshold() -> None:
    """A six-level branch should not be flagged just because subtree-height mean is low."""

    df = enrich_tree_fields(pd.DataFrame(_chain_rows(6)))

    issues, _ = run_rule_diagnostics(df)

    assert not [issue for issue in issues if issue["issue_type"] == "deep_node"]


def test_tree_height_flags_abnormally_deep_leaf_path() -> None:
    """A ten-level branch should still be detected as an unusually deep path."""

    df = enrich_tree_fields(pd.DataFrame(_chain_rows(10)))

    issues, _ = run_rule_diagnostics(df)

    deep_issues = [issue for issue in issues if issue["issue_type"] == "deep_node"]
    assert len(deep_issues) == 1
    assert "叶子路径深度" in deep_issues[0]["evidence"]
