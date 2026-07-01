"""Command line entry point for standard product taxonomy maintenance."""

from __future__ import annotations

import argparse
import logging

from config import settings
from data_loader import load_product_data
from evaluator import evaluate_system
from llm_judge import judge_parent_child_issues, judge_synonym_issues
from report_writer import write_reports
from rule_checker import (
    detect_deep_nodes,
    detect_duplicate_names,
    detect_missing_synonyms,
    detect_orphan_nodes,
    detect_same_name_parent_child,
    detect_suspicious_parent_child_by_rule,
    detect_suspicious_synonyms_by_rule,
    detect_unbalanced_branches,
    detect_wide_nodes,
)
from tree_builder import enrich_tree_fields
from version_compare import compare_versions


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(description="标准产品体系维护分析原型")
    parser.add_argument("--input", required=True, help="输入数据文件，支持 CSV/XLSX")
    parser.add_argument("--compare", help="可选，对比版本数据文件")
    parser.add_argument("--output", default="output/report.md", help="Markdown 报告输出路径")
    parser.add_argument("--max-depth", type=int, default=settings.max_depth, help="最大层级深度阈值")
    parser.add_argument("--max-children", type=int, default=settings.max_children, help="最大直接子节点数阈值")
    return parser.parse_args()


def main() -> None:
    """Run single-version analysis and optional version comparison."""

    args = parse_args()
    logger.info("Loading input data: %s", args.input)
    df = enrich_tree_fields(load_product_data(args.input))

    logger.info("Running rule checks")
    parent_child_candidates = detect_suspicious_parent_child_by_rule(df)
    synonym_candidates = detect_suspicious_synonyms_by_rule(df)
    issues = [
        *detect_deep_nodes(df, args.max_depth),
        *detect_wide_nodes(df, args.max_children),
        *detect_unbalanced_branches(df),
        *detect_duplicate_names(df),
        *detect_same_name_parent_child(df),
        *detect_missing_synonyms(df),
        *synonym_candidates,
        *detect_orphan_nodes(df),
        *parent_child_candidates,
    ]

    logger.info("Running optional LLM semantic checks")
    llm_results = [
        *judge_parent_child_issues(parent_child_candidates, df),
        *judge_synonym_issues(synonym_candidates, df),
    ]

    logger.info("Calculating evaluation metrics")
    evaluation = evaluate_system(df, issues)

    version_diff = None
    if args.compare:
        logger.info("Loading compare data: %s", args.compare)
        compare_df = enrich_tree_fields(load_product_data(args.compare))
        logger.info("Comparing versions")
        version_diff = compare_versions(df, compare_df)

    logger.info("Writing reports")
    md_path, json_path = write_reports(args.output, df, issues, evaluation, version_diff, llm_results)
    logger.info("Done. Markdown: %s JSON: %s", md_path, json_path)


if __name__ == "__main__":
    main()
