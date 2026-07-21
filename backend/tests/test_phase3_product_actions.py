import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.action import SplitSubtreePayload
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.action_service import ActionService
from backend.app.services.action_simulation_service import ActionSimulationService
from backend.app.services.version_service import VersionService
from backend.app.main import create_app
from backend.tests.test_m4_action_execution import _create_issue, _seed_version, _settings


def _suggest(settings, version_id, issue_id, action_type, target_id, payload, batch="phase3"):
    suggestion_id = SuggestionRepository(settings).create_suggestion(
        review_batch_id=batch,
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id, version_id=version_id, action_type=action_type,
            target_node_id=target_id, target_node_name="target", action_payload=payload,
            reason="阶段三治理", suggestion="执行结构治理", risk_level="high",
            confidence=0.95, need_confirm=True,
        ),
    )
    SuggestionRepository(settings).update_status(suggestion_id, "approved")
    return SuggestionRepository(settings).get_suggestion(suggestion_id)


def _add_second_child(settings, version_id):
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=[
        TaxonomyNodeRecord(category_id=22, category_name="梨", parent_id=20, level=3,
                           path_ids="10,20,22", path_names="食品 > 水果 > 梨", is_leaf=1)
    ])


def test_split_schema_rejects_duplicate_child_assignment():
    with pytest.raises(ValidationError):
        SplitSubtreePayload.model_validate({"groups": [
            {"name": "仁果", "child_ids": [21]}, {"name": "其他", "child_ids": [21]},
        ]})


def test_split_executes_complete_plan_and_simulation_does_not_write(tmp_path):
    settings = _settings(tmp_path); version_id = _seed_version(settings); _add_second_child(settings, version_id)
    issue_id = _create_issue(settings, version_id, 20, "wide_node")
    suggestion = _suggest(settings, version_id, issue_id, "split_subtree", 20, {"groups": [
        {"name": "苹果类", "child_ids": [21]}, {"name": "梨类", "child_ids": [22]},
    ]})
    before = TaxonomyRepository(settings).list_node_records(version_id, include_deprecated=True)
    preview = ActionSimulationService(settings).simulate(version_id, [suggestion])
    assert preview.valid and len(preview.diff.split) == 1 and len(preview.diff.added) == 2
    assert TaxonomyRepository(settings).list_node_records(version_id, include_deprecated=True) == before
    result = ActionService(settings).execute_suggestion_records(version_id=version_id, review_batch_id="phase3", approved=[suggestion])
    names = {item.category_name: item for item in result.nodes}
    assert names["苹果"].parent_id == names["苹果类"].category_id
    assert names["梨"].parent_id == names["梨类"].category_id


def test_merge_moves_children_unions_synonyms_and_preserves_old_version(tmp_path):
    settings = _settings(tmp_path); version_id = _seed_version(settings)
    issue_id = _create_issue(settings, version_id, 20, "semantic_duplicate")
    suggestion = _suggest(settings, version_id, issue_id, "merge_node", 20,
                          {"source_node_id": 20, "target_node_id": 30})
    result = ActionService(settings).execute_suggestion_records(version_id=version_id, review_batch_id="phase3", approved=[suggestion])
    saved = VersionService(settings).save_new_version(version_id, "phase3", result.nodes)
    assert TaxonomyRepository(settings).get_node_detail(version_id, 20) is not None
    assert TaxonomyRepository(settings).get_node_detail(saved.new_version_id, 20) is None
    assert TaxonomyRepository(settings).get_node_detail(saved.new_version_id, 21)["parent_id"] == 30


def test_deprecate_default_query_hides_node_and_cascade_hides_subtree(tmp_path):
    settings = _settings(tmp_path); version_id = _seed_version(settings)
    issue_id = _create_issue(settings, version_id, 20, "obsolete_node")
    suggestion = _suggest(settings, version_id, issue_id, "deprecate_node", 20,
                          {"reason": "过时", "child_strategy": "cascade_subtree"})
    result = ActionService(settings).execute_suggestion_records(version_id=version_id, review_batch_id="phase3", approved=[suggestion])
    saved = VersionService(settings).save_new_version(version_id, "phase3", result.nodes)
    assert TaxonomyRepository(settings).get_node_detail(saved.new_version_id, 20) is None
    assert TaxonomyRepository(settings).get_node_detail(saved.new_version_id, 21) is None
    assert TaxonomyRepository(settings).get_node_detail(saved.new_version_id, 20, include_deprecated=True)["node_status"] == "deprecated"


def test_delete_leaf_rejects_non_leaf_and_deletes_leaf_from_new_snapshot(tmp_path):
    settings = _settings(tmp_path); version_id = _seed_version(settings)
    issue_id = _create_issue(settings, version_id, 20, "redundant_node")
    invalid = _suggest(settings, version_id, issue_id, "delete_leaf_node", 20, {}, batch="invalid")
    with pytest.raises(ValueError, match="叶子"):
        ActionService(settings).execute_suggestion_records(version_id=version_id, review_batch_id="invalid", approved=[invalid])
    leaf_issue = _create_issue(settings, version_id, 30, "redundant_leaf")
    valid = _suggest(settings, version_id, leaf_issue, "delete_leaf_node", 30, {})
    result = ActionService(settings).execute_suggestion_records(version_id=version_id, review_batch_id="phase3", approved=[valid])
    assert 30 not in {item.category_id for item in result.nodes}
    assert TaxonomyRepository(settings).get_node_detail(version_id, 30) is not None


def test_collapse_intermediate_reparents_children_and_removes_only_middle_node(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_version(settings)
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=[
        TaxonomyNodeRecord(category_id=22, category_name="食品用途", parent_id=21, level=4, path_ids="10,20,21,22", path_names="食品 > 水果 > 苹果 > 食品用途", is_leaf=0),
        TaxonomyNodeRecord(category_id=23, category_name="消费场景", parent_id=22, level=5, path_ids="10,20,21,22,23", path_names="食品 > 水果 > 苹果 > 食品用途 > 消费场景", is_leaf=0),
        TaxonomyNodeRecord(category_id=24, category_name="家庭消费", parent_id=23, level=6, path_ids="10,20,21,22,23,24", path_names="食品 > 水果 > 苹果 > 食品用途 > 消费场景 > 家庭消费", is_leaf=0),
        TaxonomyNodeRecord(category_id=25, category_name="日常食用", parent_id=24, level=7, path_ids="10,20,21,22,23,24,25", path_names="食品 > 水果 > 苹果 > 食品用途 > 消费场景 > 家庭消费 > 日常食用", is_leaf=0),
        TaxonomyNodeRecord(category_id=26, category_name="鲜食方式", parent_id=25, level=8, path_ids="10,20,21,22,23,24,25,26", path_names="食品 > 水果 > 苹果 > 食品用途 > 消费场景 > 家庭消费 > 日常食用 > 鲜食方式", is_leaf=0),
        TaxonomyNodeRecord(category_id=27, category_name="直接食用", parent_id=26, level=9, path_ids="10,20,21,22,23,24,25,26,27", path_names="食品 > 水果 > 苹果 > 食品用途 > 消费场景 > 家庭消费 > 日常食用 > 鲜食方式 > 直接食用", is_leaf=1),
    ])
    issue_id = _create_issue(settings, version_id, 27, "excessive_depth")
    suggestion = _suggest(
        settings,
        version_id,
        issue_id,
        "collapse_intermediate_node",
        23,
        {"target_node_ids": [23, 24], "semantic_basis": "消费场景和家庭消费不构成必要独立分类边界，下级用途可直接归入食品用途。"},
    )

    preview = ActionSimulationService(settings).simulate(version_id, [suggestion])

    assert preview.valid
    by_id = {item.category_id: item for item in preview.nodes}
    assert 23 not in by_id and 24 not in by_id
    assert by_id[25].parent_id == 22
    assert by_id[27].level == 7
    assert TaxonomyRepository(settings).get_node_detail(version_id, 23) is not None


def test_review_preview_api_returns_diff_without_nodes(tmp_path):
    settings = _settings(tmp_path); version_id = _seed_version(settings); _add_second_child(settings, version_id)
    issue_id = _create_issue(settings, version_id, 20, "wide_node")
    suggestion = _suggest(settings, version_id, issue_id, "split_subtree", 20, {"groups": [
        {"name": "苹果类", "child_ids": [21]}, {"name": "梨类", "child_ids": [22]},
    ]})
    response = TestClient(create_app(settings)).post("/api/reviews/phase3/preview", json={"suggestion_ids": [suggestion.id]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True and len(payload["diff"]["split"]) == 1
    assert "nodes" not in payload
