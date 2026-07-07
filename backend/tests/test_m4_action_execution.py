from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.action_service import ActionService
from backend.app.services.version_service import VersionService


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _seed_version(settings: Settings) -> int:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(
        file_id=1,
        version_no="v1.0",
        description="test",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=10,
                category_name="食品",
                parent_id=None,
                level=1,
                path_ids="10",
                path_names="食品",
                syn_list=None,
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=20,
                category_name="水果",
                parent_id=10,
                level=2,
                path_ids="10,20",
                path_names="食品 > 水果",
                syn_list=None,
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=21,
                category_name="苹果",
                parent_id=20,
                level=3,
                path_ids="10,20,21",
                path_names="食品 > 水果 > 苹果",
                syn_list="AirPods, iPhone, 红富士",
                is_leaf=1,
            ),
            TaxonomyNodeRecord(
                category_id=30,
                category_name="饮料",
                parent_id=10,
                level=2,
                path_ids="10,30",
                path_names="食品 > 饮料",
                syn_list=None,
                is_leaf=1,
            ),
        ],
    )
    return version_id


def _create_issue(settings: Settings, version_id: int, node_id: int, issue_type: str) -> int:
    return DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type=issue_type,
            node_id=node_id,
            node_name="测试节点",
            description=f"{issue_type} 测试问题",
            reason="测试原因",
            risk_level="medium",
            confidence=0.9,
        ),
    )


def _create_approved_suggestion(
    settings: Settings,
    *,
    review_batch_id: str,
    version_id: int,
    issue_id: int,
    action_type: str,
    target_node_id: int,
    payload: dict,
    new_name: str | None = None,
    new_parent_id: int | None = None,
) -> int:
    suggestion_id = SuggestionRepository(settings).create_suggestion(
        review_batch_id=review_batch_id,
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id,
            version_id=version_id,
            action_type=action_type,
            target_node_id=target_node_id,
            target_node_name="测试节点",
            new_name=new_name,
            new_parent_id=new_parent_id,
            action_payload=payload,
            reason="测试原因",
            suggestion="测试建议",
            risk_level="medium",
            confidence=0.9,
            need_confirm=True,
        ),
    )
    SuggestionRepository(settings).update_status(suggestion_id, "approved")
    return suggestion_id


def test_clean_synonym_generates_new_version_without_changing_base(tmp_path):
    settings = _settings(tmp_path)
    base_version_id = _seed_version(settings)
    issue_id = _create_issue(settings, base_version_id, 21, "synonym_pollution")
    review_batch_id = "batch-clean"
    _create_approved_suggestion(
        settings,
        review_batch_id=review_batch_id,
        version_id=base_version_id,
        issue_id=issue_id,
        action_type="clean_synonym",
        target_node_id=21,
        payload={"synonyms_to_remove": ["AirPods", "iPhone"]},
    )

    execute_result = ActionService(settings).execute_actions(base_version_id, review_batch_id)
    save_result = VersionService(settings).save_new_version(
        base_version_id=base_version_id,
        review_batch_id=review_batch_id,
        nodes=execute_result.nodes,
    )

    assert execute_result.executed_count == 1
    assert execute_result.failed_count == 0
    assert save_result.new_version_no == "v1.1"

    base_node = TaxonomyRepository(settings).get_node_detail(base_version_id, 21)
    new_node = TaxonomyRepository(settings).get_node_detail(save_result.new_version_id, 21)
    assert base_node["syn_list"] == "AirPods, iPhone, 红富士"
    assert new_node["syn_list"] == "红富士"

    statuses = SuggestionRepository(settings).list_suggestions(review_batch_id=review_batch_id)
    assert [item.status for item in statuses] == ["executed"]
    with connect(settings) as connection:
        log_count = connection.execute("SELECT COUNT(*) FROM operation_log").fetchone()[0]
    assert log_count >= 1


def test_rename_node_recomputes_descendant_path_names(tmp_path):
    settings = _settings(tmp_path)
    base_version_id = _seed_version(settings)
    issue_id = _create_issue(settings, base_version_id, 20, "naming_irregular")
    review_batch_id = "batch-rename"
    _create_approved_suggestion(
        settings,
        review_batch_id=review_batch_id,
        version_id=base_version_id,
        issue_id=issue_id,
        action_type="rename_node",
        target_node_id=20,
        payload={"new_name": "鲜果"},
        new_name="鲜果",
    )

    execute_result = ActionService(settings).execute_actions(base_version_id, review_batch_id)
    save_result = VersionService(settings).save_new_version(
        base_version_id=base_version_id,
        review_batch_id=review_batch_id,
        nodes=execute_result.nodes,
    )

    renamed = TaxonomyRepository(settings).get_node_detail(save_result.new_version_id, 20)
    child = TaxonomyRepository(settings).get_node_detail(save_result.new_version_id, 21)
    assert renamed["category_name"] == "鲜果"
    assert renamed["path_names"] == "食品 > 鲜果"
    assert child["path_names"] == "食品 > 鲜果 > 苹果"


def test_move_node_to_own_subtree_is_rejected_and_no_version_created(tmp_path):
    settings = _settings(tmp_path)
    base_version_id = _seed_version(settings)
    issue_id = _create_issue(settings, base_version_id, 20, "bad_parent_child_relation")
    review_batch_id = "batch-invalid-move"
    _create_approved_suggestion(
        settings,
        review_batch_id=review_batch_id,
        version_id=base_version_id,
        issue_id=issue_id,
        action_type="move_node",
        target_node_id=20,
        payload={"new_parent_id": 21},
        new_parent_id=21,
    )

    try:
        ActionService(settings).execute_actions(base_version_id, review_batch_id)
    except ValueError as exc:
        assert "校验失败" in str(exc)
    else:
        raise AssertionError("Expected invalid move_node to be rejected.")

    versions = VersionRepository(settings).list_versions(file_id=1)
    assert [item["version_no"] for item in versions] == ["v1.0"]
