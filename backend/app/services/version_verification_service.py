from dataclasses import dataclass

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.services.diagnosis_service import DiagnosisService
from backend.app.services.vector_index_service import VectorIndexService
from backend.app.tools.export_tools import export_excel
from backend.app.services.quality_score_service import calculate_quality_score


@dataclass(frozen=True)
class VersionVerificationResult:
    version_id: int
    status: str
    quality_before: float
    quality_after: float
    quality_delta: float
    remaining_issue_count: int
    vector_index_status: str
    export_path: str


class VersionVerificationService:
    """Re-diagnose, score and export a newly created immutable version."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify(
        self,
        *,
        base_version_id: int,
        new_version_id: int,
        build_vector_index: bool = False,
    ) -> VersionVerificationResult:
        versions = VersionRepository(self.settings)
        if versions.get_version(base_version_id) is None:
            raise ValueError(f"Taxonomy version {base_version_id} was not found.")
        if versions.get_version(new_version_id) is None:
            raise ValueError(f"Taxonomy version {new_version_id} was not found.")
        versions.update_lifecycle(new_version_id, "verifying")

        diagnosis = DiagnosisService(self.settings)
        # Both versions use the same deterministic checks, making the comparison reproducible.
        for version_id in (base_version_id, new_version_id):
            diagnosis.run_structure_diagnosis(
                version_id,
                max_depth=self.settings.max_tree_depth_threshold,
                max_children=self.settings.max_children_threshold,
            )
            diagnosis.run_content_rule_diagnosis(version_id)

        diagnosis_repo = DiagnosisRepository(self.settings)
        base_issues = diagnosis_repo.list_issues(base_version_id)
        new_issues = diagnosis_repo.list_issues(new_version_id)
        identity = lambda item: (item.get("issue_type_code"), item.get("node_id"))
        dispositions = {identity(item): item.get("status") for item in base_issues if item.get("status") in {"deferred", "false_positive"}}
        for item in new_issues:
            if identity(item) in dispositions:
                diagnosis_repo.update_status(int(item["id"]), str(dispositions[identity(item)]))
                item["status"] = dispositions[identity(item)]
        quality_before = self._quality_score(base_version_id)
        quality_after = self._quality_score(new_version_id)
        export_path = export_excel(new_version_id, self.settings)
        vector_status = "not_requested"
        base_keys = {identity(item) for item in base_issues}
        active_new_issues = [item for item in new_issues if item.get("status") not in {"false_positive", "resolved"}]
        added = [item for item in active_new_issues if identity(item) not in base_keys]
        added_medium_high = [item for item in added if item.get("risk_level") in {"medium", "high"}]
        severe_structure = [item for item in added if item.get("issue_type_code") in {"missing_parent", "duplicate_sibling"}]
        unresolved = [item for item in active_new_issues if identity(item) in base_keys]
        status = "failed" if added_medium_high or severe_structure else ("partial" if unresolved else "passed")
        if build_vector_index:
            try:
                vector_status = VectorIndexService(self.settings).index_version(new_version_id).status
                if vector_status not in {"completed", "skipped"} and status != "failed":
                    status = "partial"
            except Exception:
                # Excel output and relational data remain usable when an optional vector backend is down.
                vector_status = "failed"
                if status != "failed":
                    status = "partial"

        remaining = len(active_new_issues)
        versions.update_verification(
            new_version_id,
            status=status,
            quality_score=quality_after,
            export_path=str(export_path),
        )
        versions.update_lifecycle(new_version_id, status)
        versions.update_model_metadata(
            new_version_id,
            verification_mode="deterministic_rules",
            verification_model=None,
        )
        return VersionVerificationResult(
            version_id=new_version_id,
            status=status,
            quality_before=quality_before,
            quality_after=quality_after,
            quality_delta=round(quality_after - quality_before, 1),
            remaining_issue_count=remaining,
            vector_index_status=vector_status,
            export_path=str(export_path),
        )

    def _quality_score(self, version_id: int) -> float:
        nodes = TaxonomyRepository(self.settings).list_nodes(version_id)
        issues = DiagnosisRepository(self.settings).list_issues(version_id)
        return calculate_quality_score(len(nodes), issues).score
