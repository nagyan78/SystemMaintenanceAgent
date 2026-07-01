"""根据产品分类的祖先路径生成树结构辅助字段。"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


# 祖先路径可能用英文逗号、中文逗号、竖线、> 或空白分隔，这里统一兼容。
PATH_SPLIT_PATTERN = re.compile(r"[,，|>\s]+")


def parse_parent_id(category_group_id: str) -> str | None:
    """从 `category_group_id` 中提取直接父节点 ID。

    `category_group_id` 表示从顶层节点到当前节点父节点的祖先路径，所以路径
    中最后一个 ID 就是当前节点的直接父节点。空路径表示当前节点是顶层分类。
    """

    ids = parse_id_path(category_group_id)
    return ids[-1] if ids else None


def add_tree_fields(df: pd.DataFrame) -> pd.DataFrame:
    """添加树结构诊断需要的派生字段。

    新增字段包括：
    - `parent_id`：直接父节点 ID
    - `depth`：当前节点深度，顶层节点为 1
    - `full_path_ids`：从根节点到当前节点的完整 ID 路径
    - `full_path_names`：从根节点到当前节点的完整名称路径
    - `path`：用于报告展示的人类可读路径
    - `child_count`：当前节点的直接子节点数量
    - `is_leaf`：是否为叶子节点

    函数会返回新的 DataFrame，不会修改传入的原始数据。
    """

    result = df.copy()

    # 先清洗核心字段，确保后面拼路径和统计子节点时不会受到空格、nan 字符串
    # 或 Excel 数字 ID 的影响。
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

    # 深度 = 祖先数量 + 当前节点本身。顶层节点没有祖先，所以深度为 1。
    result["depth"] = ancestor_ids.map(lambda ids: len(ids) + 1)
    result["full_path_ids"] = [
        ids + [category_id] for ids, category_id in zip(ancestor_ids, result["category_id"])
    ]
    result["full_path_names"] = result.apply(_build_full_path_names, axis=1)
    result["path"] = result["full_path_names"].map(lambda names: " > ".join(names))

    # 直接子节点数量通过统计 parent_id 得到：某个 ID 被多少节点引用为父节点，
    # 它就有多少个直接子节点。
    child_counts = result["parent_id"].dropna().value_counts()
    result["child_count"] = result["category_id"].map(child_counts).fillna(0).astype(int)
    result["is_leaf"] = result["child_count"] == 0
    return result


def parse_id_path(value: Any) -> list[str]:
    """把祖先 ID 路径拆成规范化后的 ID 列表。"""

    text = _clean_text(value)
    if not text:
        return []
    return [_normalize_id_token(token) for token in PATH_SPLIT_PATTERN.split(text) if token.strip()]


def _build_full_path_names(row: pd.Series) -> list[str]:
    """用祖先名称和当前节点名称拼出完整名称路径。"""

    ancestor_names = [
        name.strip()
        for name in re.split(r"[,，|>]+", _clean_text(row.get("category_group_name", "")))
        if name.strip()
    ]
    return ancestor_names + [_clean_text(row.get("category_name", ""))]


def _clean_text(value: Any) -> str:
    """把任意值转成干净文本，并把 null/nan/none 视为空字符串。"""

    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _normalize_id_token(value: Any) -> str:
    """规范单个 ID，修复 Excel 可能生成的 `1.0` 形式。"""

    text = _clean_text(value)
    if text.endswith(".0"):
        head = text[:-2]
        if head.isdigit() or (head.startswith("-") and head[1:].isdigit()):
            return head
    return text
