from backend.app.config import Settings
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.version import CreateVersionResult
from backend.app.services.taxonomy_service import TaxonomyService


class VersionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_initial_version(self, file_id: int) -> CreateVersionResult:
        version_repo = VersionRepository(self.settings)
        taxonomy_repo = TaxonomyRepository(self.settings)
        existing = version_repo.get_by_file_and_no(file_id, "v1.0")
        if existing and taxonomy_repo.count_nodes(int(existing["id"])) > 0:
            overview = TaxonomyService(self.settings).get_overview(int(existing["id"]))
            return CreateVersionResult(
                version_id=int(existing["id"]),
                file_id=file_id,
                version_no="v1.0",
                node_count=overview.node_count,
                root_count=overview.root_count,
                max_depth=overview.max_depth,
                max_children_count=overview.max_children_count,
            )

        taxonomy_service = TaxonomyService(self.settings)
        nodes = taxonomy_service.parse_tree_nodes(file_id)
        build_result = taxonomy_service._summarize(file_id, nodes)
        version_id = version_repo.create_version(
            file_id=file_id,
            version_no="v1.0",
            description="初始导入版本",
        )
        taxonomy_repo.bulk_insert_nodes(version_id=version_id, nodes=nodes)
        return CreateVersionResult(
            version_id=version_id,
            file_id=file_id,
            version_no="v1.0",
            node_count=build_result.node_count,
            root_count=build_result.root_count,
            max_depth=build_result.max_depth,
            max_children_count=build_result.max_children_count,
        )

    def get_version(self, version_id: int) -> dict | None:
        return VersionRepository(self.settings).get_version(version_id)
