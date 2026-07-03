"""Tests for Markdown and HTML report generation."""

from __future__ import annotations

from src.common import IssueResult
from src.report_generator import generate_html_dashboard


def test_generate_html_dashboard_contains_summary_score_and_issue() -> None:
    """The HTML dashboard should render summary cards, health score, and issue rows."""

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
        health_score=88,
    )

    assert "<!doctype html>" in html
    assert "标准产品体系诊断看板" in html
    assert "体系健康分" in html
    assert "88.0 / 100" in html
    assert "节点过宽" in html
    assert "applyFilters" in html


def test_html_dashboard_ai_result_uses_semantic_fields() -> None:
    """AI result area should render semantic judgement fields separately from rule evidence."""

    issue = {
        "issue_type": "suspicious_name_redundancy",
        "node_id": "c1",
        "node_name": "Single Mode Optical Module",
        "path": "Optical Module > Single Mode Optical Module",
        "severity": "low",
        "evidence": "RULE_EVIDENCE_PARENT_NAME_CONTAINED",
        "suggestion": "RULE_SUGGESTION_MERGE_LEVEL",
        "ai_dependency": "high",
        "ai_judgement": {
            "is_problem": False,
            "confidence": 0.7,
            "relevant_nodes": ["Optical Module", "Single Mode Optical Module"],
            "semantic_relation": "Single Mode Optical Module is a subtype of Optical Module by transmission mode.",
            "reason": "The child name represents a specific valid subtype, not a duplicate level.",
            "suggestion": "Keep the parent-child structure.",
            "result_source": "ai_semantic",
        },
    }

    html = generate_html_dashboard({"total_nodes": 2, "root_nodes": 1}, [issue], health_score=99)

    assert "必要分析节点" in html
    assert "Optical Module、Single Mode Optical Module" in html
    assert "语义关系" in html
    assert "Single Mode Optical Module is a subtype" in html
    assert "AI语义原因" in html
    assert "RULE_EVIDENCE_PARENT_NAME_CONTAINED" in html
    assert "RULE_SUGGESTION_MERGE_LEVEL" not in html
