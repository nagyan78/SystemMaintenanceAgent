"""第一轮产品分类树结构诊断命令行入口。"""

from __future__ import annotations

import argparse
from collections import Counter

from .data_loader import load_product_data
from .report_generator import (
    generate_html_dashboard,
    generate_markdown_report,
    save_html_report,
    save_report,
)
from .structure_checker import check_structure_issues
from .tree_analyzer import summarize_tree
from .tree_builder import add_tree_fields


def main() -> None:
    """从命令行参数读取 Excel，生成 Markdown 报告和 HTML 看板。"""

    parser = argparse.ArgumentParser(description="标准产品体系第一轮结构诊断")
    parser.add_argument("--input", required=True, help="输入 .xlsx 文件路径")
    parser.add_argument(
        "--output",
        default="outputs/reports/diagnosis_report.md",
        help="Markdown 诊断报告输出路径",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/reports/diagnosis_dashboard.html",
        help="HTML 诊断看板输出路径",
    )
    args = parser.parse_args()

    # 诊断流程分为四步：
    # 1. 读取并清洗 Excel；
    # 2. 补充树结构派生字段；
    # 3. 运行结构规则检查；
    # 4. 分别生成 Markdown 和 HTML 报告。
    raw_df = load_product_data(args.input)
    tree_df = add_tree_fields(raw_df)
    summary = summarize_tree(tree_df)
    issues = check_structure_issues(tree_df)
    issue_counts = Counter(issue.issue_type for issue in issues)

    report = generate_markdown_report(summary, issues)
    save_report(report, args.output)

    html_dashboard = generate_html_dashboard(summary, issues)
    save_html_report(html_dashboard, args.html_output)

    print(f"总节点数: {summary['total_nodes']}")
    print(f"最大深度: {summary['max_depth']}")
    print(f"最大直接子节点数: {summary['max_child_count']}")
    print(f"层级过深问题数量: {issue_counts.get('depth_too_deep', 0)}")
    print(f"节点过宽问题数量: {issue_counts.get('width_too_large', 0)}")
    print(f"父节点缺失问题数量: {issue_counts.get('missing_parent', 0)}")
    print(f"Markdown 报告已输出: {args.output}")
    print(f"HTML 看板已输出: {args.html_output}")


if __name__ == "__main__":
    main()
