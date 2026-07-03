"""Build tree-derived fields such as depth, degree, subtree size, and path."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


ROOT_PARENT_VALUES = {"", "0", "none", "nan", "null", "-1"}


def enrich_tree_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add structural fields to a copy of df without mutating source data."""

    result = df.copy()
    result["category_id"] = result["category_id"].map(_clean_id)
    result["parent_id"] = result["parent_id"].map(_clean_id)
    result["category_name"] = result["category_name"].fillna("").astype(str).str.strip()

    id_to_name = dict(zip(result["category_id"], result["category_name"]))
    id_to_parent = dict(zip(result["category_id"], result["parent_id"]))
    children: dict[str, list[str]] = defaultdict(list)

    for _, row in result.iterrows():
        parent_id = str(row["parent_id"])
        if not _is_root_parent(parent_id) and parent_id in id_to_parent:
            children[parent_id].append(str(row["category_id"]))

    cycle_nodes = _detect_cycle_nodes(id_to_parent)
    roots = [
        node_id
        for node_id, parent_id in id_to_parent.items()
        if _is_root_parent(parent_id)
    ]
    reachable = _reachable_nodes(roots, children)
    depth_cache: dict[str, int] = {}
    path_cache: dict[str, str] = {}
    subtree_cache: dict[str, int] = {}
    subtree_height_cache: dict[str, int] = {}
    single_child_cache: dict[str, int] = {}

    def depth_for(node_id: str, visiting: set[str] | None = None) -> int:
        if node_id in depth_cache:
            return depth_cache[node_id]
        visiting = visiting or set()
        if node_id in visiting or node_id in cycle_nodes:
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
        if node_id in visiting or node_id in cycle_nodes:
            path_cache[node_id] = f"[CYCLE] > {name}"
            return path_cache[node_id]
        parent_id = id_to_parent.get(node_id, "")
        if _is_root_parent(parent_id) or parent_id not in id_to_parent:
            path_cache[node_id] = name
        else:
            path_cache[node_id] = f"{path_for(parent_id, visiting | {node_id})} > {name}"
        return path_cache[node_id]

    def subtree_size_for(node_id: str, visiting: set[str] | None = None) -> int:
        if node_id in subtree_cache:
            return subtree_cache[node_id]
        visiting = visiting or set()
        if node_id in visiting:
            return 1
        total = 1
        for child_id in children.get(node_id, []):
            total += subtree_size_for(child_id, visiting | {node_id})
        subtree_cache[node_id] = total
        return total

    def subtree_height_for(node_id: str, visiting: set[str] | None = None) -> int:
        if node_id in subtree_height_cache:
            return subtree_height_cache[node_id]
        visiting = visiting or set()
        if node_id in visiting or node_id in cycle_nodes:
            subtree_height_cache[node_id] = 0
            return 0
        child_heights = [
            subtree_height_for(child_id, visiting | {node_id})
            for child_id in children.get(node_id, [])
        ]
        subtree_height_cache[node_id] = 1 + (max(child_heights) if child_heights else 0)
        return subtree_height_cache[node_id]

    def single_child_chain_for(node_id: str, visiting: set[str] | None = None) -> int:
        if node_id in single_child_cache:
            return single_child_cache[node_id]
        visiting = visiting or set()
        if node_id in visiting or node_id in cycle_nodes:
            single_child_cache[node_id] = 0
            return 0
        parent_id = id_to_parent.get(node_id, "")
        parent_chain = (
            single_child_chain_for(parent_id, visiting | {node_id})
            if parent_id in id_to_parent
            else 0
        )
        own_degree = len(children.get(node_id, []))
        single_child_cache[node_id] = parent_chain + 1 if own_degree == 1 else 0
        return single_child_cache[node_id]

    result["depth"] = result["category_id"].map(depth_for)
    result["degree"] = result["category_id"].map(lambda node_id: len(children.get(node_id, []))).astype(int)
    result["child_count"] = result["degree"]
    result["subtree_size"] = result["category_id"].map(subtree_size_for).astype(int)
    result["subtree_height"] = result["category_id"].map(subtree_height_for).astype(int)
    result["is_leaf"] = result["degree"] == 0
    result["is_root"] = result["parent_id"].map(_is_root_parent)
    result["is_reachable"] = result["category_id"].map(lambda node_id: node_id in reachable)
    result["has_cycle"] = result["category_id"].map(lambda node_id: node_id in cycle_nodes)
    result["single_child_chain_length"] = result["category_id"].map(single_child_chain_for).astype(int)
    result["parent_name"] = result["parent_id"].map(id_to_name).fillna("")
    result["path"] = result["category_id"].map(path_for)
    return result


def _is_root_parent(parent_id: str) -> bool:
    """Return True when parent_id represents a root/no-parent value."""

    return str(parent_id).strip().lower() in ROOT_PARENT_VALUES


def _clean_id(value: Any) -> str:
    """Normalize IDs read from Excel while preserving string identifiers."""

    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    if text.endswith(".0"):
        head = text[:-2]
        if head.isdigit() or (head.startswith("-") and head[1:].isdigit()):
            return head
    return text


def _detect_cycle_nodes(id_to_parent: dict[str, str]) -> set[str]:
    """Detect nodes participating in parent-chain cycles."""

    cycle_nodes: set[str] = set()
    for start in id_to_parent:
        path: list[str] = []
        index_by_node: dict[str, int] = {}
        current = start
        while current in id_to_parent and not _is_root_parent(id_to_parent[current]):
            if current in index_by_node:
                cycle_nodes.update(path[index_by_node[current]:])
                break
            if current in cycle_nodes:
                break
            index_by_node[current] = len(path)
            path.append(current)
            parent = id_to_parent[current]
            if parent not in id_to_parent:
                break
            current = parent
    return cycle_nodes


def _reachable_nodes(roots: list[str], children: dict[str, list[str]]) -> set[str]:
    """Return nodes reachable from valid roots."""

    reachable: set[str] = set()
    stack = list(roots)
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        stack.extend(children.get(node_id, []))
    return reachable
