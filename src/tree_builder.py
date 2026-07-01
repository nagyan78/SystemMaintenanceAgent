"""Build derived tree fields from category ancestor paths."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


PATH_SPLIT_PATTERN = re.compile(r"[,，/|>\s]+")


def parse_parent_id(category_group_id: str) -> str | None:
    """从 category_group_id 中提取直接父节点 ID。

    ``category_group_id`` is an ancestor path from the top node to the current
    node's parent. The direct parent is therefore the final ID in that path. A
    blank path means the node is a top-level category.
    """

    ids = parse_id_path(category_group_id)
    return ids[-1] if ids else None


def add_tree_fields(df: pd.DataFrame) -> pd.DataFrame:
    """添加 parent_id、depth、child_count、is_leaf 等字段。

    The returned DataFrame is a copy. The original input is not modified.
    """

    result = df.copy()
    result["category_id"] = result["category_id"].map(_normalize_id_token)
    result["category_group_id"] = result["category_group_id"].map(_clean_text)
    result["category_name"] = result["category_name"].map(_clean_text)
    result["category_group_name"] = result.get("category_group_name", "").map(_clean_text)

    ancestor_ids = result["category_group_id"].map(parse_id_path)
    result["parent_id"] = pd.Series(
        [ids[-1] if ids else None for ids in ancestor_ids],
        index=result.index,
        dtype=object,
    )
    result["depth"] = ancestor_ids.map(lambda ids: len(ids) + 1)
    result["full_path_ids"] = [
        ids + [category_id] for ids, category_id in zip(ancestor_ids, result["category_id"])
    ]
    result["full_path_names"] = result.apply(_build_full_path_names, axis=1)
    result["path"] = result["full_path_names"].map(lambda names: " > ".join(names))

    child_counts = result["parent_id"].dropna().value_counts()
    result["child_count"] = result["category_id"].map(child_counts).fillna(0).astype(int)
    result["is_leaf"] = result["child_count"] == 0
    return result


def parse_id_path(value: Any) -> list[str]:
    """Split an ancestor ID path into normalized ID tokens."""

    text = _clean_text(value)
    if not text:
        return []
    return [_normalize_id_token(token) for token in PATH_SPLIT_PATTERN.split(text) if token.strip()]


def _build_full_path_names(row: pd.Series) -> list[str]:
    """Build a readable name path from ancestor names plus current node name."""

    ancestor_names = [
        name.strip()
        for name in re.split(r"[,，/|>]+", _clean_text(row.get("category_group_name", "")))
        if name.strip()
    ]
    return ancestor_names + [_clean_text(row.get("category_name", ""))]


def _clean_text(value: Any) -> str:
    """Convert a value to a stripped string and treat null-like values as blank."""

    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _normalize_id_token(value: Any) -> str:
    """Normalize ID tokens that Excel may have represented as numeric values."""

    text = _clean_text(value)
    if text.endswith(".0"):
        head = text[:-2]
        if head.isdigit() or (head.startswith("-") and head[1:].isdigit()):
            return head
    return text
