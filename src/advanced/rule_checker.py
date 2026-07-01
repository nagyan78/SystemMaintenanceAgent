"""Rule-based checks for product category maintenance."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd

from .tree_builder import ROOT_PARENT_VALUES


Issue = dict[str, Any]
SYNONYM_SPLIT_RE = re.compile(r"[,，、;；|/]+")


def make_issue(
    issue_type: str,
    severity: str,
    row: pd.Series,
    evidence: str,
    suggestion: str,
) -> Issue:
    """Create the unified issue dictionary used by all checks."""

    return {
        "issue_type": issue_type,
        "severity": severity,
        "category_id": str(row.get("category_id", "")),
        "category_name": str(row.get("category_name", "")),
        "path": str(row.get("path", "")),
        "evidence": evidence,
        "suggestion": suggestion,
    }


def detect_deep_nodes(df: pd.DataFrame, max_depth: int = 8) -> list[Issue]:
    """Detect nodes deeper than max_depth."""

    issues = []
    for _, row in df[df["depth"] > max_depth].iterrows():
        issues.append(make_issue(
            "deep_node",
            "medium",
            row,
            f"节点深度为 {row['depth']}，超过阈值 {max_depth}。",
            "建议检查中间层级是否过细，可合并弱区分层级或重新归并路径。",
        ))
    return issues


def detect_wide_nodes(df: pd.DataFrame, max_children: int = 2000) -> list[Issue]:
    """Detect nodes whose direct child count exceeds max_children."""

    issues = []
    for _, row in df[df["child_count"] > max_children].iterrows():
        issues.append(make_issue(
            "wide_node",
            "high",
            row,
            f"直接子节点数为 {row['child_count']}，超过阈值 {max_children}。",
            "建议增加中间分类层级，按材质、用途、规格或业务属性拆分子节点。",
        ))
    return issues


def detect_unbalanced_branches(df: pd.DataFrame) -> list[Issue]:
    """Detect obvious structural imbalance between sibling branches."""

    issues = []
    grouped = df.groupby("parent_id", dropna=False)
    for _, group in grouped:
        if len(group) < 3:
            continue
        max_depth = int(group["depth"].max())
        min_depth = int(group["depth"].min())
        if max_depth - min_depth >= 4:
            parent_id = str(group.iloc[0]["parent_id"])
            parent = df[df["category_id"] == parent_id]
            if not parent.empty:
                row = parent.iloc[0]
                issues.append(make_issue(
                    "unbalanced_branch",
                    "medium",
                    row,
                    f"同一父节点下子分支深度差为 {max_depth - min_depth}。",
                    "建议统一相邻分支的拆分粒度，补充必要中间层或合并过细层级。",
                ))
    return issues


def detect_duplicate_names(df: pd.DataFrame) -> list[Issue]:
    """Detect duplicate names globally and under the same parent."""

    issues: list[Issue] = []
    name_counts = Counter(df["category_name"].str.strip())
    for _, row in df.iterrows():
        name = row["category_name"].strip()
        if name and name_counts[name] > 1:
            issues.append(make_issue(
                "duplicate_category_name",
                "medium",
                row,
                f"节点名称“{name}”在全局出现 {name_counts[name]} 次。",
                "建议确认是否为重复节点；如业务含义不同，应补充限定词。",
            ))

    duplicated_sibling_mask = df.duplicated(["parent_id", "category_name"], keep=False)
    for _, row in df[duplicated_sibling_mask].iterrows():
        issues.append(make_issue(
            "duplicate_sibling_name",
            "high",
            row,
            "同一父节点下存在相同 category_name。",
            "建议合并同父重复节点，或用规格、用途等限定词区分。",
        ))
    return issues


def detect_same_name_parent_child(df: pd.DataFrame) -> list[Issue]:
    """Detect nodes whose name is the same as their parent's name."""

    issues = []
    for _, row in df.iterrows():
        parent_name = str(row.get("parent_name", "")).strip()
        if parent_name and parent_name == str(row["category_name"]).strip():
            issues.append(make_issue(
                "same_name_parent_child",
                "high",
                row,
                f"父节点和子节点名称均为“{parent_name}”。",
                "建议删除冗余层级，或重新命名子节点以体现细分含义。",
            ))
    return issues


def detect_missing_synonyms(df: pd.DataFrame) -> list[Issue]:
    """Detect nodes with empty synonym fields."""

    issues = []
    mask = df["synonyms"].fillna("").astype(str).str.strip() == ""
    for _, row in df[mask].iterrows():
        issues.append(make_issue(
            "missing_synonyms",
            "low",
            row,
            "synonyms 字段为空。",
            "建议补充常见别名、简称、行业俗称或中英文名称。",
        ))
    return issues


def detect_suspicious_synonyms_by_rule(df: pd.DataFrame) -> list[Issue]:
    """Detect suspicious synonyms with lightweight string rules."""

    issues = []
    for _, row in df.iterrows():
        name = str(row["category_name"]).strip()
        for synonym in split_synonyms(row.get("synonyms", "")):
            if not synonym:
                continue
            if synonym == name:
                issues.append(make_issue(
                    "suspicious_synonym",
                    "low",
                    row,
                    f"同义词“{synonym}”与标准名称完全相同。",
                    "建议删除无信息增益的同义词，保留真正别名。",
                ))
            elif len(synonym) <= 1 or len(synonym) > 40:
                issues.append(make_issue(
                    "suspicious_synonym",
                    "medium",
                    row,
                    f"同义词“{synonym}”长度异常。",
                    "建议核对该同义词是否为截断、拼接错误或描述性文本。",
                ))
    return issues


def detect_suspicious_parent_child_by_rule(df: pd.DataFrame) -> list[Issue]:
    """Screen parent-child relations that may need LLM semantic judgement."""

    issues = []
    for _, row in df.iterrows():
        parent_name = str(row.get("parent_name", "")).strip()
        name = str(row.get("category_name", "")).strip()
        if not parent_name or not name:
            continue
        if _looks_semantically_far(parent_name, name):
            issues.append(make_issue(
                "suspicious_parent_child",
                "medium",
                row,
                f"父类“{parent_name}”与子类“{name}”缺少明显词面关联。",
                "建议调用 LLM 或人工复核该节点是否挂载到更合适的父类下。",
            ))
    return issues


def detect_orphan_nodes(df: pd.DataFrame) -> list[Issue]:
    """Detect nodes whose parent_id is not empty but cannot be found."""

    ids = set(df["category_id"])
    issues = []
    for _, row in df.iterrows():
        parent_id = str(row["parent_id"]).strip()
        if parent_id.lower() not in ROOT_PARENT_VALUES and parent_id not in ids:
            issues.append(make_issue(
                "orphan_node",
                "high",
                row,
                f"parent_id={parent_id} 在数据中不存在。",
                "建议修正 parent_id，或补充缺失父节点。",
            ))
    return issues


def split_synonyms(value: str) -> list[str]:
    """Split the synonyms field using common Chinese and English delimiters."""

    return [part.strip() for part in SYNONYM_SPLIT_RE.split(str(value)) if part.strip()]


def _looks_semantically_far(parent_name: str, child_name: str) -> bool:
    """Very small prefilter for relationships worth LLM review."""

    if parent_name in child_name or child_name in parent_name:
        return False
    parent_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", parent_name.lower()))
    child_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", child_name.lower()))
    return bool(parent_tokens and child_tokens and parent_tokens.isdisjoint(child_tokens))
