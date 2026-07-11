from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.analysis_run_repo import AnalysisRunRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.report_service import ReportService


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        report_dir=tmp_path / "reports",
    )


def test_report_uses_only_current_workflow_analysis_run_evidence(tmp_path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="根",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="根",
                is_leaf=1,
            )
        ],
    )
    runs = AnalysisRunRepository(settings)
    run_1 = runs.create_or_get(workflow_id="wf-1", round_no=1, analyzed_version_id=version_id)
    run_2 = runs.create_or_get(workflow_id="wf-2", round_no=1, analyzed_version_id=version_id)
    issues = DiagnosisRepository(settings)
    for workflow_id, run_id, description in (
        ("wf-1", run_1, "only-first-workflow"),
        ("wf-2", run_2, "only-second-workflow"),
    ):
        issues.create_issue(
            version_id=version_id,
            workflow_id=workflow_id,
            analysis_run_id=run_id,
            detector_version="content-v1",
            issue=DiagnosisIssueRecord(
                issue_type="naming_irregular",
                node_id=1,
                node_name="根",
                description=description,
                reason="test",
                risk_level="low",
                confidence=1.0,
            ),
        )
        OperationLogRepository(settings).create_log(
            version_id=version_id,
            workflow_id=workflow_id,
            analysis_run_id=run_id,
            operator="tester",
            operation_type=f"operation-{workflow_id}",
            operation_detail={},
        )

    result = ReportService(settings).generate_diagnosis_report(
        version_id,
        workflow_id="wf-1",
        analysis_run_id=run_1,
        analyzed_version_id=version_id,
        result_version_id=None,
        verification={
            "status": "partially_passed",
            "resolved_fingerprints": ["fixed"],
            "unresolved_fingerprints": ["remaining"],
            "introduced_fingerprints": [],
            "quality_delta": 1.5,
        },
    )
    text = result.report_path.read_text(encoding="utf-8")

    assert "only-first-workflow" in text
    assert "operation-wf-1" in text
    assert "only-second-workflow" not in text
    assert "operation-wf-2" not in text
    assert "partially_passed" in text
    assert result.report_name.startswith("v1.0_wf-1_")
