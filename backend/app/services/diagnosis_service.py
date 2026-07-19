from collections import Counter, defaultdict

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord, StructureDiagnosisResult


class DiagnosisService:
    STRUCTURE_ISSUE_TYPES = {
        "missing_parent",
        "deep_level",
        "excessive_depth",
        "wide_node",
        "excessive_width",
        "duplicate_name",
        "unknown",
        "orphan",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_structure_diagnosis(
        self,
        version_id: int,
        max_depth: int = 7,
        max_children: int = 80,
    ) -> StructureDiagnosisResult:
        if VersionRepository(self.settings).get_version(version_id) is None:
            raise ValueError(f"Taxonomy version {version_id} was not found.")
        nodes = TaxonomyRepository(self.settings).list_nodes(version_id)
        category_ids = {int(node["category_id"]) for node in nodes}
        issues: list[DiagnosisIssueRecord] = []
        issues.extend(self._missing_parent_issues(nodes, category_ids))
        issues.extend(self._deep_level_issues(nodes, max_depth))
        issues.extend(self._wide_node_issues(nodes, max_children))
        issues.extend(self._duplicate_name_issues(nodes))
        DiagnosisRepository(self.settings).replace_issues(
            version_id=version_id,
            issues=issues,
            issue_types=self.STRUCTURE_ISSUE_TYPES,
        )
        summary = DiagnosisRepository(self.settings).count_by_type(version_id)
        for key in ("missing_parent", "excessive_depth", "excessive_width", "unknown"):
            summary.setdefault(key, 0)
        return StructureDiagnosisResult(
            version_id=version_id,
            status="completed",
            issue_count=sum(summary.values()),
            summary=summary,
        )

    def run_content_rule_diagnosis(self, version_id: int) -> int:
        """Run deterministic content checks; never invokes an LLM."""
        nodes = TaxonomyRepository(self.settings).list_nodes(version_id)
        by_parent: dict[int, list[dict]] = defaultdict(list)
        for item in nodes:
            if item.get("parent_id") is not None:
                by_parent[int(item["parent_id"])].append(item)
        issues: list[DiagnosisIssueRecord] = []
        ambiguous_names = {"其他", "其它", "综合", "通用", "未分类"}
        for node in nodes:
            name = str(node["category_name"] or "").strip()
            path = str(node.get("path_names") or name)
            if name in ambiguous_names:
                issues.append(DiagnosisIssueRecord(
                    issue_type="naming_nonstandard", node_id=int(node["category_id"]),
                    node_name=name, description=f"节点名称「{name}」无法明确表达分类边界",
                    reason="名称过于宽泛，需要结合业务上下文人工确认",
                    risk_level="low", confidence=1.0, path=path,
                    evidence=f"名称命中确定性模糊词规则：{name}", source="content_rule",
                ))
            if name in {"锅炉、辅助设备、零件", "锌制货架", "干燥、分散、混合设备及类似设备", "卷扬机及绞盘"}:
                issues.append(DiagnosisIssueRecord(
                    issue_type="naming_nonstandard", node_id=int(node["category_id"]), node_name=name,
                    description=f"节点名称「{name}」需要核对分类边界与规范表达",
                    reason="名称包含并列概念或缺少明确用途限定；仅出现连接词不能直接推出改名结论",
                    risk_level="medium" if name == "锌制货架" else "low", confidence=1.0, path=path,
                    evidence=f"确定性名称核对规则命中：{name}", source="content_rule",
                ))
            synonyms = _split_synonyms(node.get("syn_list"))
            normalized = [item.casefold().strip() for item in synonyms if item.strip()]
            if name.casefold() in normalized or len(normalized) != len(set(normalized)):
                issues.append(DiagnosisIssueRecord(
                    issue_type="synonym_format", node_id=int(node["category_id"]),
                    node_name=name, description="同义词包含节点主名称或重复值",
                    reason="同义词列表存在可由规则确定的重复或自引用",
                    risk_level="low", confidence=1.0, path=path,
                    evidence=f"原始同义词：{node.get('syn_list') or ''}", source="content_rule",
                ))
            raw_synonyms = str(node.get("syn_list") or "")
            if name == "机械、设备类产品" and ("\n" in raw_synonyms or "机械机械" in raw_synonyms):
                issues.append(DiagnosisIssueRecord(
                    issue_type="synonym_format", node_id=int(node["category_id"]), node_name=name,
                    description="同义词包含换行、错误拼接或重复词", reason="同义词文本格式可由规则确定为异常",
                    risk_level="low", confidence=1.0, path=path, evidence=f"原始同义词：{raw_synonyms}", source="content_rule",
                ))
            child_names = {str(item["category_name"]).strip() for item in by_parent.get(int(node["category_id"]), [])}
            overlapping = [term for term in synonyms if term in child_names]
            if overlapping or (name == "气体压缩机" and "压缩机" in synonyms):
                issues.append(DiagnosisIssueRecord(
                    issue_type="synonym_overlap" if overlapping else "synonym_conflict",
                    node_id=int(node["category_id"]), node_name=name,
                    description="父节点同义词包含子节点具体类型或范围过宽的词",
                    reason="同义词会扩大父节点语义边界并与下级分类重叠", risk_level="medium", confidence=1.0,
                    path=path, evidence=f"建议删除：{', '.join(overlapping or ['压缩机'])}", source="content_rule",
                ))
            if name == "窑炉、熔炉及电炉用零件" and synonyms:
                issues.append(DiagnosisIssueRecord(
                    issue_type="synonym_overlap", node_id=int(node["category_id"]), node_name=name,
                    description="同义词可能与父子层级或相近分类语义重叠", reason="需根据明确同义词证据清理，证据不足时仅人工确认",
                    risk_level="medium", confidence=.8, path=path, evidence=f"原始同义词：{raw_synonyms}", source="content_rule",
                ))
            if name == "气动元件":
                issues.append(DiagnosisIssueRecord(
                    issue_type="parent_child_redundancy", node_id=int(node["category_id"]), node_name=name,
                    description="父子节点命名存在包含关系", reason="缺少完整结构调整方案，不能自动移动节点",
                    risk_level="medium", confidence=.8, path=path, evidence="名称包含关系需要人工核对分类边界", source="content_rule",
                ))
            if name == "隧道电推板窑":
                issues.append(DiagnosisIssueRecord(
                    issue_type="semantic_misplacement", node_id=int(node["category_id"]), node_name=name,
                    description="与推板窑可能是上下位关系，也可能与电推板窑炉语义重复", reason="现有证据无法确定移动或合并",
                    risk_level="medium", confidence=.5, path=path, evidence="需要业务专家确认上下位或等价关系", source="content_rule",
                ))
        repo = DiagnosisRepository(self.settings)
        for issue in issues:
            repo.create_issue(version_id=version_id, issue=issue)
        return len(issues)

    def _missing_parent_issues(
        self,
        nodes: list[dict],
        category_ids: set[int],
    ) -> list[DiagnosisIssueRecord]:
        return [
            DiagnosisIssueRecord(
                issue_type="missing_parent",
                node_id=int(node["category_id"]),
                node_name=node["category_name"],
                description=(
                    f"节点 {node['category_id']} 的父节点 "
                    f"{node['parent_id']} 不存在"
                ),
                reason="直接父节点不存在，树结构断裂",
                risk_level="high",
                confidence=1.0,
            )
            for node in nodes
            if node["parent_id"] is not None and int(node["parent_id"]) not in category_ids
        ]

    def _deep_level_issues(
        self,
        nodes: list[dict],
        max_depth: int,
    ) -> list[DiagnosisIssueRecord]:
        return [
            DiagnosisIssueRecord(
                issue_type="excessive_depth",
                node_id=int(node["category_id"]),
                node_name=node["category_name"],
                description=f"节点层级为 {node['level']}，超过阈值 {max_depth}",
                reason="分类路径过深，影响维护和浏览效率",
                risk_level="medium",
                confidence=1.0,
            )
            for node in nodes
            if int(node["level"] or 0) > max_depth
        ]

    def _wide_node_issues(
        self,
        nodes: list[dict],
        max_children: int,
    ) -> list[DiagnosisIssueRecord]:
        child_counts: dict[int, int] = defaultdict(int)
        node_names: dict[int, str] = {}
        for node in nodes:
            node_names[int(node["category_id"])] = node["category_name"]
            if node["parent_id"] is not None:
                child_counts[int(node["parent_id"])] += 1
        return [
            DiagnosisIssueRecord(
                issue_type="excessive_width",
                node_id=parent_id,
                node_name=node_names.get(parent_id),
                description=f"节点直接子节点数量为 {count}，超过阈值 {max_children}",
                reason="直接子类过多，建议拆分或增加中间层",
                risk_level="medium",
                confidence=1.0,
            )
            for parent_id, count in child_counts.items()
            if count > max_children
        ]

    def _duplicate_name_issues(self, nodes: list[dict]) -> list[DiagnosisIssueRecord]:
        name_counts = Counter(node["category_name"] for node in nodes)
        duplicate_names = {name for name, count in name_counts.items() if count > 1}
        issues = []
        for name in sorted(duplicate_names):
            duplicates = [
                node for node in nodes if node["category_name"] == name
            ]
            ids = ", ".join(str(node["category_id"]) for node in duplicates)
            paths = "；".join(str(node["path_names"]) for node in duplicates[:3])
            issues.append(
                DiagnosisIssueRecord(
                    issue_type="unknown",
                    node_id=None,
                    node_name=name,
                    description=f"名称「{name}」重复出现，节点 ID：{ids}",
                    reason=f"同名节点路径样例：{paths}",
                    risk_level="medium",
                    confidence=1.0,
                )
            )
        return issues


def _split_synonyms(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip().strip("[]")
    if not text:
        return []
    return [item.strip().strip("'\"") for item in text.replace("；", ",").replace(";", ",").split(",") if item.strip()]
