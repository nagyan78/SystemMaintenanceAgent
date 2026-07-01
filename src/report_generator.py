"""Generate lightweight Markdown and HTML diagnosis reports."""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from .common import IssueResult


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
                f"- 维护建议：{issue.suggestion}",
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


def generate_html_dashboard(summary: dict[str, object], issues: list[IssueResult]) -> str:
    """Generate a standalone HTML dashboard for visual issue inspection."""

    issue_counts = Counter(issue.issue_type for issue in issues)
    severity_counts = Counter(issue.severity for issue in issues)
    issue_rows = "\n".join(_render_issue_row(issue) for issue in issues)
    if not issue_rows:
        issue_rows = (
            '<tr class="empty-row"><td colspan="8">未发现首轮结构规则问题。</td></tr>'
        )

    issue_type_options = "\n".join(
        f'<option value="{escape(issue_type)}">{escape(issue_type)} ({count})</option>'
        for issue_type, count in sorted(issue_counts.items())
    )
    severity_options = "\n".join(
        f'<option value="{escape(severity)}">{escape(severity)} ({count})</option>'
        for severity, count in sorted(severity_counts.items())
    )

    cards = "\n".join(
        [
            _render_metric_card("总节点数", summary.get("total_nodes", 0), "分类体系节点总量"),
            _render_metric_card("顶层节点", summary.get("root_nodes", 0), "一级分类数量"),
            _render_metric_card("叶子节点", summary.get("leaf_nodes", 0), "无直接子节点的分类"),
            _render_metric_card("最大深度", summary.get("max_depth", 0), "最长分类路径层级"),
            _render_metric_card("最大宽度", summary.get("max_child_count", 0), "单节点最多直接子节点"),
            _render_metric_card("结构问题", len(issues), "首轮规则命中数量"),
        ]
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>标准产品体系结构诊断看板</title>
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
      grid-template-columns: minmax(220px, 1fr) 180px 180px auto;
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
      min-width: 1080px;
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
    tbody tr:hover {{
      background: #f8fbff;
    }}
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
    .severity-high {{ background: #fee4e2; color: var(--danger); }}
    .severity-medium {{ background: #fff3d6; color: var(--warning); }}
    .severity-low {{ background: #dcfae6; color: var(--ok); }}
    .path {{
      min-width: 260px;
      color: #344054;
    }}
    .reason, .suggestion {{
      min-width: 260px;
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
    <h1>标准产品体系结构诊断看板</h1>
    <p>首轮规则检测结果：父节点缺失、层级过深、节点过宽。</p>
  </header>
  <main>
    <section class="metrics" aria-label="数据概况">
      {cards}
    </section>
    <section class="panel" aria-label="问题列表">
      <div class="toolbar">
        <label>
          关键词
          <input id="keywordFilter" type="search" placeholder="搜索节点、路径、原因或建议">
        </label>
        <label>
          问题类型
          <select id="typeFilter">
            <option value="">全部类型</option>
            {issue_type_options}
          </select>
        </label>
        <label>
          严重程度
          <select id="severityFilter">
            <option value="">全部程度</option>
            {severity_options}
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
              <th>路径</th>
              <th>严重程度</th>
              <th>判断依据</th>
              <th>维护建议</th>
              <th>人工确认</th>
            </tr>
          </thead>
          <tbody id="issueTableBody">
            {issue_rows}
          </tbody>
        </table>
      </div>
    </section>
    <p class="footer-note">该看板为静态 HTML 文件，只展示诊断结果，不会修改原始 Excel 数据。</p>
  </main>
  <script>
    const keywordFilter = document.querySelector("#keywordFilter");
    const typeFilter = document.querySelector("#typeFilter");
    const severityFilter = document.querySelector("#severityFilter");
    const resetFilters = document.querySelector("#resetFilters");
    const rows = Array.from(document.querySelectorAll("#issueTableBody tr")).filter(
      row => !row.classList.contains("empty-row")
    );

    function applyFilters() {{
      const keyword = keywordFilter.value.trim().toLowerCase();
      const issueType = typeFilter.value;
      const severity = severityFilter.value;
      rows.forEach(row => {{
        const matchesKeyword = !keyword || row.textContent.toLowerCase().includes(keyword);
        const matchesType = !issueType || row.dataset.issueType === issueType;
        const matchesSeverity = !severity || row.dataset.severity === severity;
        row.hidden = !(matchesKeyword && matchesType && matchesSeverity);
      }});
    }}

    keywordFilter.addEventListener("input", applyFilters);
    typeFilter.addEventListener("change", applyFilters);
    severityFilter.addEventListener("change", applyFilters);
    resetFilters.addEventListener("click", () => {{
      keywordFilter.value = "";
      typeFilter.value = "";
      severityFilter.value = "";
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
        f"<small>{escape(description)}</small>"
        "</article>"
    )


def _render_issue_row(issue: IssueResult) -> str:
    """Render one issue table row with data attributes for filtering."""

    severity_class = f"severity-{escape(issue.severity)}"
    manual_review = "是" if issue.need_manual_review else "否"
    return (
        f'<tr data-issue-type="{escape(issue.issue_type)}" data-severity="{escape(issue.severity)}">'
        f'<td><span class="badge">{escape(issue.issue_type)}</span></td>'
        f"<td>{escape(issue.node_id)}</td>"
        f"<td>{escape(issue.node_name)}</td>"
        f'<td class="path">{escape(issue.path)}</td>'
        f'<td><span class="badge {severity_class}">{escape(issue.severity)}</span></td>'
        f'<td class="reason">{escape(issue.reason)}</td>'
        f'<td class="suggestion">{escape(issue.suggestion)}</td>'
        f"<td>{manual_review}</td>"
        "</tr>"
    )
