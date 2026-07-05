from collections import Counter, defaultdict

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord, StructureDiagnosisResult


class DiagnosisService:
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
        )
        summary = DiagnosisRepository(self.settings).count_by_type(version_id)
        for key in ("missing_parent", "deep_level", "wide_node", "duplicate_name"):
            summary.setdefault(key, 0)
        return StructureDiagnosisResult(
            version_id=version_id,
            status="completed",
            issue_count=sum(summary.values()),
            summary=summary,
        )

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
                issue_type="deep_level",
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
                issue_type="wide_node",
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
                    issue_type="duplicate_name",
                    node_id=None,
                    node_name=name,
                    description=f"名称「{name}」重复出现，节点 ID：{ids}",
                    reason=f"同名节点路径样例：{paths}",
                    risk_level="medium",
                    confidence=1.0,
                )
            )
        return issues
