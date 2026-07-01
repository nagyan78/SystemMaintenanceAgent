"""Tests for first-round structural checks."""

from __future__ import annotations

import pandas as pd

from src.structure_checker import check_depth_too_deep, check_width_too_large
from src.tree_builder import add_tree_fields


def test_check_depth_too_deep() -> None:
    """Nodes deeper than the threshold should produce an IssueResult."""

    df = pd.DataFrame(
        [
            {
                "category_id": "1",
                "category_name": "Root",
                "category_group_id": "",
                "category_pids": "",
                "category_group_name": "",
                "syn_list": "",
            },
            {
                "category_id": "9",
                "category_name": "Deep Node",
                "category_group_id": "1,2,3",
                "category_pids": "1,2,3",
                "category_group_name": "Root,L2,L3",
                "syn_list": "",
            },
        ]
    )

    issues = check_depth_too_deep(add_tree_fields(df), threshold=3)

    assert len(issues) == 1
    assert issues[0].issue_type == "depth_too_deep"
    assert "超过阈值 3" in issues[0].reason
    assert issues[0].suggestion


def test_check_width_too_large() -> None:
    """Nodes with too many direct children should produce an IssueResult."""

    rows = [
        {
            "category_id": "1",
            "category_name": "Root",
            "category_group_id": "",
            "category_pids": "",
            "category_group_name": "",
            "syn_list": "",
        }
    ]
    for child_id in ("2", "3", "4"):
        rows.append(
            {
                "category_id": child_id,
                "category_name": f"Child {child_id}",
                "category_group_id": "1",
                "category_pids": "1",
                "category_group_name": "Root",
                "syn_list": "",
            }
        )

    issues = check_width_too_large(add_tree_fields(pd.DataFrame(rows)), threshold=2)

    assert len(issues) == 1
    assert issues[0].issue_type == "width_too_large"
    assert issues[0].node_id == "1"
    assert "直接子节点数为 3" in issues[0].reason
    assert issues[0].suggestion

