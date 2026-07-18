from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.action_service import ActionService
from backend.app.services.version_service import VersionService


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def _seed(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(
        file_id=1, version_no="v1.0", description="test"
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="水果",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="水果",
                syn_list="AirPods, 红富士",
                is_leaf=1,
            )
        ],
    )
    issue_id = DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type="synonym_pollution",
            node_id=1,
            node_name="水果",
            description="同义词污染",
            reason="测试",
            risk_level="medium",
            confidence=0.9,
        ),
    )
    return version_id, issue_id


def test_eligible_suggestion_is_validated_executed_and_versioned(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)
    run_id = "run-1"
    suggestion_id = SuggestionRepository(settings).create_suggestion(
        analysis_run_id=run_id,
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id,
            version_id=version_id,
            action_type="clean_synonym",
            target_node_id=1,
            action_payload={"synonyms_to_remove": ["AirPods"]},
            reason="测试",
            suggestion="删除污染同义词",
            risk_level="medium",
            confidence=0.9,
        ),
    )

    actions = ActionService(settings)
    validations = actions.validate_automatic_actions(
        version_id, analysis_run_id=run_id
    )
    assert [item.valid for item in validations] == [True]
    assert SuggestionRepository(settings).get_suggestion(suggestion_id).status == "validated"

    executed = actions.execute_validated_actions(
        version_id, analysis_run_id=run_id, operator="agent"
    )
    saved = VersionService(settings).save_new_version(
        base_version_id=version_id,
        action_batch_id=executed.action_batch_id,
        nodes=executed.nodes,
        analysis_run_id=run_id,
    )
    assert saved.new_version_no == "v1.1"
    assert SuggestionRepository(settings).get_suggestion(suggestion_id).status == "executed"
    assert TaxonomyRepository(settings).get_node_detail(saved.new_version_id, 1)["syn_list"] == "红富士"


def test_ineligible_suggestion_is_skipped_without_blocking_eligible_actions(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)
    run_id = "run-2"
    repo = SuggestionRepository(settings)
    eligible = repo.create_suggestion(
        analysis_run_id=run_id,
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id,
            version_id=version_id,
            action_type="mark_as_valid",
            target_node_id=1,
            action_payload={"mark_reason": "测试"},
            reason="测试",
            suggestion="标记有效",
            risk_level="low",
            confidence=0.9,
        ),
    )
    skipped = repo.create_suggestion(
        analysis_run_id=run_id,
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id,
            version_id=version_id,
            action_type="mark_as_valid",
            target_node_id=1,
            action_payload={"mark_reason": "高风险"},
            reason="测试",
            suggestion="不应自动执行",
            risk_level="high",
            confidence=0.95,
        ),
    )

    validations = ActionService(settings).validate_automatic_actions(
        version_id, analysis_run_id=run_id
    )
    assert [item.suggestion_id for item in validations] == [eligible]
    assert repo.get_suggestion(eligible).status == "validated"
    assert repo.get_suggestion(skipped).status == "skipped"
