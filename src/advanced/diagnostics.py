"""Pure rule-based taxonomy diagnostics."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from .metrics import (
    child_subtree_entropy,
    normalized_child_subtree_entropy,
    sibling_average_degree,
    summarize_taxonomy,
)
from .rule_checker import split_synonyms
from .tree_builder import ROOT_PARENT_VALUES


Issue = dict[str, Any]


def run_rule_diagnostics(df: pd.DataFrame) -> tuple[list[Issue], dict[str, Any]]:
    """Run all non-AI diagnosis rules and return issues plus summary metrics."""

    summary = summarize_taxonomy(df)
    issues: list[Issue] = []
    issues.extend(_detect_parent_missing_and_orphan(df))
    issues.extend(_detect_cycles(df))
    issues.extend(_detect_tree_height(df, summary))
    issues.extend(_detect_redundant_paths(df))
    issues.extend(_detect_width(df, summary))
    issues.extend(_detect_balance(df))
    issues.extend(_detect_leaf_ratio(df, summary))
    issues.extend(_detect_suspicious_parent_child(df))
    issues.extend(_detect_duplicate_names(df))
    issues.extend(_detect_synonyms(df))
    return _dedupe_issues(issues), summary


def calculate_health_score(issues: list[Issue]) -> int:
    """Calculate a 0-100 health score from issue severity."""

    penalty_by_severity = {"high": 5, "medium": 2, "low": 1}
    penalty = sum(
        penalty_by_severity.get(str(issue.get("severity")), 1)
        for issue in issues
        if not issue.get("is_candidate")
    )
    return max(0, 100 - penalty)


def make_issue(
    issue_type: str,
    severity: str,
    row: pd.Series | dict[str, Any],
    evidence: str,
    suggestion: str,
    need_manual_check: bool | None = None,
    *,
    ai_dependency: str | None = None,
    is_candidate: bool = False,
) -> Issue:
    """Create the structured issue format used by HTML/JSON/Markdown outputs."""

    if need_manual_check is None:
        need_manual_check = severity != "low" or is_candidate
    node_id = str(row.get("category_id", row.get("node_id", "")))
    node_name = str(row.get("category_name", row.get("node_name", "")))
    return {
        "issue_type": issue_type,
        "node_id": node_id,
        "node_name": node_name,
        "category_id": node_id,
        "category_name": node_name,
        "path": str(row.get("path", node_name)),
        "severity": severity,
        "evidence": evidence,
        "reason": evidence,
        "suggestion": suggestion,
        "ai_dependency": ai_dependency or _ai_dependency_for_issue(issue_type),
        "need_manual_check": bool(need_manual_check),
        "need_manual_review": bool(need_manual_check),
        "is_candidate": bool(is_candidate),
    }


def _detect_tree_height(df: pd.DataFrame, summary: dict[str, Any]) -> list[Issue]:
    """Detect abnormal root-to-leaf path depth using mean + 2 sigma."""

    issues: list[Issue] = []
    min_deep_path_depth = 8
    statistical_threshold = float(summary["mean_depth"]) + 2 * float(summary["std_depth"])
    threshold = min_deep_path_depth if float(summary["std_depth"]) == 0 else max(min_deep_path_depth, statistical_threshold)
    if threshold <= 0 or "is_leaf" not in df.columns:
        return issues
    candidates = df[(df["is_leaf"].astype(bool)) & (df["depth"] > threshold)]
    for _, row in candidates.iterrows():
        depth = int(row["depth"])
        severity = "high" if depth >= threshold + 2 else "medium"
        issues.append(make_issue(
            "deep_node",
            severity,
            row,
            (
                f"该叶子路径深度为 {depth}，超过判定阈值 {threshold:.2f}。"
                f"阈值取 max(最低深度 {min_deep_path_depth}, "
                f"叶子平均深度 {summary['mean_depth']} + 2 倍标准差 {summary['std_depth']})。"
            ),
            "解决思路：检查该深路径中是否存在只起过渡作用的中间层；保留有明确业务语义的层级，合并无独立含义的连续单子节点层级。",
            ai_dependency="low",
        ))
    return issues


def _detect_redundant_paths(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    for _, row in df.iterrows():
        chain_length = int(row.get("single_child_chain_length", 0))
        if chain_length >= 3:
            depth = max(1, int(row.get("depth", 1)))
            redundancy_rate = chain_length / depth
            issues.append(make_issue(
                "redundant_single_child_chain",
                "low",
                row,
                (
                    f"路径中存在连续 {chain_length} 层节点都只有 1 个直接子节点，"
                    f"当前路径冗余率约为 {redundancy_rate:.2%}。"
                ),
                "解决思路：优先检查连续单子节点链条中的中间层是否有独立分类价值；没有独立语义的层级可合并到上级或下级。",
                False,
                ai_dependency="high",
                is_candidate=True,
            ))

        parent_name = str(row.get("parent_name", "")).strip()
        name = str(row.get("category_name", "")).strip()
        if not parent_name or not name:
            continue
        if parent_name == name:
            issues.append(make_issue(
                "same_name_parent_child",
                "medium",
                row,
                f"父节点和子节点名称完全相同：{name}。",
                "建议删除冗余层级，或重新命名子节点以体现细分含义。",
            ))
        elif parent_name in name or name in parent_name:
            issues.append(make_issue(
                "suspicious_name_redundancy",
                "low",
                row,
                f"父节点名称“{parent_name}”与子节点名称“{name}”存在明显包含关系。",
                "建议人工复核该层级是否只是重复表达，必要时优化命名或合并层级。",
                False,
                ai_dependency="high",
                is_candidate=True,
            ))
    return issues


def _detect_width(df: pd.DataFrame, summary: dict[str, Any]) -> list[Issue]:
    """Detect width issues with relative branch explosion ratio."""

    issues: list[Issue] = []
    sibling_avg = sibling_average_degree(df)
    for _, row in df[~df["is_leaf"]].iterrows():
        degree = int(row.get("degree", 0))
        avg = sibling_avg.get(str(row["category_id"]), 0)
        branch_ratio = degree / avg if avg else 0
        evidence_parts: list[str] = []
        issue_type = ""
        severity = "low"
        is_candidate = False

        if branch_ratio > 5:
            issue_type = "branch_explosion"
            severity = "medium"
            evidence_parts.append(f"相对分支爆炸比为 {branch_ratio:.2f}，明显高于同级节点平均宽度")
        elif branch_ratio >= 2:
            issue_type = issue_type or "branch_wide"
            evidence_parts.append(f"相对分支爆炸比为 {branch_ratio:.2f}，高于同级节点平均宽度")

        if issue_type:
            issues.append(make_issue(
                issue_type,
                severity,
                row,
                "；".join(evidence_parts) + "。",
                "解决思路：检查该节点下是否直接挂载了过多并列子类；可按用途、材质、规格、产品形态或业务属性增加中间分组。",
                ai_dependency="low",
                is_candidate=is_candidate,
            ))
    return issues


def _detect_balance(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    by_parent: dict[str, list[pd.Series]] = {}
    for _, row in df.iterrows():
        by_parent.setdefault(str(row.get("parent_id", "")), []).append(row)

    by_id = {str(row["category_id"]): row for _, row in df.iterrows()}
    for parent_id, children in by_parent.items():
        if parent_id.strip().lower() in ROOT_PARENT_VALUES or parent_id not in by_id or len(children) < 2:
            continue
        sizes = [max(1, int(child.get("subtree_size", 1))) for child in children]
        min_size = min(sizes)
        max_size = max(sizes)
        if min_size <= 0:
            continue
        balance_ratio = max_size / min_size
        normalized_entropy = normalized_child_subtree_entropy(sizes)
        if balance_ratio < 5 and normalized_entropy >= 0.5:
            continue

        if balance_ratio > 20 or normalized_entropy < 0.5:
            severity = "high"
            balance_label = "严重不均衡" if balance_ratio > 20 else "明显不均衡"
        else:
            severity = "medium"
            balance_label = "不均衡"

        parent = by_id[parent_id]
        issues.append(make_issue(
            "unbalanced_branch",
            severity,
            parent,
            (
                f"直接子分支规模差异较大：最大分支包含 {max_size} 个节点，"
                f"最小分支包含 {min_size} 个节点；最大/最小规模比为 {balance_ratio:.2f}，"
                f"分支规模信息熵为 {child_subtree_entropy(sizes)}，"
                f"标准化信息熵为 {normalized_entropy:.2f}，判断为{balance_label}。"
            ),
            "解决思路：统一同一父节点下相邻分支的拆分粒度；对过大的分支补充中间层，对过细或过小的分支考虑合并。",
            ai_dependency="low",
        ))
    return issues


def _detect_leaf_ratio(df: pd.DataFrame, summary: dict[str, Any]) -> list[Issue]:
    ratio = float(summary.get("leaf_ratio", 0) or 0)
    if 0.3 <= ratio <= 0.8 or not len(df):
        return []
    high_leaf_ratio = ratio > 0.8
    row = {
        "category_id": "GLOBAL",
        "category_name": "整体结构粒度",
        "path": "整体结构粒度",
    }
    return [make_issue(
        "leaf_ratio_abnormal",
        "low",
        row,
        f"整棵树叶子节点占比为 {ratio:.2%}。{summary.get('leaf_ratio_label', '')}",
        (
            "解决思路：抽查叶子节点较多的分支，判断是否还有稳定的下级分类维度，如用途、规格、材质、场景或型号。"
            if high_leaf_ratio
            else "解决思路：检查是否存在中间层过多、分类粒度过细或大量节点未沉到底层的问题。"
        ),
        False,
        ai_dependency="low",
        is_candidate=True,
    )]


def _detect_duplicate_names(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    names = df["category_name"].fillna("").astype(str).str.strip()
    name_counts = Counter(name for name in names if name)
    for _, row in df.iterrows():
        name = str(row.get("category_name", "")).strip()
        if name and name_counts[name] > 1:
            issues.append(make_issue(
                "duplicate_category_name",
                "medium",
                row,
                f"节点名称“{name}”在全局出现 {name_counts[name]} 次。",
                "建议确认是否为重复节点；如业务含义不同，应补充限定词。",
                ai_dependency="medium",
            ))
    return issues


def _detect_suspicious_parent_child(df: pd.DataFrame) -> list[Issue]:
    """Screen a small set of parent-child pairs for semantic AI review."""

    issues: list[Issue] = []
    for _, row in df.iterrows():
        parent_name = str(row.get("parent_name", "")).strip()
        child_name = str(row.get("category_name", "")).strip()
        if not parent_name or not child_name:
            continue
        if parent_name == child_name or parent_name in child_name or child_name in parent_name:
            continue
        if len(parent_name) < 2 or len(child_name) < 2:
            continue
        issues.append(make_issue(
            "suspicious_parent_child",
            "low",
            row,
            f"父类“{parent_name}”与子类“{child_name}”缺少明显词面关联，建议进行语义复核。",
            "建议使用 AI 或人工判断该子类是否挂载在合适父类下。",
            False,
            ai_dependency="high",
            is_candidate=True,
        ))
    return issues


def _detect_parent_missing_and_orphan(df: pd.DataFrame) -> list[Issue]:
    ids = set(df["category_id"].astype(str))
    issues: list[Issue] = []
    for _, row in df.iterrows():
        parent_id = str(row.get("parent_id", "")).strip()
        if parent_id.lower() not in ROOT_PARENT_VALUES and parent_id not in ids:
            issues.append(make_issue(
                "missing_parent",
                "high",
                row,
                f"parent_id={parent_id} 在数据中不存在。",
                "建议修正 parent_id，或补充缺失的父节点。",
                ai_dependency="low",
            ))
        if not bool(row.get("is_reachable", False)):
            issues.append(make_issue(
                "orphan_node",
                "high",
                row,
                "该节点无法从任何有效根节点访问。",
                "建议检查父子关系链路，确保节点可以连接到空 parent_id 的根节点。",
                ai_dependency="low",
            ))
    return issues


def _detect_cycles(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    for _, row in df[df["has_cycle"]].iterrows():
        issues.append(make_issue(
            "cycle_parent_child",
            "high",
            row,
            "该节点所在父子链路存在循环引用。",
            "建议修正 parent_id，确保分类树为无环结构。",
            ai_dependency="low",
        ))
    return issues


def _detect_synonyms(df: pd.DataFrame) -> list[Issue]:
    if "synonyms" not in df.columns:
        return []
    issues: list[Issue] = []
    for _, row in df.iterrows():
        name = str(row.get("category_name", "")).strip()
        synonyms = split_synonyms(str(row.get("synonyms", "")))
        if not synonyms:
            continue
        counts = Counter(synonyms)
        duplicates = sorted(synonym for synonym, count in counts.items() if count > 1)
        if duplicates:
            issues.append(make_issue(
                "duplicate_synonym",
                "low",
                row,
                f"同义词存在重复项：{', '.join(duplicates)}。",
                "建议删除重复同义词，保持同义词列表简洁。",
                False,
                ai_dependency="low",
            ))
        if name and name in counts:
            issues.append(make_issue(
                "suspicious_synonym",
                "low",
                row,
                f"同义词“{name}”与标准名称完全相同。",
                "建议删除无信息增益的同义词；如需判断别名语义，可接入模型辅助。",
                False,
                ai_dependency="medium",
            ))
    return issues


def _dedupe_issues(issues: list[Issue]) -> list[Issue]:
    seen: set[tuple[str, str, str]] = set()
    result: list[Issue] = []
    for issue in issues:
        key = (
            str(issue.get("issue_type", "")),
            str(issue.get("node_id", "")),
            str(issue.get("evidence", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _ai_dependency_for_issue(issue_type: str) -> str:
    """Return how much AI assistance is useful for judging this issue."""

    high_dependency = {
        "suspicious_name_redundancy",
        "suspicious_parent_child",
    }
    medium_dependency = {
        "duplicate_category_name",
        "same_name_parent_child",
        "suspicious_synonym",
    }
    if issue_type in high_dependency:
        return "high"
    if issue_type in medium_dependency:
        return "medium"
    return "low"


def _detect_leaf_ratio(df: pd.DataFrame, summary: dict[str, Any]) -> list[Issue]:
    """Detect leaf-heavy branches that need semantic model review."""

    issues: list[Issue] = []
    total_ratio = float(summary.get("leaf_ratio", 0) or 0)
    if not len(df):
        return issues

    for _, row in df[~df["is_leaf"].astype(bool)].iterrows():
        node_id = str(row.get("category_id", ""))
        children = df[df["parent_id"].astype(str) == node_id]
        if len(children) < 5:
            continue
        child_leaf_ratio = float(children["is_leaf"].astype(bool).sum()) / len(children)
        if child_leaf_ratio <= 0.8:
            continue
        issues.append(make_issue(
            "leaf_ratio_abnormal",
            "low",
            row,
            (
                f"该分支直接子节点中的叶子节点占比为 {child_leaf_ratio:.2%}，"
                f"共有 {len(children)} 个直接子节点，可能存在可继续细分的类别。"
            ),
            "建议接入 model 判断该分支下的叶子节点是否存在稳定的下级分类维度，如用途、规格、材质、场景或型号。",
            False,
            ai_dependency="high",
            is_candidate=True,
        ))

    if issues or 0.3 <= total_ratio <= 0.8:
        return issues

    row = {
        "category_id": "GLOBAL",
        "category_name": "整体叶子节点占比",
        "path": "整体叶子节点占比",
    }
    issues.append(make_issue(
        "leaf_ratio_abnormal",
        "low",
        row,
        f"整棵树叶子节点占比为 {total_ratio:.2%}。{summary.get('leaf_ratio_label', '')}",
        "建议接入 model 判断叶子节点较多的分支是否存在可以继续细分的语义类别。",
        False,
        ai_dependency="high" if total_ratio > 0.8 else "low",
        is_candidate=True,
    ))
    return issues
