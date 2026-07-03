"""Tree metrics for the rule-only taxonomy diagnosis flow."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

import pandas as pd


def summarize_taxonomy(df: pd.DataFrame) -> dict[str, Any]:
    """Return dashboard-level metrics derived from enriched tree fields."""

    total_nodes = len(df)
    leaf_mask = df["is_leaf"].astype(bool) if total_nodes else pd.Series(dtype=bool)
    leaf_depths = [
        int(depth)
        for depth in df.loc[leaf_mask, "depth"].tolist()
        if _is_positive_number(depth)
    ]
    non_leaf_degrees = [
        int(degree)
        for degree in df.loc[~leaf_mask, "degree"].tolist()
        if _is_positive_number(degree)
    ]
    subtree_heights = [
        int(height)
        for height in df.get("subtree_height", pd.Series(dtype=int)).tolist()
        if _is_positive_number(height)
    ]
    root_nodes = int(df["is_root"].sum()) if "is_root" in df.columns else 0
    leaf_nodes = int(leaf_mask.sum()) if total_nodes else 0
    leaf_ratio = leaf_nodes / total_nodes if total_nodes else 0.0
    redundant_chain_nodes = int((df.get("single_child_chain_length", 0) >= 3).sum()) if total_nodes else 0

    return {
        "total_nodes": total_nodes,
        "root_nodes": root_nodes,
        "leaf_nodes": leaf_nodes,
        "leaf_ratio": round(leaf_ratio, 4),
        "leaf_ratio_label": _leaf_ratio_label(leaf_ratio),
        "path_redundancy_rate": round(redundant_chain_nodes / total_nodes, 4) if total_nodes else 0,
        "max_depth": max(leaf_depths) if leaf_depths else 0,
        "mean_depth": round(mean(leaf_depths), 2) if leaf_depths else 0,
        "std_depth": round(pstdev(leaf_depths), 2) if len(leaf_depths) > 1 else 0,
        "max_subtree_height": max(subtree_heights) if subtree_heights else 0,
        "mean_subtree_height": round(mean(subtree_heights), 2) if subtree_heights else 0,
        "std_subtree_height": round(pstdev(subtree_heights), 2) if len(subtree_heights) > 1 else 0,
        "max_child_count": max(non_leaf_degrees) if non_leaf_degrees else 0,
        "p95_width": round(_percentile(non_leaf_degrees, 0.95), 2) if non_leaf_degrees else 0,
    }


def child_subtree_entropy(child_sizes: list[int]) -> float:
    """Calculate entropy for child subtree-size distribution."""

    total = sum(size for size in child_sizes if size > 0)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for size in child_sizes:
        if size <= 0:
            continue
        p_i = size / total
        entropy -= p_i * math.log(p_i)
    return round(entropy, 4)


def normalized_child_subtree_entropy(child_sizes: list[int]) -> float:
    """Return entropy normalized by log(child_count), in the 0-1 range."""

    positive_sizes = [size for size in child_sizes if size > 0]
    if len(positive_sizes) <= 1:
        return 1.0
    entropy = child_subtree_entropy(positive_sizes)
    return round(entropy / math.log(len(positive_sizes)), 4)


def sibling_average_degree(df: pd.DataFrame) -> dict[str, float]:
    """Map each node id to the average degree of its siblings."""

    result: dict[str, float] = {}
    groups = defaultdict(list)
    for _, row in df.iterrows():
        groups[str(row.get("parent_id", ""))].append(row)
    for siblings in groups.values():
        if not siblings:
            continue
        average = sum(int(row.get("degree", 0)) for row in siblings) / len(siblings)
        for row in siblings:
            result[str(row.get("category_id", ""))] = average
    return result


def _percentile(values: list[int], percentile: float) -> float:
    """Return a simple linear-interpolated percentile."""

    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[int(rank)])
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _is_positive_number(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _leaf_ratio_label(value: float) -> str:
    if value < 0.3:
        return "叶子节点占比较低，分类层级仍有展开空间，也可能存在中间层过多的问题。"
    if value > 0.8:
        return "叶子节点占比较高，可能存在大量未继续分层的节点。"
    return "叶子节点占比适中，结构相对正常。"

