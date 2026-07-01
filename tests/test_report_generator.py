"""Tests for Markdown and HTML report generation."""

from __future__ import annotations

from src.common import IssueResult
from src.report_generator import generate_html_dashboard


def test_generate_html_dashboard_contains_summary_and_issue() -> None:
    """The HTML dashboard should render summary cards and issue rows."""

    issue = IssueResult(
        issue_type="width_too_large",
        node_id="1",
        node_name="Root",
        path="Root",
        severity="medium",
        reason="当前节点直接子节点数为 3，超过阈值 2。",
        suggestion="检查子节点是否可拆分为更均衡的下级分组。",
        confidence=1.0,
        need_manual_review=True,
    )

    html = generate_html_dashboard(
        {
            "total_nodes": 4,
            "root_nodes": 1,
            "leaf_nodes": 3,
            "max_depth": 2,
            "max_child_count": 3,
        },
        [issue],
    )

    assert "<!doctype html>" in html
    assert "标准产品体系结构诊断看板" in html
    assert "总节点数" in html
    assert "width_too_large" in html
    assert "applyFilters" in html
