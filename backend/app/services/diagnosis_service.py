from collections import defaultdict

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
        "duplicate_sibling",
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
        for key in ("missing_parent", "excessive_depth", "excessive_width", "duplicate_sibling"):
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
                    reason="名称过于宽泛，需要由 AI 结合父级范围、同级节点和子节点明确产品分类边界",
                    risk_level="low", confidence=1.0, path=path,
                    evidence=f"名称命中确定性模糊词规则：{name}", source="content_rule",
                ))
            synonyms = _split_synonyms(node.get("syn_list"))
            normalized = [item.casefold().strip() for item in synonyms if item.strip()]
            raw_synonyms = str(node.get("syn_list") or "")
            synonym_format_reasons: list[str] = []
            if name.casefold() in normalized:
                synonym_format_reasons.append("包含节点主名称")
            if len(normalized) != len(set(normalized)):
                synonym_format_reasons.append("存在重复值")
            if "\n" in raw_synonyms or "\r" in raw_synonyms:
                synonym_format_reasons.append("包含换行")
            if synonym_format_reasons:
                issues.append(DiagnosisIssueRecord(
                    issue_type="synonym_format", node_id=int(node["category_id"]),
                    node_name=name, description="同义词格式不规范",
                    reason="同义词列表" + "、".join(synonym_format_reasons),
                    risk_level="low", confidence=1.0, path=path,
                    evidence=f"原始同义词：{node.get('syn_list') or ''}", source="content_rule",
                ))
            child_names = {str(item["category_name"]).strip() for item in by_parent.get(int(node["category_id"]), [])}
            overlapping = [term for term in synonyms if term in child_names]
            if overlapping:
                issues.append(DiagnosisIssueRecord(
                    issue_type="synonym_overlap",
                    node_id=int(node["category_id"]), node_name=name,
                    description="父节点同义词包含子节点具体类型或范围过宽的词",
                    reason="同义词会扩大父节点语义边界并与下级分类重叠", risk_level="medium", confidence=1.0,
                    path=path, evidence=f"建议删除：{', '.join(overlapping)}", source="content_rule",
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
        issues: list[DiagnosisIssueRecord] = []
        for node in nodes:
            depth = int(node["level"] or 0)
            if not bool(node.get("is_leaf")) or depth <= max_depth:
                continue
            excess = depth - max_depth
            risk_level = "low" if excess == 1 else "medium" if excess == 2 else "high"
            issues.append(DiagnosisIssueRecord(
                issue_type="excessive_depth",
                node_id=int(node["category_id"]),
                node_name=node["category_name"],
                description=f"叶路径长度为 {depth}，超过阈值 {max_depth}",
                reason=f"该根到叶路径需要减少 {excess} 层",
                risk_level=risk_level,
                confidence=1.0,
                path=str(node.get("path_names") or node["category_name"]),
                evidence=f"实际路径长度：{depth}；固定阈值：{max_depth}；需减少层数：{excess}",
            ))
        return issues

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
        issues: list[DiagnosisIssueRecord] = []
        for parent_id, count in child_counts.items():
            if count <= max_children:
                continue
            minimum_groups = (count + max_children - 1) // max_children
            risk_level = "low" if minimum_groups == 2 else "medium" if minimum_groups == 3 else "high"
            issues.append(DiagnosisIssueRecord(
                issue_type="excessive_width",
                node_id=parent_id,
                node_name=node_names.get(parent_id),
                description=f"节点直接子节点数量为 {count}，超过阈值 {max_children}",
                reason=f"至少需要拆分为 {minimum_groups} 个中间分组",
                risk_level=risk_level,
                confidence=1.0,
                evidence=f"直接子节点数：{count}；单组上限：{max_children}；最少分组数：{minimum_groups}",
            ))
        return issues

    def _duplicate_name_issues(self, nodes: list[dict]) -> list[DiagnosisIssueRecord]:
        siblings: dict[tuple[int | None, str], list[dict]] = defaultdict(list)
        for node in nodes:
            name = str(node["category_name"] or "").strip()
            siblings[(node.get("parent_id"), name)].append(node)
        issues: list[DiagnosisIssueRecord] = []
        for (_, name), duplicates in sorted(siblings.items(), key=lambda item: (str(item[0][0]), item[0][1])):
            if len(duplicates) < 2:
                continue
            ordered = sorted(duplicates, key=lambda item: int(item["category_id"]))
            retained = ordered[0]
            ids = ", ".join(str(item["category_id"]) for item in ordered)
            for duplicate in ordered[1:]:
                issues.append(DiagnosisIssueRecord(
                    issue_type="duplicate_sibling",
                    node_id=int(duplicate["category_id"]),
                    node_name=name,
                    description=f"同一父节点下名称「{name}」重复，节点 ID：{ids}",
                    reason=f"保留候选节点为 {retained['category_id']}，其余节点需合并或重命名",
                    risk_level="high",
                    confidence=1.0,
                    path=str(duplicate.get("path_names") or name),
                    evidence=f"同级重复节点：{ids}",
                ))
        return issues


def _split_synonyms(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip().strip("[]")
    if not text:
        return []
    return [item.strip().strip("'\"") for item in text.replace("；", ",").replace(";", ",").split(",") if item.strip()]
