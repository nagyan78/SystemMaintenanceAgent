import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.file_repo import FileRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.repositories.report_repo import ReportRepository
from backend.app.schemas.issue import ReportResult
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.domain.issue_types import get_issue_type


logger = logging.getLogger(__name__)

STRUCTURE_TYPES = {
    "missing_parent",
    "deep_level",
    "wide_node",
    "duplicate_name",
    "orphan",
    "duplicate_mount",
    "cycle_reference",
    "circular_reference",
    "excessive_depth",
    "excessive_width",
    "duplicate_sibling",
    "parent_child_redundancy",
}
ISSUE_LABELS = {
    "missing_parent": "父节点缺失",
    "deep_level": "层级过深",
    "wide_node": "节点过宽",
    "duplicate_name": "重复名称",
    "orphan": "孤立节点",
    "duplicate_mount": "重复挂载",
    "cycle_reference": "循环引用",
    "circular_reference": "循环引用",
    "bad_parent_child_relation": "父子关系异常",
    "synonym_pollution": "同义词污染",
    "synonym_format": "同义词格式问题",
    "synonym_format_issue": "同义词格式问题",
    "semantic_duplicate": "语义重复",
    "inconsistent_granularity": "粒度不一致",
    "naming_irregular": "命名不规范",
    "vague_node": "节点含义模糊",
    "ambiguous_name": "节点含义模糊",
}
ISSUE_DESCRIPTIONS = {
    "missing_parent": "节点引用的父节点在当前版本中不存在，会造成分类路径断裂。",
    "deep_level": "节点路径超过当前层级阈值，可能增加检索和维护复杂度。",
    "wide_node": "同一父节点直接子节点过多，可能降低浏览和维护效率。",
    "duplicate_name": "相同名称出现在多个位置，需要结合完整路径判断是否重复。",
    "orphan": "节点未形成可追溯的有效祖先路径。",
    "duplicate_mount": "同一节点被重复挂载，可能造成统计和路径口径不一致。",
    "cycle_reference": "节点祖先关系形成循环，分类树无法正常展开。",
    "circular_reference": "节点祖先关系形成循环，分类树无法正常展开。",
    "bad_parent_child_relation": "子节点含义与父节点分类原则不一致，需复核挂载关系。",
    "synonym_pollution": "同义词中混入了与主名称不完全等价的概念。",
    "synonym_format": "同义词存在主名称重复、重复值、空值或格式不统一。",
    "synonym_format_issue": "同义词存在主名称重复、重复值、空值或格式不统一。",
    "semantic_duplicate": "不同节点在语义上可能表达同一概念，需要合并复核。",
    "inconsistent_granularity": "同一分类范围内节点粒度不一致，影响分类口径。",
    "naming_irregular": "节点名称不符合当前命名规范或表达不统一。",
    "vague_node": "节点名称无法清晰界定分类对象或范围。",
    "ambiguous_name": "节点名称无法清晰界定分类对象或范围。",
}
RISK_LABELS = {"high": "高风险", "medium": "中风险", "low": "低风险"}
RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
STATUS_LABELS = {
    "pending": "待处理",
    "approved": "已通过",
    "rejected": "已驳回",
    "edited": "已编辑",
    "executed": "已执行",
    "failed": "处理失败",
    "resolved": "已解决",
}
ACTION_LABELS = {
    "add_node": "新增节点",
    "move_node": "移动节点",
    "rename_node": "重命名节点",
    "merge_node": "合并节点",
    "clean_synonym": "修改同义词",
    "split_subtree": "拆分子树",
    "deprecate_node": "停用节点",
    "delete_leaf_node": "删除节点",
    "mark_as_valid": "标记为有效",
}


@dataclass
class DiagnosisReportData:
    basic_info: dict[str, Any]
    runtime_info: dict[str, Any]
    taxonomy_statistics: dict[str, int]
    issue_summary: dict[str, Any]
    structure_issues: list[dict[str, Any]]
    content_issues: list[dict[str, Any]]
    issue_groups: list[dict[str, Any]]
    representative_cases: list[dict[str, Any]]
    persisted_suggestions: list[dict[str, Any]]
    guidance_suggestions: list[dict[str, Any]]
    quality_result: dict[str, Any]
    version_changes: dict[str, Any]
    conclusion: str
    next_actions: dict[str, list[str]]
    all_issues: list[dict[str, Any]]


class ReportService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_diagnosis_report(
        self, version_id: int, *, report_type: str = "final",
        review_batch_id: str | None = None,
        workflow_id: str | None = None, run_id: str | None = None,
    ) -> ReportResult:
        if report_type not in {"draft", "partial", "failed", "final"}:
            raise ValueError("report_type must be draft, partial, failed or final")
        data = self.collect_report_data(version_id)
        markdown = self.render_markdown_report(data)
        markdown += self._governance_appendix(version_id, review_batch_id)
        if report_type == "draft":
            markdown = "> 诊断草稿：本报告尚未完成 AI 修改方案执行和复诊，不是最终交付结论。\n\n" + markdown
        elif report_type == "partial":
            markdown = "> 部分完成报告：规则诊断和已完成的 AI 结果已保留；未完成范围及原因见覆盖说明。\n\n" + markdown
        elif report_type == "failed":
            markdown = "> 失败报告：本次运行未能完成，本文仅记录失败前已持久化的可信事实。\n\n" + markdown
        self.settings.report_dir.mkdir(parents=True, exist_ok=True)
        report_name = report_file_name(
            {"version_no": data.basic_info["version_no"], "id": version_id}, report_type
        )
        report_path = self.settings.report_dir / report_name
        report_path.write_text(markdown, encoding="utf-8")
        ReportRepository(self.settings).save(
            version_id=version_id, report_type=report_type,
            report_path=str(report_path), review_batch_id=review_batch_id,
            workflow_id=workflow_id, run_id=run_id,
            fact_payload=json.dumps(_json_ready(asdict(data)), ensure_ascii=False, default=str),
        )
        return ReportResult(
            version_id=version_id,
            report_name=report_name,
            report_path=report_path,
            status="completed",
        )

    def collect_report_data(self, version_id: int) -> DiagnosisReportData:
        version = VersionRepository(self.settings).get_version(version_id)
        if version is None:
            raise ValueError(f"Taxonomy version {version_id} was not found.")
        file_record = FileRepository(self.settings).get_file(int(version["file_id"])) or {}
        overview = TaxonomyService(self.settings).get_overview(version_id)
        task = TaskRepository(self.settings).get_latest_diagnosis_for_version(version_id)
        task_result = _load_json(task.get("result_payload") if task else None)
        raw_issues = DiagnosisRepository(self.settings).list_issues(version_id)
        raw_suggestions = SuggestionRepository(self.settings).list_suggestions(version_id=version_id)
        issues = _enrich_issues(self.settings, version_id, raw_issues)
        active_issues = [item for item in issues if item.get("status") not in {"resolved", "false_positive"}]
        structure_issues = [item for item in active_issues if item["issue_type"] in STRUCTURE_TYPES]
        content_issues = [item for item in active_issues if item["issue_type"] not in STRUCTURE_TYPES]
        issue_summary = build_issue_summary(structure_issues, content_issues)
        issue_groups = analyze_common_root_causes(active_issues)
        representative_cases = select_representative_cases(active_issues, issue_groups)
        persisted = [_suggestion_to_dict(item) for item in raw_suggestions]
        guidance = build_guidance_suggestions(active_issues)
        quality = build_quality_explanation(version.get("quality_score"), active_issues)
        stats = {
            "node_count": overview.node_count,
            "root_count": overview.root_count,
            "max_depth": overview.max_depth,
            "leaf_count": overview.leaf_count,
            "non_leaf_count": overview.non_leaf_count,
            "max_children_count": overview.max_children_count,
            "synonym_non_empty_count": overview.synonym_non_empty_count,
        }
        basic_info = _build_basic_info(version, file_record, task)
        runtime_info = _build_runtime_info(task, task_result, overview.node_count, issues)
        changes = _build_version_changes(self.settings, version)
        conclusion = build_conclusion(stats, issue_summary, self.settings)
        next_actions = build_next_actions(active_issues)
        return DiagnosisReportData(
            basic_info=basic_info,
            runtime_info=runtime_info,
            taxonomy_statistics=stats,
            issue_summary=issue_summary,
            structure_issues=structure_issues,
            content_issues=content_issues,
            issue_groups=issue_groups,
            representative_cases=representative_cases,
            persisted_suggestions=persisted,
            guidance_suggestions=guidance,
            quality_result=quality,
            version_changes=changes,
            conclusion=conclusion,
            next_actions=next_actions,
            all_issues=sorted(active_issues, key=_issue_sort_key),
        )

    def render_markdown_report(self, data: DiagnosisReportData) -> str:
        return render_markdown_report(data, self.settings)

    def _governance_appendix(self, version_id: int, review_batch_id: str | None) -> str:
        version = VersionRepository(self.settings).get_version(version_id) or {}
        parent_id = version.get("parent_version_id")
        issues = DiagnosisRepository(self.settings)
        current = issues.list_issues(version_id)
        before = issues.list_issues(int(parent_id)) if parent_id else []
        key = lambda item: (item.get("issue_type_code"), item.get("node_id"))
        before_keys, current_keys = {key(item) for item in before}, {key(item) for item in current}
        resolved = [item for item in before if key(item) not in current_keys or item.get("status") == "resolved"]
        unresolved = [item for item in current if key(item) in before_keys and item.get("status") not in {"resolved", "false_positive"}]
        added = [item for item in current if key(item) not in before_keys]
        deferred = [item for item in current if item.get("status") == "deferred"]
        suggestions = SuggestionRepository(self.settings).list_suggestions(review_batch_id=review_batch_id) if review_batch_id else []
        counts: dict[str, int] = {}
        for item in suggestions: counts[item.status] = counts.get(item.status, 0) + 1
        actions = [item.action_type for item in suggestions if item.status in {"approved", "executed"}]
        added_lines = "\n".join(
            f"  - {item.get('issue_type_label')}：{item.get('node_name') or '-'}；关联执行动作："
            f"{', '.join(s.action_type for s in suggestions if s.status in {'approved', 'executed'} and s.target_node_id == item.get('node_id')) or '未能自动关联'}"
            for item in added
        ) or "  - 无"
        release_allowed = version.get("lifecycle_status") in {"passed", "released"}
        return f"""

## 版本治理与复诊结论

- 基线版本：{parent_id or '无'}
- 当前版本：{version.get('version_no')}（ID {version_id}）
- 审核决策统计：{counts}
- 实际执行动作：{actions or ['无']}
- 修改前/后问题数量：{len(before)} / {len(current)}
- 已解决：{len(resolved)}；未解决：{len(unresolved)}；新增：{len(added)}；待确认：{len(deferred)}
- 复诊状态：{version.get('verification_status')}
- 生命周期状态：{version.get('lifecycle_status')}
- 是否允许发布：{'是' if release_allowed else '否'}
- 相邻版本质量：{(VersionRepository(self.settings).get_version(int(parent_id)) or {}).get('quality_score') if parent_id else '-'} → {version.get('quality_score')}
- 初始诊断模式/模型：{version.get('diagnosis_mode') or '历史数据未记录'} / {version.get('diagnosis_model') or '历史数据未记录'}
- AI 建议模式/模型：{'AI/规则混合' if any(item.analysis_run_id for item in suggestions) else '规则诊断'} / {version.get('diagnosis_model') or '历史数据未记录'}
- 复诊模式/模型：{version.get('verification_mode') or '确定性规则'} / {version.get('verification_model') or '未使用模型'}

### 新增问题与关联动作
{added_lines}
"""


def report_file_name(version: dict, report_type: str = "final") -> str:
    return f"{version['version_no']}_version-{version['id']}_{report_type}_report.md"


def build_issue_summary(structure_issues: list[dict], content_issues: list[dict]) -> dict[str, Any]:
    all_issues = [*structure_issues, *content_issues]
    risks = Counter(item.get("risk_level", "low") for item in all_issues)
    structure_groups = _group_issues(structure_issues)
    content_groups = _group_issues(content_issues)
    return {
        "total": len(all_issues),
        "structure_total": len(structure_issues),
        "content_total": len(content_issues),
        "high": risks["high"],
        "medium": risks["medium"],
        "low": risks["low"],
        "structure_groups": structure_groups,
        "content_groups": content_groups,
    }


def select_representative_cases(issues: list[dict], issue_groups: list[dict]) -> list[dict]:
    if not issues:
        return []
    common_missing_ids = {
        group["parent_id"] for group in issue_groups if group["kind"] == "missing_parent_group"
    }
    ranked = sorted(
        issues,
        key=lambda item: (
            RISK_ORDER.get(item.get("risk_level"), 3),
            0 if item.get("parent_id") in common_missing_ids else 1,
            -int(item.get("children_count") or 0),
            -float(item.get("confidence") or 0),
            int(item.get("id") or 0),
        ),
    )
    selected: list[dict] = []
    seen_types: set[str] = set()
    seen_missing_parents: set[int] = set()

    def add(item: dict) -> None:
        if item in selected:
            return
        if item["issue_type"] == "missing_parent" and item.get("parent_id") is not None:
            parent_id = int(item["parent_id"])
            if parent_id in seen_missing_parents:
                return
            seen_missing_parents.add(parent_id)
        selected.append(item)
        seen_types.add(item["issue_type"])

    # 先保证结构问题与内容问题都有代表，再按风险、影响范围和类型补足。
    for category_items in (
        [item for item in ranked if item["issue_type"] in STRUCTURE_TYPES],
        [item for item in ranked if item["issue_type"] not in STRUCTURE_TYPES],
    ):
        if category_items:
            add(category_items[0])
    for item in ranked:
        if item["issue_type"] not in seen_types:
            add(item)
        if len(selected) >= 8:
            break
    for item in ranked:
        if len(selected) >= min(5, len(issues)):
            break
        add(item)
    return selected[:8]


def analyze_common_root_causes(issues: list[dict]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    missing: dict[int, list[dict]] = defaultdict(list)
    for item in issues:
        if item["issue_type"] == "missing_parent" and item.get("parent_id") is not None:
            missing[int(item["parent_id"])].append(item)
    for parent_id, members in sorted(missing.items()):
        if len(members) > 1:
            groups.append({
                "kind": "missing_parent_group",
                "parent_id": parent_id,
                "members": members,
                "title": f"{len(members)} 个节点引用同一缺失父节点 {parent_id}",
            })

    paths: dict[str, list[dict]] = defaultdict(list)
    for item in issues:
        parts = _path_parts(item.get("path_names"))
        if len(parts) >= 2:
            paths[" > ".join(parts[:2])].append(item)
    for prefix, members in sorted(paths.items()):
        if len(members) >= 3 and len({item["id"] for item in members}) >= 3:
            groups.append({
                "kind": "subtree_group",
                "path_prefix": prefix,
                "members": members,
                "title": f"“{prefix}”路径集中出现 {len(members)} 项问题",
            })

    nodes: dict[int, list[dict]] = defaultdict(list)
    for item in issues:
        if item.get("node_id") is not None:
            nodes[int(item["node_id"])].append(item)
    for node_id, members in sorted(nodes.items()):
        if len({item["issue_type"] for item in members}) > 1:
            groups.append({
                "kind": "same_node_group",
                "node_id": node_id,
                "members": members,
                "title": f"节点 {node_id} 同时存在 {len(members)} 项不同问题",
            })
    return groups


def build_guidance_suggestions(issues: list[dict]) -> list[dict[str, Any]]:
    guidance = {
        "missing_parent": [
            "检查缺失父节点是否存在于原始数据或被导入过程遗漏。",
            "优先恢复遗漏父节点或修正错误的父节点引用。",
            "无法恢复时，由 AI 结合完整路径生成新的挂载节点或迁移方案。",
            "多个节点引用同一缺失父节点时，优先恢复共同父节点。",
        ],
        "bad_parent_child_relation": [
            "由 AI 结合父节点、兄弟节点和完整路径决定重命名、合并或移动方案。",
            "判断属于错误挂载，还是节点混合了多个概念。",
            "根据复核结果选择移动、拆分或重命名，并提交审核。",
        ],
        "synonym_pollution": [
            "删除与主名称不等价的词，并检查其是否应建立独立节点。",
            "不要把上位词、下位词或相关词直接作为同义词。",
        ],
        "synonym_format": [
            "删除与主名称重复、重复出现或为空的同义词。",
            "统一中英文符号、空格和分隔方式。",
        ],
        "synonym_format_issue": [
            "删除与主名称重复、重复出现或为空的同义词。",
            "统一中英文符号、空格和分隔方式。",
        ],
        "duplicate_name": ["结合完整路径核对同名节点，确认应合并、重命名还是保留。"],
        "semantic_duplicate": ["比较节点定义、路径和适用范围，确认是否合并或保留差异。"],
        "naming_irregular": ["按现有命名规范统一表达，重命名前确认下游引用影响。"],
        "inconsistent_granularity": ["对照同级节点范围，统一分类粒度或增加必要中间层。"],
        "vague_node": ["补充业务定义并明确分类边界，必要时拆分或重命名。"],
        "ambiguous_name": ["补充业务定义并明确分类边界，必要时拆分或重命名。"],
        "deep_level": ["复核超阈值路径是否可归并，并保留必要的业务层级。"],
        "wide_node": ["复核过宽节点的分类维度，必要时增加有业务含义的中间层。"],
        "orphan": ["恢复有效祖先路径，或将节点移动到经过确认的分类位置。"],
        "duplicate_mount": ["核对重复挂载来源，保留唯一权威路径并评估引用影响。"],
        "cycle_reference": ["立即解除循环祖先关系，并对受影响子树执行完整性复核。"],
        "circular_reference": ["立即解除循环祖先关系，并对受影响子树执行完整性复核。"],
    }
    result = []
    for issue_type in sorted({item["issue_type"] for item in issues}, key=_type_sort_key):
        actions = guidance.get(issue_type)
        if actions:
            result.append({"issue_type": issue_type, "label": _issue_label(issue_type), "actions": actions})
    return result


def build_quality_explanation(score: float | None, issues: list[dict]) -> dict[str, Any]:
    base_score = round(float(score), 2) if score is not None else None
    if base_score is None:
        base_level = "暂无法评价"
    elif base_score >= 90:
        base_level = "优秀"
    elif base_score >= 80:
        base_level = "良好"
    elif base_score >= 60:
        base_level = "一般"
    else:
        base_level = "较差"
    adjusted = "质量通过" if not issues else "需要整改"
    reason = "当前没有未解决问题" if not issues else f"当前仍有 {len(issues)} 项未解决问题"
    return {
        "base_score": base_score,
        "base_level": base_level,
        "risk_adjusted_level": adjusted,
        "risk_adjustment_reason": reason,
    }


def build_conclusion(stats: dict[str, int], summary: dict[str, Any], settings: Settings) -> str:
    traits = [f"当前体系共 {stats['node_count']} 个节点，最大层级为 {stats['max_depth']}"]
    absent = []
    existing_structure = {item["issue_type"] for item in summary["structure_groups"]}
    if "deep_level" not in existing_structure:
        absent.append("层级过深")
    if "wide_node" not in existing_structure:
        absent.append("节点过宽")
    if absent:
        traits.append(f"本次未发现明显的{'、'.join(absent)}问题")
    groups = [*summary["structure_groups"], *summary["content_groups"]]
    if not groups:
        traits.append("本次未发现需要登记的问题")
    else:
        main = "、".join(item["label"] for item in sorted(groups, key=lambda x: -x["count"])[:3])
        traits.append(f"主要问题集中在{main}")
        if summary["high"]:
            high_types = []
            for group in groups:
                if group["risk_level"] == "high":
                    high_types.append(group["label"])
            traits.append(f"应优先处理{'、'.join(dict.fromkeys(high_types))}等高风险问题")
    return "。".join(traits) + "。"


def build_next_actions(issues: list[dict]) -> dict[str, list[str]]:
    result = {"high": [], "medium": [], "low": []}
    for risk in result:
        grouped = Counter(item["issue_type"] for item in issues if item.get("risk_level") == risk)
        result[risk] = [
            f"处理 {count} 项{_issue_label(issue_type)}，由 AI 逐项核对证据、补全动作并提交安全预演。"
            for issue_type, count in sorted(grouped.items(), key=lambda pair: (-pair[1], pair[0]))
        ]
    return result


def render_markdown_report(data: DiagnosisReportData, settings: Settings) -> str:
    info, runtime = data.basic_info, data.runtime_info
    summary, stats = data.issue_summary, data.taxonomy_statistics
    score = _display_score(data)
    main_groups = sorted(
        [*summary["structure_groups"], *summary["content_groups"]],
        key=lambda item: (RISK_ORDER.get(item["risk_level"], 3), -item["count"]),
    )
    main_names = "、".join(item["label"] for item in main_groups[:2]) or "未发现集中问题"
    priority_name = main_groups[0]["label"] if main_groups else "定期复检"
    conclusion_level = _overall_conclusion(data)
    return f"""# 产品标准体系诊断报告

## 一、报告概述

- 文件名称：{info['file_name']}
- 体系版本：{info['version_no']}（版本 ID：{info['version_id']}）
- 报告生成时间：{info['generated_at']}
- 诊断模式：{info['diagnosis_mode']}
- 节点总数：{stats['node_count']}
- 综合评分：{score}

### 诊断结论

本次共检查 **{stats['node_count']}** 个节点，发现 **{summary['total']}** 个问题，其中高风险问题 **{summary['high']}** 个、中风险问题 **{summary['medium']}** 个、低风险问题 **{summary['low']}** 个。

当前体系主要存在{main_names}等问题。建议优先处理{priority_name}，修复完成后重新进行诊断。

---

## 二、体系基本情况

| 统计项目 | 数量 |
|---|---:|
| 节点总数 | {stats['node_count']} |
| 一级类目数 | {stats['root_count']} |
| 最大层级 | {stats['max_depth']} |
| 叶子节点数 | {stats['leaf_count']} |
| 非叶子节点数 | {stats['non_leaf_count']} |
| 最大直接子节点数 | {stats['max_children_count']} |
| 已配置同义词节点数 | {stats['synonym_non_empty_count']} |

---

## 三、诊断结果汇总

### 3.1 总体情况

{_render_summary_table(data)}

### 3.2 问题类型分布

{_render_issue_distribution(main_groups)}

---

## 四、重点问题说明

{_render_focus_issues(data, main_groups)}

---

## 五、AI分析情况

{_render_ai_analysis(data)}

---

## 六、问题处理建议

{_render_business_advice(data)}

---

## 七、处理计划

{_render_treatment_plan(data)}

---

## 八、最终结论

本次诊断发现，当前产品标准体系整体**{conclusion_level}**。

主要问题集中在{main_names}。建议首先处理{priority_name}，再逐步完成结构优化和内容规范化。

所有修改均在不可变副本上由 AI 生成方案，并经确定性校验和完整预演后执行；原版本保留，修改后使用相同诊断标准重新检查。

---

## 附录：完整问题清单

{_render_business_appendix(data.all_issues)}
"""


def _display_score(data: DiagnosisReportData) -> str:
    score = data.quality_result["base_score"]
    if not data.runtime_info["coverage_complete"] and data.runtime_info["ai_enabled"]:
        return f"暂不评级（当前暂存分数：{score:.2f}）" if score is not None else "暂不评级"
    return f"{score:.2f}/100（{data.quality_result['risk_adjusted_level']}）" if score is not None else "当前未记录"


def _risk_counts(issues: list[dict]) -> tuple[int, int, int]:
    counts = Counter(item.get("risk_level", "low") for item in issues)
    return counts["high"], counts["medium"], counts["low"]


def _render_summary_table(data: DiagnosisReportData) -> str:
    structure = _risk_counts(data.structure_issues)
    content = _risk_counts(data.content_issues)
    summary = data.issue_summary
    return "\n".join([
        "| 问题分类 | 问题数量 | 高风险 | 中风险 | 低风险 |",
        "|---|---:|---:|---:|---:|",
        f"| 结构问题 | {summary['structure_total']} | {structure[0]} | {structure[1]} | {structure[2]} |",
        f"| 内容问题 | {summary['content_total']} | {content[0]} | {content[1]} | {content[2]} |",
        f"| **合计** | **{summary['total']}** | **{summary['high']}** | **{summary['medium']}** | **{summary['low']}** |",
    ])


def _render_issue_distribution(groups: list[dict]) -> str:
    if not groups:
        return "本次未发现需要登记的问题。"
    rows = ["| 问题类型 | 数量 | 风险等级 | 问题说明 |", "|---|---:|---|---|"]
    for item in groups:
        rows.append(
            f"| {item['label']} | {item['count']} | {RISK_LABELS.get(item['risk_level'], item['risk_level'])} | {item['description']} |"
        )
    return "\n".join(rows)


def _render_focus_issues(data: DiagnosisReportData, groups: list[dict]) -> str:
    if not groups:
        return "当前没有需要重点说明的问题。"
    blocks = []
    for index, group in enumerate(groups[:4], 1):
        issues = [item for item in data.all_issues if item["issue_type"] == group["issue_type"]]
        impacts = sorted({impact for item in issues for impact in item.get("impact", [])})
        rows = ["| 节点名称 | 所在路径 | 问题说明 | 修改建议 |", "|---|---|---|---|"]
        for item in sorted(issues, key=_issue_sort_key)[:3]:
            values = [
                str(item.get("node_name") or item.get("node_id") or "未关联节点"),
                str(item.get("path_names") or "路径信息不足"),
                _shorten(item.get("reason") or item.get("evidence") or "需进一步确认", 150),
                _shorten(item.get("suggested_action") or "由 AI 补全可执行修改方案", 150),
            ]
            rows.append("| " + " | ".join(_escape_table(value) for value in values) + " |")
        blocks.append(
            f"### 4.{index} {group['label']}\n\n"
            f"- 问题数量：{group['count']}\n"
            f"- 风险等级：{RISK_LABELS.get(group['risk_level'], group['risk_level'])}\n"
            f"- 问题说明：{group['description']}\n"
            f"- 影响范围：{'、'.join(impacts) or '数据维护'}\n"
            f"- 处理原则：{_focus_principle(group['issue_type'])}\n\n"
            "典型问题：\n\n" + "\n".join(rows)
        )
    return "\n\n".join(blocks)


def _focus_principle(issue_type: str) -> str:
    guidance = build_guidance_suggestions([{"issue_type": issue_type}])
    return guidance[0]["actions"][0] if guidance else "由 AI 结合完整路径和产品语义生成可执行修改方案。"


def _metric(value: int | None) -> str:
    return str(value) if value is not None else "当前任务未记录"


def _render_ai_analysis(data: DiagnosisReportData) -> str:
    runtime, info = data.runtime_info, data.basic_info
    if not runtime["ai_enabled"]:
        discovery = "本次未启用 AI 分析，不能将未分析节点解释为 AI 确认正常。"
        scope = "未启用"
    elif runtime["report_nature"] == "降级报告":
        discovery = f"AI 分析因{runtime['stop_reason']}未完整完成；报告仅保留已写入的问题，未完成部分仍需复检。"
        scope = "候选节点语义复核（部分完成）"
    else:
        model_count = runtime["ai_issue_count"] if runtime["ai_issue_count"] is not None else runtime["model_content_count"]
        discovery = f"已记录 {model_count} 个经模型判断的问题，具体证据见重点问题与附录。"
        scope = "候选节点语义复核"
    return "\n".join([
        f"- AI分析范围：{scope}",
        f"- 抽取节点数量：{_metric(runtime['candidate_count'])}",
        f"- 成功分析数量：{_metric(runtime['completed_count'])}",
        f"- 确认问题数量：{_metric(runtime['ai_issue_count']) if runtime['ai_issue_count'] is not None else runtime['model_content_count']}",
        f"- 无法判断数量：{_metric(runtime['ai_inconclusive_count'])}",
        f"- 使用模型：{info['model_name']}",
        "",
        "### AI分析结论",
        "",
        "AI主要对节点名称、上下级关系、同义词和分类粒度进行语义分析。",
        "",
        f"本次AI分析发现：{discovery}",
        "",
        "AI 分析必须为每项有效问题给出产品语义判断和可执行修改方案；校验或预演失败的方案会保留原因并计入未解决问题。",
    ])


def _render_business_advice(data: DiagnosisReportData) -> str:
    by_risk = {risk: [item for item in data.all_issues if item.get("risk_level") == risk] for risk in ("high", "medium", "low")}
    priority = []
    if by_risk["high"]:
        priority.append("修复影响分类路径完整性或语义正确性的高风险问题。")
    if by_risk["medium"]:
        priority.append("复核中风险结构和内容问题，结合建议调整节点。")
    if data.runtime_info["ai_enabled"] and not data.runtime_info["coverage_complete"]:
        priority.append("对 AI 未完成分析的候选节点重新执行诊断。")
    if not priority:
        priority.append("保持当前规则配置，在数据更新后重新检查。")
    later = []
    actual_types = {item["issue_type"] for item in data.all_issues}
    if actual_types & {"deep_level", "wide_node"}:
        later.append("调整本次发现的层级或分支结构问题。")
    if actual_types & {"duplicate_name", "duplicate_mount", "semantic_duplicate"}:
        later.append("复核重复节点，确认合并、重命名或保留方案。")
    if actual_types & {"synonym_pollution", "synonym_format", "synonym_format_issue", "naming_irregular"}:
        later.append("清理不规范同义词并统一节点命名。")
    later.append("修复完成后重新诊断并对比结果。")
    text = "### 6.1 优先处理\n\n" + "\n".join(f"{i}. {value}" for i, value in enumerate(priority, 1))
    text += "\n\n### 6.2 后续优化\n\n" + "\n".join(f"{i}. {value}" for i, value in enumerate(later, 1))
    if data.persisted_suggestions:
        text += f"\n\n### 6.3 已生成的审核建议\n\n当前共有 **{len(data.persisted_suggestions)}** 条已保存建议：\n\n"
        text += "\n".join(
            f"- [{STATUS_LABELS.get(item.get('status'), item.get('status'))}] "
            f"{ACTION_LABELS.get(item.get('action_type'), item.get('action_type'))}："
            f"{item.get('suggestion') or item.get('reason') or '未记录建议内容'}"
            for item in data.persisted_suggestions
        )
    return text


def _render_treatment_plan(data: DiagnosisReportData) -> str:
    rows = [
        "| 优先级 | 处理内容 | 问题数量 | 处理方式 | 当前状态 |",
        "|---|---|---:|---|---|",
    ]
    configs = [("high", "高", "AI 二次复核并预演"), ("medium", "中", "AI 复核并预演"), ("low", "低", "批量规范化处理")]
    for risk, label, method in configs:
        items = [item for item in data.all_issues if item.get("risk_level") == risk]
        if not items:
            continue
        types = "、".join(dict.fromkeys(_issue_label(item["issue_type"]) for item in items))
        rows.append(f"| {label} | {types} | {len(items)} | {method} | 待处理 |")
    if len(rows) == 2:
        rows.append("| — | 当前无待处理问题 | 0 | 定期复检 | 无待处理项 |")
    return "\n".join(rows)


def _overall_conclusion(data: DiagnosisReportData) -> str:
    if data.issue_summary["high"] or data.quality_result["risk_adjusted_level"] in {"需要整改", "较差"}:
        return "需要重点治理"
    if data.issue_summary["total"]:
        return "存在一定问题"
    return "基本正常"


def _render_business_appendix(issues: list[dict]) -> str:
    if not issues:
        return "本次未发现问题，完整问题清单为空。"
    rows = [
        "| 序号 | 问题类型 | 风险等级 | 节点名称 | 所在路径 | 问题说明 | 修改建议 | 状态 |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for index, item in enumerate(sorted(issues, key=_issue_sort_key), 1):
        values = [
            str(index), _issue_label(item["issue_type"]),
            RISK_LABELS.get(item.get("risk_level"), str(item.get("risk_level"))),
            str(item.get("node_name") or item.get("node_id") or "未关联节点"),
            str(item.get("path_names") or "路径信息不足"),
            _shorten(item.get("reason") or item.get("evidence") or "需进一步确认", 160),
            _shorten(item.get("suggested_action") or "由 AI 补全可执行修改方案", 160),
            STATUS_LABELS.get(item.get("status"), str(item.get("status") or "待处理")),
        ]
        rows.append("| " + " | ".join(_escape_table(value) for value in values) + " |")
    return "\n".join(rows)


def _build_basic_info(version: dict, file_record: dict, task: dict | None) -> dict[str, Any]:
    ai_enabled = bool(task and task.get("enable_ai_analysis"))
    model = str(task.get("model_name") or "未使用 AI 模型") if task else "未使用 AI 模型"
    return {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "file_name": file_record.get("file_name") or f"文件 {version['file_id']}",
        "version_no": version["version_no"],
        "version_id": version["id"],
        "diagnosis_mode": "AI 增强模式" if ai_enabled else "规则诊断模式",
        "model_name": model if ai_enabled else "未使用 AI 模型",
        "scope": (
            "对全部节点执行结构和内容规则筛查，AI 对候选节点进行语义复核。"
            if ai_enabled
            else "对全部节点执行结构和内容规则筛查，本次未启用 AI 语义复核。"
        ),
    }


def _build_runtime_info(
    task: dict | None,
    task_result: dict[str, Any],
    total_nodes: int,
    issues: list[dict],
) -> dict[str, Any]:
    if task is None:
        return {
            "report_nature": "阶段性报告",
            "task_id": "未关联诊断任务",
            "terminal_status": "未关联",
            "terminal_reason": "当前版本未关联可追溯的诊断任务",
            "rules_completed": False,
            "ai_enabled": False,
            "candidate_count": None,
            "completed_count": None,
            "ai_issue_count": None,
            "ai_inconclusive_count": None,
            "ai_state": "未运行",
            "coverage_complete": False,
            "stop_reason": "未关联诊断任务",
            "rule_content_count": sum(item.get("source") == "content_rule" for item in issues),
            "model_content_count": sum(item.get("source") == "model_analysis" for item in issues),
        }
    status = str(task.get("status") or "pending")
    ai_enabled = bool(task.get("enable_ai_analysis"))
    warning = str(task_result.get("ai_warning") or task.get("error_message") or "").strip()
    ai_status = str(task_result.get("ai_analysis_status") or "")
    coverage = task_result.get("coverage") if isinstance(task_result.get("coverage"), dict) else {}
    degraded = status == "completed_degraded" or ai_status == "partial" or bool(warning)
    report_nature = "降级报告" if degraded else ("正式报告" if status == "completed" else "阶段性报告")
    terminal_labels = {
        "completed": "已完成",
        "completed_degraded": "降级完成",
        "failed": "失败",
        "running": "运行中",
        "pending": "等待运行",
        "cancelled": "已取消",
    }
    reason = _business_stop_reason(warning, status, ai_status)
    candidate_count = _optional_int_value(coverage.get("candidate_count", task_result.get("candidate_count")))
    completed_count = _optional_int_value(coverage.get("deep_diagnosed_count", task_result.get("ai_processed_count")))
    ai_issue_count = _optional_int_value(coverage.get("ai_issue_count", task_result.get("ai_issue_count")))
    ai_inconclusive_count = _optional_int_value(task_result.get("ai_inconclusive_count"))
    if not ai_enabled:
        ai_state = "本次未启用"
    elif degraded:
        ai_state = f"因{reason}提前停止，已保存完成部分"
    elif candidate_count == 0:
        ai_state = "候选数为 0，未执行深诊断"
    elif completed_count is not None:
        ai_state = f"已完成 {completed_count} 个候选"
    else:
        ai_state = "完成数未知"
    rules_completed = int(task.get("progress") or 0) >= 45 or status in {"completed", "completed_degraded"}
    coverage_complete = bool(coverage.get("coverage_complete")) if coverage else rules_completed and (
        not ai_enabled or (not degraded and candidate_count is not None and completed_count is not None and completed_count >= candidate_count)
    )
    return {
        "report_nature": report_nature,
        "task_id": task.get("id") or "未记录",
        "terminal_status": terminal_labels.get(status, status),
        "terminal_reason": reason,
        "rules_completed": rules_completed,
        "total_nodes": total_nodes,
        "ai_enabled": ai_enabled,
        "candidate_count": candidate_count,
        "completed_count": completed_count,
        "ai_issue_count": ai_issue_count,
        "ai_inconclusive_count": ai_inconclusive_count,
        "ai_state": ai_state,
        "coverage_complete": coverage_complete,
        "coverage": coverage,
        "stop_reason": reason,
        "rule_content_count": sum(item.get("source") == "content_rule" for item in issues),
        "model_content_count": sum(item.get("source") == "model_analysis" for item in issues),
    }


def _business_stop_reason(warning: str, status: str, ai_status: str) -> str:
    lowered = warning.lower()
    if "model_budget_exceeded" in lowered or "token" in lowered or "tokens" in lowered:
        return "模型 Token 预算耗尽"
    if "connection error" in lowered or "无法连接" in warning or "unreachable" in lowered:
        return "模型连接失败"
    if warning:
        return _shorten(warning, 120)
    if status == "failed":
        return "诊断任务执行失败"
    if ai_status == "partial":
        return "AI 分析未完整完成"
    if status == "completed":
        return "正常结束"
    return "诊断任务尚未结束"


def _optional_int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enrich_issues(settings: Settings, version_id: int, issues: list[dict]) -> list[dict]:
    taxonomy = TaxonomyRepository(settings)
    result = []
    for raw in issues:
        item = dict(raw)
        node = None
        if item.get("node_id") is not None:
            node = taxonomy.get_node_detail(version_id, int(item["node_id"]), include_deprecated=True)
        parent_id = node.get("parent_id") if node else None
        parent = "无父节点"
        if parent_id is not None:
            parent_node = taxonomy.get_node_detail(version_id, int(parent_id), include_deprecated=True)
            parent = (
                f"{parent_node['category_name']}（ID：{parent_id}）"
                if parent_node
                else f"ID：{parent_id}（当前版本中不存在）"
            )
        path = item.get("path") or (node.get("path_names") if node else None) or "路径信息不足"
        item.update(
            path_names=path,
            parent_id=parent_id,
            parent=parent,
            children_count=(len(taxonomy.get_children(version_id, int(item["node_id"]))) if item.get("node_id") is not None else 0),
            impact=_issue_impact(item["issue_type"]),
            suggested_action=_case_suggestion(item["issue_type"]),
        )
        result.append(item)
    return result


def _group_issues(issues: list[dict]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in issues:
        grouped[item["issue_type"]].append(item)
    result = []
    for issue_type, members in grouped.items():
        result.append({
            "issue_type": issue_type,
            "label": _issue_label(issue_type),
            "count": len(members),
            "risk_level": min((item.get("risk_level", "low") for item in members), key=lambda value: RISK_ORDER.get(value, 3)),
            "description": _issue_description(issue_type),
        })
    return sorted(result, key=lambda item: (RISK_ORDER.get(item["risk_level"], 3), -item["count"], item["label"]))


def _issue_label(issue_type: str) -> str:
    if issue_type not in ISSUE_LABELS:
        definition = get_issue_type(issue_type)
        if definition.code != "unknown" or issue_type == "unknown":
            return definition.label
        logger.warning("Report encountered unknown issue type: %s", issue_type)
        return f"{issue_type}（尚未配置中文说明）"
    return ISSUE_LABELS[issue_type]


def _issue_description(issue_type: str) -> str:
    if issue_type in ISSUE_DESCRIPTIONS:
        return ISSUE_DESCRIPTIONS[issue_type]
    definition = get_issue_type(issue_type)
    return definition.description if definition.code != "unknown" else "当前问题类型尚未配置中文说明，由 AI 结合保存的判断依据完成产品语义判断。"


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _type_sort_key(issue_type: str) -> tuple[int, str]:
    return (0 if issue_type in STRUCTURE_TYPES else 1, _issue_label(issue_type))


def _issue_sort_key(item: dict) -> tuple[Any, ...]:
    return (
        RISK_ORDER.get(item.get("risk_level"), 3),
        _issue_label(item.get("issue_type", "")),
        str(item.get("path_names") or ""),
        int(item.get("id") or 0),
    )


def _path_parts(path: Any) -> list[str]:
    if not path:
        return []
    return [part.strip() for part in str(path).replace(",", " > ").split(">") if part.strip()]


def _issue_impact(issue_type: str) -> list[str]:
    mapping = {
        "missing_parent": ["分类树结构", "路径检索", "产品统计", "版本更新"],
        "deep_level": ["路径检索", "数据维护"],
        "wide_node": ["分类树结构", "数据维护"],
        "duplicate_name": ["路径检索", "产品统计", "数据维护"],
        "orphan": ["分类树结构", "路径检索", "版本更新"],
        "duplicate_mount": ["分类树结构", "产品统计", "版本更新"],
        "cycle_reference": ["分类树结构", "路径检索", "版本更新"],
        "circular_reference": ["分类树结构", "路径检索", "版本更新"],
        "bad_parent_child_relation": ["分类树结构", "路径检索", "产品统计"],
        "synonym_pollution": ["同义词搜索", "路径检索"],
        "synonym_format": ["同义词搜索", "数据维护"],
        "synonym_format_issue": ["同义词搜索", "数据维护"],
        "semantic_duplicate": ["路径检索", "产品统计", "数据维护"],
        "inconsistent_granularity": ["产品统计", "数据维护"],
        "naming_irregular": ["路径检索", "数据维护"],
        "vague_node": ["路径检索", "产品统计", "数据维护"],
        "ambiguous_name": ["路径检索", "产品统计", "数据维护"],
    }
    return mapping.get(issue_type, ["数据维护"])


def _case_suggestion(issue_type: str) -> str:
    guidance = build_guidance_suggestions([{"issue_type": issue_type}])
    if not guidance:
        return "结合完整路径和业务资料进一步确认，确认后再制定维护动作。"
    return " ".join(f"{index}. {action}" for index, action in enumerate(guidance[0]["actions"], 1))


def _first_action(issues: list[dict]) -> str:
    if not issues:
        return "建议保持当前规则配置，并在数据更新后使用相同配置复查。"
    priority = {
        "cycle_reference": 0,
        "circular_reference": 0,
        "missing_parent": 1,
        "orphan": 2,
        "duplicate_mount": 3,
        "bad_parent_child_relation": 4,
    }
    highest = min(
        issues,
        key=lambda item: (
            RISK_ORDER.get(item.get("risk_level"), 3),
            priority.get(item.get("issue_type"), 9),
            int(item.get("id") or 0),
        ),
    )
    if highest["issue_type"] == "missing_parent":
        return "建议优先修复分类路径断裂，再处理内容质量问题。"
    return f"建议优先复核{_issue_label(highest['issue_type'])}，确认后再进入维护审核。"


def _render_taxonomy_analysis(stats: dict[str, int], settings: Settings) -> str:
    total = stats["node_count"]
    leaf_ratio = stats["leaf_count"] / total * 100 if total else 0
    synonym_ratio = stats["synonym_non_empty_count"] / total * 100 if total else 0
    depth = (
        f"最大层级为 {stats['max_depth']}，超过当前层级过深阈值 {settings.max_tree_depth_threshold}。"
        if stats["max_depth"] > settings.max_tree_depth_threshold
        else f"最大层级为 {stats['max_depth']}，未超过当前层级过深阈值 {settings.max_tree_depth_threshold}。"
    )
    width = (
        f"最大直接子节点数为 {stats['max_children_count']}，超过当前节点过宽阈值 {settings.max_children_threshold}。"
        if stats["max_children_count"] > settings.max_children_threshold
        else f"最大直接子节点数为 {stats['max_children_count']}，未超过当前节点过宽阈值 {settings.max_children_threshold}。"
    )
    return "\n\n".join([
        f"- 叶子节点占比为 {leaf_ratio:.1f}%，当前统计显示末级节点占体系主体。",
        f"- 同义词非空节点占比为 {synonym_ratio:.1f}%；覆盖情况仅表示是否填写，具体质量以内容诊断为准。",
        f"- {depth}",
        f"- {width}",
    ])


def _render_group_table(groups: list[dict], category: str) -> str:
    if not groups:
        return f"本次未发现{category}问题。"
    rows = ["| 问题类型 | 数量 | 风险等级 | 问题说明 |", "|---|---:|---|---|"]
    for item in groups:
        rows.append(f"| {item['label']} | {item['count']} | {RISK_LABELS.get(item['risk_level'], item['risk_level'])} | {item['description']} |")
    rows.append(f"| **合计** | **{sum(item['count'] for item in groups)}** | — | 与{category}问题总数一致 |")
    return "\n".join(rows)


def _render_group_analysis(groups: list[dict], issues: list[dict]) -> str:
    if not groups:
        return "本次未发现需要展开分析的问题。"
    lines = []
    for group in groups:
        examples = [item for item in issues if item["issue_type"] == group["issue_type"]]
        evidence = next((item.get("reason") or item.get("evidence") for item in examples if item.get("reason") or item.get("evidence")), "需结合业务资料进一步确认")
        lines.append(f"- **{group['label']}**：{group['description']} 本次保存的判断依据示例为：{_shorten(evidence, 180)}")
    return "\n".join(lines)


def _render_cases(cases: list[dict]) -> str:
    if not cases:
        return "本次未发现问题，因此没有需要展示的典型案例。"
    numerals = "一二三四五六七八"
    blocks = []
    for index, item in enumerate(cases):
        evidence = item.get("evidence") or item.get("reason") or "证据不足，需结合业务资料进一步确认"
        analysis = item.get("reason") or item.get("description") or "需结合业务资料进一步确认"
        blocks.append(f"""### 案例{numerals[index]}：{_issue_label(item['issue_type'])}——{item.get('node_name') or '未关联节点'}

- 问题类型：{_issue_label(item['issue_type'])}
- 风险等级：{RISK_LABELS.get(item.get('risk_level'), item.get('risk_level'))}
- 节点 ID：{item.get('node_id') if item.get('node_id') is not None else '未关联'}
- 节点名称：{item.get('node_name') or '未记录'}
- 完整路径：{item.get('path_names') or '路径信息不足'}
- 父节点：{item.get('parent')}
- 子节点数量：{item.get('children_count', 0)}
- 判断依据：{evidence}

#### 问题分析

{analysis}

#### 影响

可能影响：{'、'.join(item.get('impact') or ['数据维护'])}。

#### 处理建议

{item.get('suggested_action')}
""")
    return "\n\n".join(blocks)


def _render_root_causes(groups: list[dict]) -> str:
    if not groups:
        return "当前未发现明显的批量共同根因，问题需逐项处理。"
    blocks = []
    for index, group in enumerate(groups, 1):
        members = group["members"]
        if group["kind"] == "missing_parent_group":
            names = "、".join(str(item.get("node_name") or item.get("node_id")) for item in members[:6])
            more = f"等 {len(members)} 个节点" if len(members) > 6 else ""
            text = (
                f"{names}{more}均引用父节点 {group['parent_id']}，但当前版本不存在该父节点。"
                "这更可能是共同父节点数据遗漏，而不是多个子节点分别挂载错误。"
                "建议优先检查并恢复共同父节点，不建议在根因未确认前分别移动多个子节点。"
            )
        elif group["kind"] == "subtree_group":
            text = (
                f"“{group['path_prefix']}”路径共发现 {len(members)} 项问题，"
                "建议检查该子树的原始数据和导入完整性，再逐项复核。"
            )
        else:
            types = "、".join(dict.fromkeys(_issue_label(item["issue_type"]) for item in members))
            text = (
                f"节点 {group['node_id']} 同时存在{types}。应在一次审核中合并查看其路径、名称和同义词，"
                "避免把相关问题当作彼此独立的维护事项。"
            )
        blocks.append(f"### {index}. {group['title']}\n\n{text}")
    return "\n\n".join(blocks)


def _suggestion_to_dict(item: Any) -> dict[str, Any]:
    return item.model_dump() if hasattr(item, "model_dump") else dict(item)


def _render_suggestions(persisted: list[dict], guidance: list[dict], issue_count: int) -> str:
    blocks = ["### 8.1 已持久化的正式修改方案"]
    if persisted:
        blocks.append(f"当前共有 **{len(persisted)} 条**正式修改方案，执行前均经过确定性校验和完整预演。")
        rows = ["| 序号 | 建议内容 | 风险 | 状态 |", "|---:|---|---|---|"]
        for index, item in enumerate(persisted, 1):
            rows.append(
                f"| {index} | {item.get('suggestion') or item.get('reason') or '未记录'} | "
                f"{RISK_LABELS.get(item.get('risk_level'), item.get('risk_level'))} | "
                f"{STATUS_LABELS.get(item.get('status'), item.get('status'))} |"
            )
        blocks.append("\n".join(rows))
    else:
        blocks.append("当前尚未生成可直接审核和执行的正式建议。")
    blocks.append("### 8.2 根据诊断问题生成的处理方向")
    if issue_count == 0:
        blocks.append("本次未发现问题，因此不生成与诊断结果无关的处理方向。")
    elif guidance:
        if not persisted:
            blocks.append("以下内容为根据诊断结果生成的候选处理方向；AI 必须补全具体动作并通过校验后才能执行。")
        for index, item in enumerate(guidance, 1):
            blocks.append(f"#### 8.2.{index} {item['label']}\n\n" + "\n".join(f"- {action}" for action in item["actions"]))
    else:
        blocks.append("当前问题类型尚无完整方案，必须进入 AI 深度分析并补全具体动作。")
    return "\n\n".join(blocks)


def _render_quality(result: dict[str, Any]) -> str:
    score = "当前版本未保存基础评分" if result["base_score"] is None else f"{result['base_score']:.2f}/100"
    return (
        f"- 基础质量评分：**{score}**\n"
        f"- 当前评价等级：**{result['base_level']}**\n"
        f"- 风险修正结论：**{result['risk_adjusted_level']}**\n"
        f"- 风险修正原因：{result['risk_adjustment_reason']}\n\n"
        "基础评分主要反映当前版本保存的数量型质量结果；风险修正结论进一步考虑高风险问题类型和结构可用性。"
        "两者应同时阅读，较高的基础分不代表体系不存在必须处理的高风险问题。"
    )


def _render_next_actions(actions: dict[str, list[str]]) -> str:
    labels = [("high", "第一优先级"), ("medium", "第二优先级"), ("low", "第三优先级")]
    blocks = []
    for risk, title in labels:
        rows = actions[risk]
        blocks.append(f"### {title}\n\n" + ("\n".join(f"- {row}" for row in rows) if rows else f"本次没有{RISK_LABELS[risk]}问题。"))
    return "\n\n".join(blocks)


def _build_version_changes(settings: Settings, version: dict) -> dict[str, Any]:
    with connect(settings) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT operation_type, operation_detail, created_time FROM operation_log WHERE version_id = ? ORDER BY id",
            (version["id"],),
        ).fetchall()]
    counts = Counter(row["operation_type"] for row in rows)
    base_version = None
    for row in rows:
        detail = _load_json(row.get("operation_detail"))
        base_version = base_version or detail.get("base_version_no") or detail.get("source_version_no")
    return {
        "base_version": base_version,
        "current_version": version["version_no"],
        "operations": rows,
        "counts": counts,
    }


def _render_version_changes(changes: dict[str, Any]) -> str:
    operations = changes["operations"]
    if not operations:
        return "当前版本尚未执行维护动作，暂无版本变更记录。"
    counts = changes["counts"]
    aliases = {
        "add_node": "新增节点",
        "move_node": "移动节点",
        "rename_node": "重命名节点",
        "merge_node": "合并节点",
        "clean_synonym": "同义词修改",
    }
    lines = [
        f"- 基础版本：{changes['base_version'] or '当前记录未包含基础版本号'}",
        f"- 当前版本：{changes['current_version']}",
        f"- 执行动作数量：{len(operations)}",
    ]
    for action, label in aliases.items():
        lines.append(f"- {label}：{counts.get(action, 0)}")
    times = [str(item.get("created_time")) for item in operations if item.get("created_time")]
    lines.append(f"- 执行时间：{times[-1] if times else '当前记录未包含执行时间'}")
    return "\n".join(lines)


def _render_appendix(issues: list[dict]) -> str:
    if not issues:
        return "本次未发现问题，完整问题列表为空。"
    rows = [
        "| 序号 | 问题类型 | 风险 | 节点 ID | 节点名称 | 完整路径 | 判断依据 | 处理状态 |",
        "|---:|---|---|---:|---|---|---|---|",
    ]
    for index, item in enumerate(issues, 1):
        evidence = item.get("evidence") or item.get("reason") or "需进一步确认"
        values = [
            str(index),
            _issue_label(item["issue_type"]),
            RISK_LABELS.get(item.get("risk_level"), str(item.get("risk_level"))),
            str(item.get("node_id") if item.get("node_id") is not None else "—"),
            str(item.get("node_name") or "未记录"),
            str(item.get("path_names") or "路径信息不足"),
            _shorten(str(evidence), 180),
            STATUS_LABELS.get(item.get("status"), str(item.get("status") or "待处理")),
        ]
        rows.append("| " + " | ".join(_escape_table(value) for value in values) + " |")
    return "\n".join(rows)


def _load_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _shorten(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
