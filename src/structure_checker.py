"""基于规则的产品分类树结构问题检查。"""

from __future__ import annotations

import pandas as pd

from .common import DEFAULT_DEPTH_THRESHOLD, DEFAULT_WIDTH_THRESHOLD, IssueResult


def check_missing_parent(df: pd.DataFrame) -> list[IssueResult]:
    """检查父节点缺失问题。

    如果某个节点的 `parent_id` 指向了一个不存在的 `category_id`，说明树的
    祖先路径不完整。这个问题优先级较高，因为它会影响路径展示、层级统计和
    后续维护建议。
    """

    # 先把所有节点 ID 放入集合，后续判断父节点是否存在时就是 O(1) 查询。
    existing_ids = set(df["category_id"].astype(str))
    issues: list[IssueResult] = []

    # 顶层节点的 parent_id 是空值，不需要检查；非空 parent_id 才需要确认
    # 是否能在现有节点集合中找到。
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


def check_depth_too_deep(
    df: pd.DataFrame,
    threshold: int = DEFAULT_DEPTH_THRESHOLD,
) -> list[IssueResult]:
    """检查层级过深问题。

    层级过深通常意味着分类体系不够扁平，用户查找成本较高，也可能存在不必要
    的中间层级。默认阈值来自 `common.py`。
    """

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


def check_width_too_large(
    df: pd.DataFrame,
    threshold: int = DEFAULT_WIDTH_THRESHOLD,
) -> list[IssueResult]:
    """检查节点过宽问题。

    如果一个节点下面直接挂了太多子节点，说明这一层可能缺少中间分组。过宽的
    节点会降低浏览和维护效率。
    """

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
    """汇总所有结构问题。

    规则顺序保持固定，报告输出就会稳定，方便多次运行后对比结果变化。
    """

    return [
        *check_missing_parent(df),
        *check_depth_too_deep(df),
        *check_width_too_large(df),
    ]
