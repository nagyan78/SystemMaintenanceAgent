"""Generate lightweight Markdown and HTML diagnosis reports."""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from .common import IssueResult


IssueLike = IssueResult | dict[str, Any]

ISSUE_TYPE_LABELS = {
    "deep_node": "层级过深",
    "wide_node": "节点过宽",
    "branch_wide": "分支偏宽",
    "branch_explosion": "分支明显过宽",
    "unbalanced_branch": "分支不均衡",
    "redundant_single_child_chain": "疑似冗余层级",
    "missing_parent": "父节点缺失",
    "orphan_node": "孤立节点",
    "cycle_parent_child": "循环父子关系",
    "leaf_ratio_abnormal": "叶子占比异常",
    "duplicate_category_name": "全局重名",
    "duplicate_sibling_name": "同级重名",
    "same_name_parent_child": "父子同名",
    "suspicious_name_redundancy": "疑似名称冗余",
    "duplicate_synonym": "同义词重复",
    "suspicious_synonym": "异常同义词",
    "depth_too_deep": "层级过深",
    "width_too_large": "节点过宽",
}

SEVERITY_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

AI_DEPENDENCY_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

ISSUE_TYPE_GROUPS = [
    (
        "结构问题",
        [
            "missing_parent",
            "orphan_node",
            "cycle_parent_child",
            "deep_node",
            "wide_node",
            "branch_explosion",
            "branch_wide",
            "unbalanced_branch",
            "redundant_single_child_chain",
            "leaf_ratio_abnormal",
            "depth_too_deep",
            "width_too_large",
        ],
    ),
    (
        "内容问题",
        [
            "duplicate_category_name",
            "duplicate_sibling_name",
            "same_name_parent_child",
            "suspicious_name_redundancy",
        ],
    ),
    (
        "同义词问题",
        [
            "duplicate_synonym",
            "suspicious_synonym",
        ],
    ),
]

ISSUE_TYPE_ORDER = {
    issue_type: index
    for index, (_, issue_types) in enumerate(ISSUE_TYPE_GROUPS)
    for issue_type in issue_types
}

def generate_markdown_report(summary: dict[str, object], issues: list[IssueResult]) -> str:
    """Generate a Markdown report from summary statistics and issue results."""

    lines = [
        "# 标准产品体系结构诊断报告",
        "",
        "## 数据概况",
        "",
        f"- 总节点数：{summary.get('total_nodes', 0)}",
        f"- 顶层节点数：{summary.get('root_nodes', 0)}",
        f"- 叶子节点数：{summary.get('leaf_nodes', 0)}",
        f"- 最大深度：{summary.get('max_depth', 0)}",
        f"- 最大直接子节点数：{summary.get('max_child_count', 0)}",
        "",
        "## 结构问题",
        "",
        f"- 问题总数：{len(issues)}",
        "",
    ]
    for issue in issues:
        lines.extend(
            [
                f"### {issue.issue_type}: {issue.node_name} ({issue.node_id})",
                "",
                f"- 路径：{issue.path}",
                f"- 严重程度：{issue.severity}",
                f"- 判断依据：{issue.reason}",
                f"- 解决思路：{issue.suggestion}",
                f"- 需要人工确认：{'是' if issue.need_manual_review else '否'}",
                "",
            ]
        )
    if not issues:
        lines.append("未发现首轮结构规则问题。")
    return "\n".join(lines)


def save_report(markdown_text: str, output_path: str) -> None:
    """Save Markdown text to the requested output path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_text, encoding="utf-8")


def generate_html_dashboard(
    summary: dict[str, object],
    issues: list[IssueLike],
    health_score: float | int | None = None,
) -> str:
    """Generate a standalone HTML dashboard for visual issue inspection."""

    ordered_issues = sorted(issues, key=_issue_sort_key)
    issue_counts = Counter(_issue_value(issue, "issue_type") for issue in ordered_issues)
    ai_dependency_counts = Counter(_issue_value(issue, "ai_dependency") or "low" for issue in ordered_issues)
    issue_rows = "\n".join(_render_issue_row(issue) for issue in ordered_issues)
    if not issue_rows:
        issue_rows = '<tr class="empty-row"><td colspan="8">未发现诊断规则问题。</td></tr>'

    issue_type_options = _render_issue_type_options(issue_counts)
    ai_dependency_options = "\n".join(
        f'<option value="{escape(level)}">{escape(_ai_dependency_label(level))} ({count})</option>'
        for level, count in sorted(ai_dependency_counts.items(), key=lambda item: _ai_dependency_sort_key(item[0]))
    )

    cards = "\n".join(
        [
            _render_metric_card("体系健康分", _format_score(health_score), "按问题数量和严重程度扣分"),
            _render_metric_card("总节点数", summary.get("total_nodes", 0), "分类体系节点总量"),
            _render_metric_card("顶层节点", summary.get("root_nodes", 0), "一级分类数量"),
            _render_metric_card("叶子节点", summary.get("leaf_nodes", 0), "无直接子节点的分类"),
            _render_metric_card("叶子节点占比", _format_ratio(summary.get("leaf_ratio", 0)), summary.get("leaf_ratio_label", "整体结构粒度评价")),
            _render_metric_card("最大深度", summary.get("max_depth", 0), "最长分类路径层级"),
            _render_metric_card("平均叶子深度", summary.get("mean_depth", 0), "所有叶子路径的平均深度"),
            _render_metric_card("最大宽度", summary.get("max_child_count", 0), "单节点最多直接子节点"),
            _render_metric_card("诊断问题", len(ordered_issues), "规则命中数量"),
        ]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>标准产品体系诊断看板</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #18202f;
      --muted: #677287;
      --line: #dfe5ef;
      --primary: #1769aa;
      --primary-soft: #e7f1fb;
      --warning: #9a5b00;
      --danger: #b42318;
      --ok: #147a4a;
      --shadow: 0 12px 30px rgba(24, 32, 47, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      background: #16324f;
      color: #fff;
      padding: 28px 32px;
      border-bottom: 4px solid #4ea1d3;
    }}
    header h1 {{
      margin: 0;
      font-size: 28px;
      line-height: 1.25;
      font-weight: 700;
      letter-spacing: 0;
    }}
    header p {{
      margin: 10px 0 0;
      color: #d7e6f3;
      font-size: 14px;
    }}
    main {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px 28px 40px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
      min-height: 112px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .metric strong {{
      display: block;
      font-size: 30px;
      line-height: 1;
      color: var(--primary);
    }}
    .metric small {{
      display: block;
      margin-top: 10px;
      color: var(--muted);
      line-height: 1.35;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 220px 180px 180px auto;
      gap: 12px;
      align-items: end;
      padding: 16px;
      border-bottom: 1px solid var(--line);
      background: #fbfcff;
    }}
    label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    input, select, button {{
      height: 38px;
      border-radius: 6px;
      border: 1px solid #c7d2e1;
      background: #fff;
      color: var(--text);
      font: inherit;
      padding: 0 10px;
    }}
    button {{
      cursor: pointer;
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
      min-width: 88px;
    }}
    .table-wrap {{
      overflow: auto;
      max-height: 70vh;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1280px;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      line-height: 1.45;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #eef3f9;
      z-index: 1;
      color: #344054;
      font-weight: 700;
    }}
    tbody tr:hover {{ background: #f8fbff; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--primary-soft);
      color: var(--primary);
      font-size: 12px;
      white-space: nowrap;
    }}
    .ai-high {{ background: #fee4e2; color: var(--danger); }}
    .ai-medium {{ background: #fff3d6; color: var(--warning); }}
    .ai-low {{ background: #dcfae6; color: var(--ok); }}
    .node-cell {{
      min-width: 220px;
      white-space: nowrap;
    }}
    .node-depth {{
      display: inline-block;
      color: var(--muted);
      font-size: 12px;
      margin-right: 6px;
    }}
    .path {{
      min-width: 280px;
      color: #344054;
    }}
    .path-level {{
      display: inline-block;
      margin: 0 2px 4px 0;
      padding: 2px 6px;
      border-radius: 5px;
      background: #f1f5fa;
      color: #344054;
      font-size: 12px;
    }}
    .reason, .ai-result {{ min-width: 260px; }}
    .evidence {{
      padding: 10px 12px;
      border-left: 4px solid var(--warning);
      border-radius: 6px;
      background: #fff8e6;
      color: #4f3500;
      font-weight: 600;
    }}
    .ai-result-box {{
      display: grid;
      gap: 6px;
      padding: 10px 12px;
      border-left: 4px solid var(--primary);
      border-radius: 6px;
      background: #eef6ff;
      color: #243b53;
    }}
    .ai-result-box.is-empty {{
      border-left-color: var(--line);
      background: #f8fafc;
      color: var(--muted);
    }}
    .ai-result-box strong {{
      color: var(--primary);
    }}
    .empty-row td {{
      text-align: center;
      padding: 32px;
      color: var(--muted);
    }}
    .footer-note {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 860px) {{
      header {{ padding: 22px 18px; }}
      main {{ padding: 18px 14px 32px; }}
      .toolbar {{ grid-template-columns: 1fr; }}
      .metric strong {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>标准产品体系诊断看板</h1>
    <p>展示结构、内容、同义词等规则检查结果，并标出每类问题是否需要 AI 辅助判断。</p>
  </header>
  <main>
    <section class="metrics" aria-label="数据概况">
      {cards}
    </section>
    <section class="panel" aria-label="问题列表">
      <div class="toolbar">
        <label>
          关键词
          <input id="keywordFilter" type="search" placeholder="搜索节点、路径、判断依据或AI分析">
        </label>
        <label>
          问题类型
          <select id="typeFilter">
            <option value="">全部类型</option>
            {issue_type_options}
          </select>
        </label>
        <label>
          AI依赖程度
          <select id="aiDependencyFilter">
            <option value="">全部程度</option>
            {ai_dependency_options}
          </select>
        </label>
        <label>
          AI分析状态
          <select id="aiAnalysisFilter">
            <option value="">全部</option>
            <option value="yes">已分析</option>
            <option value="no">未分析</option>
          </select>
        </label>
        <button id="resetFilters" type="button">重置</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>问题类型</th>
              <th>节点 ID</th>
              <th>节点名称</th>
              <th>路径层级</th>
              <th>AI依赖程度</th>
              <th>AI分析结果</th>
              <th>判断依据</th>
              <th>人工确认</th>
            </tr>
          </thead>
          <tbody id="issueTableBody">
            {issue_rows}
          </tbody>
        </table>
      </div>
    </section>
    <p class="footer-note">该看板只展示诊断结果，不会修改原始 Excel 数据。</p>
  </main>
  <script>
    const keywordFilter = document.querySelector("#keywordFilter");
    const typeFilter = document.querySelector("#typeFilter");
    const aiDependencyFilter = document.querySelector("#aiDependencyFilter");
    const aiAnalysisFilter = document.querySelector("#aiAnalysisFilter");
    const resetFilters = document.querySelector("#resetFilters");
    const rows = Array.from(document.querySelectorAll("#issueTableBody tr")).filter(
      row => !row.classList.contains("empty-row")
    );

    function applyFilters() {{
      const keyword = keywordFilter.value.trim().toLowerCase();
      const issueType = typeFilter.value;
      const aiDependency = aiDependencyFilter.value;
      const aiAnalysis = aiAnalysisFilter.value;
      rows.forEach(row => {{
        const matchesKeyword = !keyword || row.textContent.toLowerCase().includes(keyword);
        const matchesType = !issueType || row.dataset.issueType === issueType;
        const matchesAiDependency = !aiDependency || row.dataset.aiDependency === aiDependency;
        const matchesAiAnalysis = !aiAnalysis || row.dataset.aiAnalyzed === aiAnalysis;
        row.hidden = !(matchesKeyword && matchesType && matchesAiDependency && matchesAiAnalysis);
      }});
    }}

    keywordFilter.addEventListener("input", applyFilters);
    typeFilter.addEventListener("change", applyFilters);
    aiDependencyFilter.addEventListener("change", applyFilters);
    aiAnalysisFilter.addEventListener("change", applyFilters);
    resetFilters.addEventListener("click", () => {{
      keywordFilter.value = "";
      typeFilter.value = "";
      aiDependencyFilter.value = "";
      aiAnalysisFilter.value = "";
      applyFilters();
    }});
  </script>
</body>
</html>"""


def save_html_report(html_text: str, output_path: str) -> None:
    """Save the HTML dashboard to the requested output path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")


def _render_metric_card(title: str, value: object, description: str) -> str:
    """Render a compact metric card for the dashboard header."""

    return (
        '<article class="metric">'
        f"<span>{escape(title)}</span>"
        f"<strong>{escape(str(value))}</strong>"
        f"<small>{escape(str(description))}</small>"
        "</article>"
    )


def _render_issue_row(issue: IssueLike) -> str:
    """Render one issue table row with data attributes for filtering."""

    issue_type = _issue_value(issue, "issue_type")
    candidate_suffix = " 候选" if _issue_bool(issue, "is_candidate", False) else ""
    ai_dependency = _issue_value(issue, "ai_dependency") or "low"
    ai_class = f"ai-{escape(ai_dependency)}"
    need_manual_review = _issue_bool(issue, "need_manual_check", _issue_bool(issue, "need_manual_review", ai_dependency != "low"))
    manual_review = "是" if need_manual_review else "否"
    ai_analyzed = "yes" if _issue_mapping(issue, "ai_judgement") else "no"
    depth = _path_depth(_issue_value(issue, "path"))
    indent = max(0, depth - 1) * 18
    return (
        f'<tr data-issue-type="{escape(issue_type)}" '
        f'data-ai-dependency="{escape(ai_dependency)}" '
        f'data-ai-analyzed="{ai_analyzed}">'
        f'<td><span class="badge">{escape(_issue_type_label(issue_type) + candidate_suffix)}</span></td>'
        f"<td>{escape(_issue_value(issue, 'node_id', 'category_id'))}</td>"
        f'<td class="node-cell" style="padding-left: {14 + indent}px">'
        f'<span class="node-depth">L{depth}</span>{escape(_issue_value(issue, "node_name", "category_name"))}</td>'
        f'<td class="path">{_render_path_levels(_issue_value(issue, "path"))}</td>'
        f'<td><span class="badge {ai_class}">{escape(_ai_dependency_label(ai_dependency))}</span></td>'
        f'<td class="ai-result">{_render_ai_result(issue)}</td>'
        f'<td class="reason"><div class="evidence">{escape(_issue_value(issue, "evidence", "reason"))}</div></td>'
        f"<td>{manual_review}</td>"
        "</tr>"
    )


def _render_ai_result(issue: IssueLike) -> str:
    """Render AI judgement only for rows that were actually analyzed."""

    judgement = _issue_mapping(issue, "ai_judgement")
    if not judgement:
        ai_dependency = _issue_value(issue, "ai_dependency") or "low"
        message = "无需AI分析" if ai_dependency == "low" else "未命中AI样例"
        return f'<div class="ai-result-box is-empty">{escape(message)}</div>'

    if bool(judgement.get("analysis_failed")):
        status = "AI分析失败"
    else:
        status = "确认问题" if bool(judgement.get("is_problem")) else "倾向正常/需复核"
    confidence = _format_confidence(judgement.get("confidence", 0))
    reason = str(judgement.get("reason", "")).strip()
    suggestion = str(judgement.get("suggestion", "")).strip()
    return (
        '<div class="ai-result-box">'
        f"<strong>{escape(status)} · {escape(confidence)}</strong>"
        f"<span>原因：{escape(reason or '-')}</span>"
        f"<span>建议：{escape(suggestion or '-')}</span>"
        "</div>"
    )


def _render_issue_type_options(issue_counts: Counter[str]) -> str:
    """Render grouped issue-type filter options in structure/content/synonym order."""

    chunks: list[str] = []
    emitted: set[str] = set()
    for group_label, issue_types in ISSUE_TYPE_GROUPS:
        options = [
            f'<option value="{escape(issue_type)}">{escape(_issue_type_label(issue_type))} ({issue_counts[issue_type]})</option>'
            for issue_type in issue_types
            if issue_counts.get(issue_type, 0) > 0
        ]
        if options:
            chunks.append(f'<optgroup label="{escape(group_label)}">')
            chunks.extend(options)
            chunks.append("</optgroup>")
            emitted.update(issue_type for issue_type in issue_types if issue_counts.get(issue_type, 0) > 0)

    remaining = sorted(issue_type for issue_type in issue_counts if issue_type not in emitted)
    if remaining:
        chunks.append('<optgroup label="其他问题">')
        chunks.extend(
            f'<option value="{escape(issue_type)}">{escape(_issue_type_label(issue_type))} ({issue_counts[issue_type]})</option>'
            for issue_type in remaining
        )
        chunks.append("</optgroup>")
    return "\n".join(chunks)


def _issue_sort_key(issue: IssueLike) -> tuple[int, str, int, str]:
    issue_type = _issue_value(issue, "issue_type")
    return (
        ISSUE_TYPE_ORDER.get(issue_type, 999),
        issue_type,
        _path_depth(_issue_value(issue, "path")),
        _issue_value(issue, "path"),
    )


def _render_path_levels(path: str) -> str:
    parts = _path_parts(path)
    if not parts:
        return ""
    return " ".join(f'<span class="path-level">{escape(part)}</span>' for part in parts)


def _path_depth(path: str) -> int:
    return max(1, len(_path_parts(path)))


def _path_parts(path: str) -> list[str]:
    return [part.strip() for part in str(path).split(">") if part.strip()]


def _issue_value(issue: IssueLike, key: str, fallback_key: str | None = None) -> str:
    """Read a field from either an IssueResult or an advanced issue dict."""

    if isinstance(issue, dict):
        value = issue.get(key)
        if (value is None or value == "") and fallback_key:
            value = issue.get(fallback_key, "")
        return str(value or "")
    value = getattr(issue, key, None)
    if (value is None or value == "") and fallback_key:
        value = getattr(issue, fallback_key, "")
    return str(value or "")


def _issue_bool(issue: IssueLike, key: str, default: bool) -> bool:
    if isinstance(issue, dict):
        return bool(issue.get(key, default))
    return bool(getattr(issue, key, default))


def _issue_mapping(issue: IssueLike, key: str) -> dict[str, Any]:
    value = issue.get(key) if isinstance(issue, dict) else getattr(issue, key, None)
    return value if isinstance(value, dict) else {}


def _format_score(score: float | int | None) -> str:
    if score is None:
        return "-"
    return f"{round(float(score), 1)} / 100"


def _format_ratio(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _format_confidence(value: object) -> str:
    try:
        return f"置信度 {float(value):.2f}"
    except (TypeError, ValueError):
        return "置信度 -"


def _issue_type_label(issue_type: str) -> str:
    return ISSUE_TYPE_LABELS.get(issue_type, issue_type)


def _severity_label(severity: str) -> str:
    return SEVERITY_LABELS.get(severity, severity)


def _ai_dependency_label(level: str) -> str:
    return AI_DEPENDENCY_LABELS.get(level, level or "低")


def _ai_dependency_sort_key(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 99)


def _format_node_list(value: object) -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _render_ai_result(issue: IssueLike) -> str:
    """Render semantic AI judgement; mark rule fallbacks explicitly."""

    judgement = _issue_mapping(issue, "ai_judgement")
    if not judgement:
        ai_dependency = _issue_value(issue, "ai_dependency") or "low"
        message = "无需AI分析" if ai_dependency == "low" else "未命中AI样例"
        return f'<div class="ai-result-box is-empty">{escape(message)}</div>'

    if bool(judgement.get("analysis_failed")) or judgement.get("result_source") == "rule_result":
        rule_reason = str(judgement.get("rule_reason", "")).strip()
        rule_suggestion = str(judgement.get("rule_suggestion", "")).strip()
        return (
            '<div class="ai-result-box is-empty">'
            "<strong>规则结果（AI调用失败）</strong>"
            f"<span>规则依据：{escape(rule_reason or '-')}</span>"
            f"<span>规则建议：{escape(rule_suggestion or '-')}</span>"
            "</div>"
        )

    status = "确认问题" if bool(judgement.get("is_problem")) else "不确认问题/需复核"
    confidence = _format_confidence(judgement.get("confidence", 0))
    relevant_nodes = _format_node_list(judgement.get("relevant_nodes", judgement.get("key_nodes", [])))
    semantic_relation = str(judgement.get("semantic_relation", "")).strip()
    reason = str(judgement.get("reason", "")).strip()
    suggestion = str(judgement.get("suggestion", "")).strip()
    return (
        '<div class="ai-result-box">'
        f"<strong>{escape(status)} · {escape(confidence)}</strong>"
        f"<span>必要分析节点：{escape(relevant_nodes or '-')}</span>"
        f"<span>语义关系：{escape(semantic_relation or '-')}</span>"
        f"<span>AI语义原因：{escape(reason or '-')}</span>"
        f"<span>AI修改建议：{escape(suggestion or '-')}</span>"
        "</div>"
    )
