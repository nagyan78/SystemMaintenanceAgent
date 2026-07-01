"""Summaries and aggregate statistics for taxonomy trees."""

from __future__ import annotations

import pandas as pd


def summarize_tree(df: pd.DataFrame) -> dict[str, int]:
    """输出树结构统计信息。"""

    if df.empty:
        return {
            "total_nodes": 0,
            "root_nodes": 0,
            "leaf_nodes": 0,
            "max_depth": 0,
            "max_child_count": 0,
        }

    return {
        "total_nodes": int(len(df)),
        "root_nodes": int(df["parent_id"].isna().sum()),
        "leaf_nodes": int(df["is_leaf"].sum()),
        "max_depth": int(df["depth"].max()),
        "max_child_count": int(df["child_count"].max()),
    }


def compute_depth_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """统计深度分布。"""

    return (
        df.groupby("depth", dropna=False)
        .size()
        .reset_index(name="node_count")
        .sort_values("depth")
        .reset_index(drop=True)
    )


def get_top_wide_nodes(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """返回直接子节点最多的节点。"""

    columns = ["category_id", "category_name", "path", "depth", "child_count"]
    return (
        df.loc[:, columns]
        .sort_values(["child_count", "category_id"], ascending=[False, True])
        .head(top_n)
        .reset_index(drop=True)
    )

