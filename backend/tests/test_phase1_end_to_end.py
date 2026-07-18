from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.schemas.workflow import StartWorkflowRequest
from backend.app.services.version_service import VersionService
from backend.app.services.workflow_context_service import WorkflowContextService


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def test_v11_can_be_maintained_into_v12_without_mutating_history(tmp_path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    versions = VersionRepository(settings)
    v10 = versions.create_version(file_id=1, version_no="v1.0")
    original = TaxonomyNodeRecord(
        category_id=1,
        category_name="原始",
        parent_id=None,
        level=1,
        path_ids="1",
        path_names="原始",
        is_leaf=1,
    )
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=v10, nodes=[original])
    service = VersionService(settings)
    v11_result = service.save_new_version(
        base_version_id=v10,
        action_batch_id="action-1",
        workflow_id="wf-1",
        analysis_run_id="run-1",
        nodes=[original.model_copy(update={"category_name": "第一次维护"})],
    )

    context = WorkflowContextService(settings).resolve(
        StartWorkflowRequest(mode="maintain", file_id=1)
    )
    assert context.base_version_id == v11_result.new_version_id

    v12_result = service.save_new_version(
        base_version_id=context.base_version_id,
        action_batch_id="action-2",
        workflow_id="wf-2",
        analysis_run_id="run-2",
        nodes=[original.model_copy(update={"category_name": "第二次维护"})],
    )

    assert v11_result.new_version_no == "v1.1"
    assert v12_result.new_version_no == "v1.2"
    assert TaxonomyRepository(settings).get_node_detail(v10, 1)["category_name"] == "原始"
    assert TaxonomyRepository(settings).get_node_detail(
        v11_result.new_version_id, 1
    )["category_name"] == "第一次维护"
    assert TaxonomyRepository(settings).get_node_detail(
        v12_result.new_version_id, 1
    )["category_name"] == "第二次维护"
    assert versions.get_version(v12_result.new_version_id)["parent_version_id"] == (
        v11_result.new_version_id
    )
