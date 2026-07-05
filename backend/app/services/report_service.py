from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.file_repo import FileRepository
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
            raise ValueError(f"Uploaded file {version['file_id']} was not found.")
        overview = TaxonomyService(self.settings).get_overview(version_id)
        issue_repo = DiagnosisRepository(self.settings)
        issue_summary = issue_repo.count_by_type(version_id)
        examples = issue_repo.list_examples(version_id, limit=5)

        self.settings.report_dir.mkdir(parents=True, exist_ok=True)
        report_name = f"{version['version_no']}_diagnosis_report.md"
        report_path = self.settings.report_dir / report_name
        report_path.write_text(
            self._render(version, file_record, overview, issue_summary, examples),
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
        examples: list[dict],
    ) -> str:
        created_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        example_lines = "\n".join(
            f"- [{item['risk_level']}] {item['issue_type']}：{item['description']}"
            for item in examples
        ) or "- 暂无典型结构问题。"
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

M1 阶段未启用内容诊断智能体，内容问题数：0。

## 5. 典型问题案例

{example_lines}

## 6. 智能维护建议

M1 阶段未启用建议生成智能体，暂无待审核建议。

## 7. 版本变更记录

当前报告基于初始导入版本生成，未执行分类调整动作。

## 8. 质量评分

M1 阶段暂不计算综合质量评分。

## 9. 后续优化建议

- 优先补齐缺失父节点，修复断裂路径。
- 对层级过深的路径评估是否需要归并或重命名。
- 对直接子节点过宽的类目增加中间层。
- 对重复名称节点结合完整路径判断是否需要合并、重命名或保留。
"""
