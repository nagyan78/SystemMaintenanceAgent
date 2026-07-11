from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.file_repo import FileRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import ReportResult
from backend.app.services.taxonomy_service import TaxonomyService


class ReportService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_diagnosis_report(self, version_id: int) -> ReportResult:
        version = VersionRepository(self.settings).get_version(version_id)
        if version is None:
            raise ValueError(f"Taxonomy version {version_id} was not found.")
        file_record = FileRepository(self.settings).get_file(int(version["file_id"]))
        if file_record is None:
            file_record = {"file_name": f"file_{version['file_id']}"}
        overview = TaxonomyService(self.settings).get_overview(version_id)
        issue_repo = DiagnosisRepository(self.settings)
        issue_summary = issue_repo.count_by_type(version_id)
        content_issue_count = issue_repo.count_content_issues(version_id)
        examples = issue_repo.list_examples(version_id, limit=5)
        content_examples = issue_repo.list_content_examples(version_id, limit=3)
        suggestions = SuggestionRepository(self.settings).list_suggestions(version_id=version_id)
        operation_logs = _list_operation_logs(self.settings, version_id)

        self.settings.report_dir.mkdir(parents=True, exist_ok=True)
        report_name = f"{version['version_no']}_diagnosis_report.md"
        report_path = self.settings.report_dir / report_name
        report_path.write_text(
            self._render(
                version,
                file_record,
                overview,
                issue_summary,
                content_issue_count,
                examples,
                content_examples,
                suggestions,
                operation_logs,
            ),
            encoding="utf-8",
        )
        return ReportResult(
            version_id=version_id,
            report_name=report_name,
            report_path=report_path,
            status="completed",
        )

    def _render(
        self,
        version: dict,
        file_record: dict,
        overview,
        issue_summary: dict[str, int],
        content_issue_count: int,
        examples: list[dict],
        content_examples: list[dict],
        suggestions: list,
        operation_logs: list[dict],
    ) -> str:
        created_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        example_lines = "\n".join(
            f"- [{item['risk_level']}] {item['issue_type']}：{item['description']}"
            for item in examples
        ) or "- 暂无典型结构问题。"
        content_example_lines = "\n".join(
            f"- [{item['risk_level']}] {item['issue_type']}：{item['description']}"
            for item in content_examples
        ) or "- 暂无典型内容问题。"

        if content_issue_count > 0:
            content_section = f"""- AI 语义诊断问题总数：{content_issue_count}
- 诊断方式：DeepSeek ReAct Agent Loop（召回→LLM判断→补充查询→再判断）
- 诊断范围：由 diagnosis_planning_node 智能规划（非全量扫描）

典型内容问题：
{content_example_lines}"""
        else:
            content_section = "内容诊断 Agent 已运行但未发现语义异常（或 M2 Agent Loop 未在本次执行中激活）。"

        total_issues = sum(issue_summary.values()) + content_issue_count
        quality_score = (
            float(version["quality_score"])
            if version.get("quality_score") is not None
            else None
        )
        quality_line = (
            f"体系健康度：{_quality_label(quality_score)}（{quality_score:.1f}/100）"
            if quality_score is not None
            else "体系健康度：待执行 quality-v1 评价"
        )
        suggestion_lines = _render_suggestions(suggestions)
        operation_lines = _render_operations(operation_logs)
        return f"""# 产品标准体系诊断报告

## 1. 基本信息

- 报告生成时间：{created_at}
- 文件名称：{file_record['file_name']}
- 版本号：{version['version_no']}
- 版本 ID：{version['id']}

## 2. 体系统计

- 节点总数：{overview.node_count}
- 一级类目数：{overview.root_count}
- 最大层级：{overview.max_depth}
- 叶子节点数：{overview.leaf_count}
- 非叶子节点数：{overview.non_leaf_count}
- 最大直接子节点数：{overview.max_children_count}
- 同义词非空节点数：{overview.synonym_non_empty_count}

## 3. 结构诊断结果

- 父节点缺失：{issue_summary.get('missing_parent', 0)}
- 层级过深：{issue_summary.get('deep_level', 0)}
- 节点过宽：{issue_summary.get('wide_node', 0)}
- 重复名称：{issue_summary.get('duplicate_name', 0)}
- 结构问题总数：{sum(issue_summary.values())}

## 4. 内容诊断结果

{content_section}

## 5. 典型问题案例

{example_lines}

## 6. 智能维护建议

{suggestion_lines}

## 7. 版本变更记录

{operation_lines}

## 8. 质量评分

{quality_line}

> 版本分数只读取持久化的 `quality-v1` 评价；未评价时不使用报告内临时公式补分。

## 9. 后续优化建议

- 优先补齐缺失父节点，修复断裂路径。
- 对层级过深的路径评估是否需要归并或重命名。
- 对直接子节点过宽的类目增加中间层。
- 对重复名称节点结合完整路径判断是否需要合并、重命名或保留。
"""


def _render_suggestions(suggestions: list) -> str:
    if not suggestions:
        return "- 暂无智能维护建议。"
    lines = []
    status_counts: dict[str, int] = {}
    for suggestion in suggestions:
        status_counts[suggestion.status] = status_counts.get(suggestion.status, 0) + 1
    counts = "，".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
    lines.append(f"- 建议总数：{len(suggestions)}（{counts}）")
    for suggestion in suggestions[:5]:
        lines.append(
            f"- [{suggestion.status}] {suggestion.action_type}：{suggestion.suggestion}"
        )
    return "\n".join(lines)


def _render_operations(operation_logs: list[dict]) -> str:
    if not operation_logs:
        return "- 暂无动作执行或版本变更记录。"
    return "\n".join(
        f"- {item['operation_type']}：{item['operation_detail'] or '{}'}"
        for item in operation_logs[:8]
    )


def _list_operation_logs(settings: Settings, version_id: int) -> list[dict]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT operation_type, operation_detail, created_time
            FROM operation_log
            WHERE version_id = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (version_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _quality_label(score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 50:
        return "一般"
    return "需要重点关注"
