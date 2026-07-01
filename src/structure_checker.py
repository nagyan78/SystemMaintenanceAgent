"""Rule-based structural issue checks for taxonomy trees."""

from __future__ import annotations

import pandas as pd

from .config import DEFAULT_DEPTH_THRESHOLD, DEFAULT_WIDTH_THRESHOLD
from .models import IssueResult


def check_missing_parent(df: pd.DataFrame) -> list[IssueResult]:
    """检测父节点缺失。"""

    existing_ids = set(df["category_id"].astype(str))
    issues: list[IssueResult] = []
    for row in df[df["parent_id"].notna()].itertuples(index=False):
        parent_id = str(row.parent_id)
        if parent_id not in existing_ids:
            issues.append(
                IssueResult(
                    issue_type="missing_parent",
                    node_id=str(row.category_id),
                    node_name=str(row.category_name),
                    path=str(row.path),
                    severity="high",
                    reason=f"父节点 ID {parent_id} 出现在祖先路径中，但数据中不存在该节点。",
                    suggestion="核对祖先路径是否填写错误，或补齐缺失的父节点记录。",
                    confidence=1.0,
                    need_manual_review=True,
                )
            )
    return issues


def check_depth_too_deep(df: pd.DataFrame, threshold: int = DEFAULT_DEPTH_THRESHOLD) -> list[IssueResult]:
    """检测层级过深。"""

    issues: list[IssueResult] = []
    for row in df[df["depth"] > threshold].itertuples(index=False):
        issues.append(
            IssueResult(
                issue_type="depth_too_deep",
                node_id=str(row.category_id),
                node_name=str(row.category_name),
                path=str(row.path),
                severity="medium",
                reason=f"当前节点深度为 {int(row.depth)}，超过阈值 {threshold}。",
                suggestion="检查该分支是否存在不必要的中间层级，可考虑合并或压缩层级。",
                confidence=1.0,
                need_manual_review=True,
            )
        )
    return issues


def check_width_too_large(df: pd.DataFrame, threshold: int = DEFAULT_WIDTH_THRESHOLD) -> list[IssueResult]:
    """检测节点过宽。"""

    issues: list[IssueResult] = []
    for row in df[df["child_count"] > threshold].itertuples(index=False):
        issues.append(
            IssueResult(
                issue_type="width_too_large",
                node_id=str(row.category_id),
                node_name=str(row.category_name),
                path=str(row.path),
                severity="medium",
                reason=f"当前节点直接子节点数为 {int(row.child_count)}，超过阈值 {threshold}。",
                suggestion="检查子节点是否可按用途、材质、行业或规格等维度拆分为更均衡的下级分组。",
                confidence=1.0,
                need_manual_review=True,
            )
        )
    return issues


def check_structure_issues(df: pd.DataFrame) -> list[IssueResult]:
    """汇总所有结构问题。"""

    return [
        *check_missing_parent(df),
        *check_depth_too_deep(df),
        *check_width_too_large(df),
    ]

