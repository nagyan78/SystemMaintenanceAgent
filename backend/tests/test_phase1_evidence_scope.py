from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.analysis_run_repo import AnalysisRunRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _issue(description: str) -> DiagnosisIssueRecord:
    return DiagnosisIssueRecord(
        issue_type="missing_parent",
        node_id=11,
        node_name="苹果",
        description=description,
        reason="parent missing",
        risk_level="high",
        confidence=1.0,
    )


def test_analysis_runs_keep_issue_evidence_isolated(tmp_path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    runs = AnalysisRunRepository(settings)
    first_run = runs.create_or_get(
        workflow_id="wf-1", round_no=1, analyzed_version_id=1
    )
    second_run = runs.create_or_get(
        workflow_id="wf-2", round_no=1, analyzed_version_id=1
    )
    repo = DiagnosisRepository(settings)

    repo.replace_issues(
        version_id=1,
        workflow_id="wf-1",
        analysis_run_id=first_run,
        detector_version="structure-v1",
        issues=[_issue("first run")],
    )
    repo.replace_issues(
        version_id=1,
        workflow_id="wf-2",
        analysis_run_id=second_run,
        detector_version="structure-v1",
        issues=[_issue("second run")],
    )

    assert [item["description"] for item in repo.list_for_run(first_run)] == [
        "first run"
    ]
    assert [item["description"] for item in repo.list_for_run(second_run)] == [
        "second run"
    ]


def test_suggestions_and_operations_are_queryable_by_analysis_run(tmp_path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    run_id = AnalysisRunRepository(settings).create_or_get(
        workflow_id="wf", round_no=1, analyzed_version_id=1
    )
    issue_id = DiagnosisRepository(settings).create_issue(
        version_id=1,
        workflow_id="wf",
        analysis_run_id=run_id,
        detector_version="content-v1",
        issue=_issue("scoped issue"),
    )
    suggestion_id = SuggestionRepository(settings).create_suggestion(
        workflow_id="wf",
        analysis_run_id=run_id,
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id,
            version_id=1,
            action_type="mark_as_valid",
            target_node_id=11,
            reason="valid",
            suggestion="keep",
            risk_level="low",
            confidence=1.0,
        ),
    )
    log_id = OperationLogRepository(settings).create_log(
        version_id=1,
        workflow_id="wf",
        analysis_run_id=run_id,
        operator="tester",
        operation_type="test",
        operation_detail={"suggestion_id": suggestion_id},
    )

    suggestions = SuggestionRepository(settings).list_for_run(run_id)
    operations = OperationLogRepository(settings).list_for_run(run_id)

    assert [item.id for item in suggestions] == [suggestion_id]
    assert [item["id"] for item in operations] == [log_id]
    assert operations[0]["workflow_id"] == "wf"
