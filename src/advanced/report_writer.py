"""Write Markdown and JSON reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


SCORE_LABELS = {
    "structure_score": "结构健康分",
    "content_score": "内容质量分",
    "synonym_score": "同义词完整度分",
    "redundancy_score": "冗余控制分",
    "total_score": "综合健康分",
}

FORMULA_EXPLANATIONS = {
    "structure_score": "100 - （过深节点数*2 + 过宽节点数*5 + 分支不均衡数*3 + 孤立节点数*8） / 节点总数 * 100",
    "content_score": "100 - （全局重名数*1 + 同级重名数*5 + 父子同名数*5 + 疑似挂载错误数*3） / 节点总数 * 100",
    "synonym_score": "100 - （缺少同义词数*1 + 可疑同义词数*4） / 节点总数 * 100",
    "redundancy_score": "100 - 重复相关问题数 / 节点总数 * 100",
    "total_score": "结构健康分*0.3 + 内容质量分*0.3 + 同义词完整度分*0.2 + 冗余控制分*0.2",
}

ISSUE_TYPE_LABELS = {
    "deep_node": "层级过深",
    "wide_node": "节点过宽",
    "unbalanced_branch": "分支不均衡",
    "orphan_node": "孤立节点",
    "duplicate_category_name": "全局重名",
    "duplicate_sibling_name": "同级重名",
    "same_name_parent_child": "父子同名",
    "suspicious_parent_child": "疑似挂载错误",
    "missing_synonyms": "缺少同义词",
    "suspicious_synonym": "可疑同义词",
}

SEVERITY_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}


def write_reports(
    output_path: str | Path,
    df: pd.DataFrame,
    issues: list[dict[str, Any]],
    evaluation: dict[str, Any],
    version_diff: dict[str, Any] | None = None,
    llm_results: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    """Write Markdown report and adjacent JSON result file."""

    md_path = Path(output_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = md_path.with_suffix(".json")

    payload = {
        "data_overview": _data_overview(df),
        "issues": issues,
        "llm_results": llm_results or [],
        "evaluation": evaluation,
        "version_diff": version_diff or {},
    }
    md_path.write_text(_build_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def _data_overview(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "total_nodes": len(df),
        "root_nodes": int(df["parent_id"].astype(str).str.lower().isin({"", "0", "none", "nan", "null", "-1"}).sum()),
        "max_depth": int(df["depth"].max()) if len(df) else 0,
        "max_child_count": int(df["child_count"].max()) if len(df) else 0,
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    overview = payload["data_overview"]
    issues = payload["issues"]
    evaluation = payload["evaluation"]
    version_diff = payload["version_diff"]
    llm_results = payload["llm_results"]

    lines = [
        "# 标准产品体系维护分析报告",
        "",
        "## 1. 项目说明",
        "本报告由规则检测与可选 LLM 语义判断生成，用于发现产品分类树中的结构、内容、同义词和版本变化问题。",
        "",
        "## 2. 数据概况",
        f"- 节点总数：{overview['total_nodes']}",
        f"- 根节点数：{overview['root_nodes']}",
        f"- 最大深度：{overview['max_depth']}",
        f"- 最大直接子节点数：{overview['max_child_count']}",
        "",
        "## 3. 体系评价结果",
    ]
    for key, value in evaluation.get("scores", {}).items():
        lines.append(f"- {SCORE_LABELS.get(key, key)}：{value}")
    lines.extend(["", "### 指标计算方式"])
    for key, formula in evaluation.get("formulas", {}).items():
        label = SCORE_LABELS.get(key, key)
        explanation = FORMULA_EXPLANATIONS.get(key, formula)
        lines.append(f"- {label}：`{explanation}`")

    lines.extend(["", "## 4. 问题概览"])
    lines.extend(_issue_overview_lines(issues))

    lines.extend(["", "## 5. 版本对比结果"])
    if version_diff:
        for key, value in version_diff.get("summary", {}).items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- 未提供对比版本。")

    lines.extend(["", "## 6. 维护建议汇总"])
    lines.extend(_summary_lines(issues, llm_results))

    return "\n".join(lines) + "\n"


def _issue_overview_lines(issues: list[dict[str, Any]]) -> list[str]:
    if not issues:
        return ["- 暂未发现。"]

    severity_counts = {
        label: sum(1 for issue in issues if issue.get("severity") == severity)
        for severity, label in SEVERITY_LABELS.items()
    }
    lines = [
        f"- 问题总数：{len(issues)}",
        "- 风险分布："
        + "，".join(f"{label} {count} 个" for label, count in severity_counts.items()),
    ]

    type_counts: dict[str, int] = {}
    for issue in issues:
        issue_type = str(issue.get("issue_type", "unknown"))
        type_counts[issue_type] = type_counts.get(issue_type, 0) + 1
    ordered_types = sorted(type_counts.items(), key=lambda item: item[1], reverse=True)
    lines.append(
        "- 主要问题："
        + "，".join(f"{ISSUE_TYPE_LABELS.get(issue_type, issue_type)} {count} 个" for issue_type, count in ordered_types[:8])
    )
    return lines


def _summary_lines(issues: list[dict[str, Any]], llm_results: list[dict[str, Any]]) -> list[str]:
    if not issues:
        return ["- 当前规则未发现明显维护问题。"]
    high_count = sum(1 for issue in issues if issue.get("severity") == "high")
    medium_count = sum(1 for issue in issues if issue.get("severity") == "medium")
    llm_problem_count = sum(1 for item in llm_results if item.get("llm_judgement", {}).get("is_problem"))
    return [
        f"- 优先处理高风险问题 {high_count} 个，包括孤儿节点、同父重复、父子同名和过宽节点。",
        f"- 安排人工复核中风险问题 {medium_count} 个，重点关注过深、结构不均衡、疑似挂载和异常同义词。",
        f"- LLM 确认为问题的候选项 {llm_problem_count} 个，可作为调整优先级依据。",
        "- 对过宽节点优先增加中间层级；对重复节点优先合并或重命名；对同义词问题优先补充高频别名并删除错误别名。",
    ]
