"""Tests for advanced Markdown report writing."""

from __future__ import annotations

from src.advanced.report_writer import _build_markdown


def test_evaluation_scores_and_formulas_are_readable_chinese() -> None:
    """Evaluation score labels and formulas should be readable in Markdown."""

    markdown = _build_markdown(
        {
            "data_overview": {
                "total_nodes": 10,
                "root_nodes": 1,
                "max_depth": 3,
                "max_child_count": 4,
            },
            "issues": [],
            "evaluation": {
                "scores": {
                    "structure_score": 98.21,
                    "content_score": 0,
                    "synonym_score": 37.54,
                    "redundancy_score": 99.97,
                    "total_score": 56.96,
                },
                "formulas": {
                    "structure_score": "100 - (deep*2 + wide*5 + unbalanced*3 + orphan*8) / total_nodes * 100",
                    "content_score": "100 - (global_duplicate*1 + sibling_duplicate*5 + parent_child_same*5 + suspicious_parent_child*3) / total_nodes * 100",
                    "synonym_score": "100 - (missing_synonyms*1 + suspicious_synonym*4) / total_nodes * 100",
                    "redundancy_score": "100 - duplicate_related_issue_count / total_nodes * 100",
                    "total_score": "structure*0.3 + content*0.3 + synonym*0.2 + redundancy*0.2",
                },
            },
            "version_diff": {},
            "llm_results": [],
        }
    )

    assert "- 结构健康分：98.21" in markdown
    assert "- 内容质量分：0" in markdown
    assert "- 同义词完整度分：37.54" in markdown
    assert "- 冗余控制分：99.97" in markdown
    assert "- 综合健康分：56.96" in markdown
    assert "过深节点数*2" in markdown
    assert "疑似挂载错误数*3" in markdown
    assert "结构健康分*0.3" in markdown
    assert "structure_score" not in markdown


def test_report_uses_summary_first_structure_without_old_issue_sections() -> None:
    """The Markdown report should summarize issues instead of splitting old sections."""

    markdown = _build_markdown(
        {
            "data_overview": {
                "total_nodes": 10,
                "root_nodes": 1,
                "max_depth": 3,
                "max_child_count": 4,
            },
            "issues": [
                {
                    "issue_type": "orphan_node",
                    "severity": "high",
                    "category_id": "A02",
                    "category_name": "孤立分类",
                    "evidence": "父节点 A01 不存在。",
                    "suggestion": "补充父节点或调整挂载关系。",
                },
                {
                    "issue_type": "missing_synonyms",
                    "severity": "medium",
                    "category_id": "B01",
                    "category_name": "电饭煲",
                    "evidence": "同义词为空。",
                    "suggestion": "补充常用别名。",
                },
            ],
            "evaluation": {
                "scores": {},
                "formulas": {},
            },
            "version_diff": {},
            "llm_results": [],
        }
    )

    assert "## 3. 体系评价结果" in markdown
    assert "## 4. 问题概览" in markdown
    assert "## 5. 版本对比结果" in markdown
    assert "## 6. 维护建议汇总" in markdown
    assert "## 3. 结构类问题" not in markdown
    assert "## 4. 内容类问题" not in markdown
    assert "## 5. 同义词问题" not in markdown
    assert "重点问题清单" not in markdown
    assert "问题总数：2" in markdown
    assert "孤立节点 1 个" in markdown
