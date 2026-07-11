from collections import Counter

from backend.app.config import Settings
from backend.app.repositories.quality_repo import QualityRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.quality import EvaluationRole, QualityEvaluation, QualityMetrics


class QualityEvaluationService:
    SCORE_VERSION = "quality-v1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(
        self,
        *,
        workflow_id: str,
        analysis_run_id: str,
        version_id: int,
        evaluation_role: EvaluationRole,
    ) -> QualityEvaluation:
        version = VersionRepository(self.settings).get_version(version_id)
        if version is None:
            raise ValueError(f"Taxonomy version {version_id} was not found.")
        nodes = TaxonomyRepository(self.settings).list_nodes(version_id)
        if not nodes:
            raise ValueError("Quality evaluation requires a non-empty taxonomy snapshot.")

        node_count = len(nodes)
        node_map = {int(node["category_id"]): node for node in nodes}
        structural_nodes = self._structural_issue_nodes(nodes, node_map)
        deep_count = sum(1 for node in nodes if int(node.get("level") or 0) > 7)
        child_counts = Counter(
            int(node["parent_id"])
            for node in nodes
            if node.get("parent_id") is not None
        )
        wide_count = sum(1 for count in child_counts.values() if count > 80)
        sibling_names = Counter(
            (node.get("parent_id"), str(node.get("category_name") or "").strip())
            for node in nodes
        )
        duplicate_excess = sum(max(count - 1, 0) for count in sibling_names.values())
        naming_count = sum(1 for node in nodes if self._has_naming_issue(node))

        structural = _remaining(25.0, len(structural_nodes), node_count)
        hierarchy = _remaining(20.0, deep_count + wide_count, node_count)
        redundancy = _remaining(15.0, duplicate_excess, node_count)
        naming = _remaining(10.0, naming_count, node_count)
        semantic_available = False
        available_detector_families = 4
        total_detector_families = 5
        coverage_ratio = round(
            available_detector_families / total_detector_families,
            4,
        )
        coverage = round(10.0 * coverage_ratio, 2)
        dimensions = QualityMetrics(
            structural_integrity=structural,
            hierarchy_balance=hierarchy,
            semantic_consistency=0.0,
            redundancy=redundancy,
            naming_quality=naming,
            coverage_confidence=coverage,
        )
        available_dimensions = {
            "structural_integrity": True,
            "hierarchy_balance": True,
            "semantic_consistency": semantic_available,
            "redundancy": True,
            "naming_quality": True,
            "coverage_confidence": True,
        }
        available_points = 25.0 + 20.0 + 15.0 + 10.0 + 10.0
        evaluation = QualityEvaluation(
            version_id=version_id,
            workflow_id=workflow_id,
            analysis_run_id=analysis_run_id,
            evaluation_role=evaluation_role,
            total_score=round(sum(dimensions.model_dump().values()), 2),
            available_points=available_points,
            coverage_ratio=coverage_ratio,
            dimensions=dimensions,
            available_dimensions=available_dimensions,
            metrics={
                "node_count": node_count,
                "structural_issue_nodes": len(structural_nodes),
                "deep_nodes": deep_count,
                "wide_nodes": wide_count,
                "duplicate_excess": duplicate_excess,
                "naming_issues": naming_count,
                "vector_index_status": version.get("vector_index_status") or "unknown",
            },
            detector_versions={
                "structure": "quality-structure-v1",
                "hierarchy": "quality-hierarchy-v1",
                "redundancy": "quality-redundancy-v1",
                "naming": "quality-naming-v1",
            },
            narrative=(
                "quality-v1 deterministic evaluation; semantic consistency "
                "is unavailable until a versioned semantic detector is recorded."
            ),
        )
        stored = QualityRepository(self.settings).upsert(evaluation)
        VersionRepository(self.settings).update_quality_score(
            version_id,
            stored.total_score,
        )
        return stored

    def _structural_issue_nodes(
        self,
        nodes: list[dict],
        node_map: dict[int, dict],
    ) -> set[int]:
        issue_nodes: set[int] = set()
        for node in nodes:
            node_id = int(node["category_id"])
            parent_id = node.get("parent_id")
            if parent_id is not None and int(parent_id) not in node_map:
                issue_nodes.add(node_id)
                continue
            if self._has_cycle(node_id, node_map):
                issue_nodes.add(node_id)
                continue
            expected_path = self._expected_path_names(node_id, node_map)
            if expected_path and str(node.get("path_names") or "") != expected_path:
                issue_nodes.add(node_id)
        return issue_nodes

    def _has_cycle(self, node_id: int, node_map: dict[int, dict]) -> bool:
        seen = {node_id}
        current = node_map[node_id]
        while current.get("parent_id") is not None:
            parent_id = int(current["parent_id"])
            if parent_id in seen:
                return True
            if parent_id not in node_map:
                return False
            seen.add(parent_id)
            current = node_map[parent_id]
        return False

    def _expected_path_names(self, node_id: int, node_map: dict[int, dict]) -> str | None:
        names: list[str] = []
        seen: set[int] = set()
        current_id = node_id
        while current_id in node_map and current_id not in seen:
            seen.add(current_id)
            node = node_map[current_id]
            names.append(str(node.get("category_name") or ""))
            if node.get("parent_id") is None:
                return " > ".join(reversed(names))
            current_id = int(node["parent_id"])
        return None

    def _has_naming_issue(self, node: dict) -> bool:
        name = str(node.get("category_name") or "")
        if not name.strip() or name != name.strip() or len(name) > 80:
            return True
        synonyms = [
            item.strip()
            for item in str(node.get("syn_list") or "").replace("，", ",").split(",")
            if item.strip()
        ]
        normalized = [item.casefold() for item in synonyms]
        return len(normalized) != len(set(normalized)) or name.casefold() in normalized


def _remaining(max_points: float, issue_count: int, node_count: int) -> float:
    issue_ratio = min(issue_count / max(node_count, 1), 1.0)
    return round(max_points * (1.0 - issue_ratio), 2)
