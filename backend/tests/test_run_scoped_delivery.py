from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.agent_run import AgentRunRecord
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.agent_run_service import AgentRunService
from backend.app.services.report_service import ReportService


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        export_dir=tmp_path / "exports",
        report_dir=tmp_path / "reports",
    )


def _seed(settings: Settings) -> int:
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'products.xlsx','products.xlsx')"
        )
    version_id = VersionRepository(settings).create_version(
        file_id=1,
        version_no="v1.0",
        description="run scoped report",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="Product",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="Product",
                syn_list="Product,Alias,Alias",
                is_leaf=1,
            )
        ],
    )
    return version_id


def _issue(settings: Settings, version_id: int, issue_type: str, source: str) -> int:
    return DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type=issue_type,
            node_id=1,
            node_name="Product",
            description=f"{issue_type} detected",
            reason=f"{issue_type} evidence",
            risk_level="low",
            confidence=0.95,
            path="Product",
            source=source,
        ),
    )


def test_report_uses_current_workflow_and_analysis_run(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed(settings)
    rule_issue_id = _issue(settings, version_id, "synonym_format", "content_rule")
    _issue(settings, version_id, "semantic_duplicate", "model_analysis")
    current_ai_issue_id = _issue(settings, version_id, "naming_nonstandard", "model_analysis")

    workflow_id = "import_current"
    TaskRepository(settings).create_workflow_task(
        file_id=1,
        workflow_id=workflow_id,
        thread_id="taxonomy_workflow:import_current",
        enable_ai_analysis=True,
        model_provider="deepseek",
        model_name="deepseek-chat",
    )
    run_repo = AgentRunRepository(settings)
    run_id = run_repo.create_run(
        AgentRunRecord(
            workflow_id=workflow_id,
            agent_type="content_diagnosis",
            version_id=version_id,
            status="completed",
            model_profile="deepseek-chat",
            coverage={
                "candidate_count": 1,
                "deep_diagnosed_count": 1,
                "ai_issue_count": 1,
                "reasonable_count": 0,
                "ai_content_sample_score": 0,
                "ai_complete": True,
                "coverage_complete": True,
                "completion_status": "completed",
            },
        )
    )
    item_id = run_repo.upsert_work_item(run_id, "candidate", "1", {})
    run_repo.complete_work_item(
        item_id,
        status="succeeded",
        result_payload={"issues": [{"issue_id": f"issue_{current_ai_issue_id}"}]},
    )

    data = ReportService(settings).collect_report_data(
        version_id,
        workflow_id=workflow_id,
        run_id=run_id,
    )

    assert data.runtime_info["ai_enabled"] is True
    assert data.runtime_info["candidate_count"] == 1
    assert data.runtime_info["completed_count"] == 1
    assert data.basic_info["model_name"] == "deepseek-chat"
    assert {item["id"] for item in data.all_issues} == {rule_issue_id, current_ai_issue_id}


def test_suggestion_scope_only_includes_safe_rule_repairs(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed(settings)
    safe_rule_issue_id = _issue(settings, version_id, "synonym_format", "content_rule")
    ai_issue_id = _issue(settings, version_id, "naming_nonstandard", "model_analysis")

    run_repo = AgentRunRepository(settings)
    analysis_run_id = run_repo.create_run(
        AgentRunRecord(
            workflow_id="import_current",
            agent_type="content_diagnosis",
            version_id=version_id,
        )
    )
    item_id = run_repo.upsert_work_item(analysis_run_id, "candidate", "1", {})
    run_repo.complete_work_item(
        item_id,
        status="succeeded",
        result_payload={"issues": [{"issue_id": f"issue_{ai_issue_id}"}]},
    )

    prepared = AgentRunService(settings).prepare_suggestion_issues(
        workflow_id="import_current",
        version_id=version_id,
        analysis_run_id=analysis_run_id,
    )
    selected = [
        issue_id
        for work_item in run_repo.list_work_items(prepared["run_id"])
        for issue_id in work_item.input_payload["issue_ids"]
    ]

    assert safe_rule_issue_id in selected
    assert ai_issue_id not in selected
    assert selected == [safe_rule_issue_id]
