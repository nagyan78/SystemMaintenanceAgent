"""Tests for parent parsing and derived tree fields."""

from __future__ import annotations

import pandas as pd

from src.tree_builder import add_tree_fields, parse_parent_id


def _sample_df() -> pd.DataFrame:
    """Build a small in-memory taxonomy for tree tests."""

    return pd.DataFrame(
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
                "category_id": "2",
                "category_name": "Child A",
                "category_group_id": "1",
                "category_pids": "1",
                "category_group_name": "Root",
                "syn_list": "",
            },
            {
                "category_id": "3",
                "category_name": "Child B",
                "category_group_id": "1",
                "category_pids": "1",
                "category_group_name": "Root",
                "syn_list": "",
            },
            {
                "category_id": "4",
                "category_name": "Grandchild",
                "category_group_id": "1,2",
                "category_pids": "1,2",
                "category_group_name": "Root,Child A",
                "syn_list": "",
            },
        ]
    )


def test_parse_parent_id_for_root_node() -> None:
    """Blank ancestor path means a top-level node has no parent."""

    assert parse_parent_id("") is None


def test_parse_parent_id_for_regular_node() -> None:
    """The direct parent is the final ID in category_group_id."""

    assert parse_parent_id("1,2,3") == "3"


def test_add_tree_fields_depth_and_child_count() -> None:
    """Derived depth and direct child counts should follow ancestor paths."""

    tree_df = add_tree_fields(_sample_df())
    by_id = tree_df.set_index("category_id")

    assert by_id.loc["1", "parent_id"] is None
    assert by_id.loc["4", "parent_id"] == "2"
    assert by_id.loc["1", "depth"] == 1
    assert by_id.loc["4", "depth"] == 3
    assert by_id.loc["1", "child_count"] == 2
    assert by_id.loc["2", "child_count"] == 1
    assert bool(by_id.loc["4", "is_leaf"]) is True

