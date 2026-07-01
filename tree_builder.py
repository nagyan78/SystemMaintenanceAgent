"""Build tree-derived fields such as depth, child count, and full path."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd


ROOT_PARENT_VALUES = {"", "0", "none", "nan", "null", "-1"}


def enrich_tree_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add depth, child_count, parent_name, and path columns to a copy of df."""

    result = df.copy()
    id_to_name = dict(zip(result["category_id"], result["category_name"]))
    id_to_parent = dict(zip(result["category_id"], result["parent_id"]))
    children: dict[str, list[str]] = defaultdict(list)

    for _, row in result.iterrows():
        parent_id = row["parent_id"]
        if not _is_root_parent(parent_id):
            children[parent_id].append(row["category_id"])

    depth_cache: dict[str, int] = {}
    path_cache: dict[str, str] = {}

    def depth_for(node_id: str, visiting: set[str] | None = None) -> int:
        if node_id in depth_cache:
            return depth_cache[node_id]
        visiting = visiting or set()
        if node_id in visiting:
            depth_cache[node_id] = -1
            return -1
        parent_id = id_to_parent.get(node_id, "")
        if _is_root_parent(parent_id) or parent_id not in id_to_parent:
            depth_cache[node_id] = 1
            return 1
        parent_depth = depth_for(parent_id, visiting | {node_id})
        depth_cache[node_id] = parent_depth + 1 if parent_depth > 0 else -1
        return depth_cache[node_id]

    def path_for(node_id: str, visiting: set[str] | None = None) -> str:
        if node_id in path_cache:
            return path_cache[node_id]
        visiting = visiting or set()
        name = id_to_name.get(node_id, "")
        if node_id in visiting:
            return f"[CYCLE] > {name}"
        parent_id = id_to_parent.get(node_id, "")
        if _is_root_parent(parent_id) or parent_id not in id_to_parent:
            path_cache[node_id] = name
        else:
            path_cache[node_id] = f"{path_for(parent_id, visiting | {node_id})} > {name}"
        return path_cache[node_id]

    result["depth"] = result["category_id"].map(depth_for)
    result["child_count"] = result["category_id"].map(lambda node_id: len(children.get(node_id, [])))
    result["parent_name"] = result["parent_id"].map(id_to_name).fillna("")
    result["path"] = result["category_id"].map(path_for)
    return result


def _is_root_parent(parent_id: str) -> bool:
    """Return True when parent_id represents a root/no-parent value."""

    return str(parent_id).strip().lower() in ROOT_PARENT_VALUES
