import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repositories.file_repo import FileRepository
from backend.app.services.excel_service import UploadedFileMetadata


SAMPLE_PATH = Path("data/sample/产品标准体系.xlsx")


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _create_sample_file_record(settings):
    metadata = UploadedFileMetadata(
        file_name=SAMPLE_PATH.name,
        file_path=SAMPLE_PATH,
        file_size=SAMPLE_PATH.stat().st_size,
        sheet_name="Sheet1",
        row_count=21090,
        column_count=6,
        columns=[
            "category_id",
            "category_name",
            "category_group_id",
            "category_pids",
            "category_group_name",
            "syn_list",
        ],
    )
    return FileRepository(settings).create_uploaded_file(metadata)


def test_m1_services_build_real_sample_version_and_report(tmp_path):
    from backend.app.repositories.diagnosis_repo import DiagnosisRepository
    from backend.app.services.diagnosis_service import DiagnosisService
    from backend.app.services.report_service import ReportService
    from backend.app.services.taxonomy_service import TaxonomyService
    from backend.app.services.version_service import VersionService

    settings = _settings(tmp_path)
    create_app(settings)
    file_id = _create_sample_file_record(settings)

    build_result = TaxonomyService(settings).build_tree(file_id)
    version_result = VersionService(settings).create_initial_version(file_id)
    diagnosis_result = DiagnosisService(settings).run_structure_diagnosis(
        version_result.version_id
    )
    report_result = ReportService(settings).generate_diagnosis_report(
        version_result.version_id
    )

    assert build_result.node_count == 21090
    assert build_result.max_depth == 10
    assert version_result.version_no == "v1.0"
    assert version_result.node_count == 21090
    assert diagnosis_result.summary["missing_parent"] == 44
    assert diagnosis_result.issue_count == sum(diagnosis_result.summary.values())
    assert report_result.report_path.exists()
    report_text = report_result.report_path.read_text(encoding="utf-8")
    assert "节点总数：21090" in report_text
    assert "父节点缺失：44" in report_text

    issue_summary = DiagnosisRepository(settings).count_by_type(version_result.version_id)
    assert issue_summary["missing_parent"] == 44


def test_m1_workflow_api_runs_upload_to_report_with_real_data(tmp_path):
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings))

    with SAMPLE_PATH.open("rb") as file_obj:
        upload_response = client.post(
            "/api/files/upload",
            files={
                "file": (
                    SAMPLE_PATH.name,
                    file_obj,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]

    start_response = client.post("/api/workflows/taxonomy/start", json={"file_id": file_id})
    assert start_response.status_code == 200
    start_body = start_response.json()
    assert start_body["task_id"]
    assert start_body["workflow_id"]
    assert start_body["thread_id"] == f"taxonomy_workflow:{start_body['workflow_id']}"
    assert start_body["status"] in {"running", "completed"}
    assert start_body["current_step"] in {"parse_excel", "completed"}
    assert start_body["progress"] >= 0

    status_response = client.get(f"/api/workflows/{start_body['task_id']}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] in {"completed", "waiting_review"}
    assert status_body["current_step"] in {"completed", "human_review"}
    assert status_body["progress"] in {80, 100}
    assert status_body["file_id"] == file_id
    assert status_body["version_no"] == "v1.0"
    assert status_body["node_count"] == 21090
    assert status_body["structure_issue_count"] >= 44
    if status_body["status"] == "completed":
        assert Path(status_body["report_path"]).exists()
    else:
        assert status_body["review_batch_id"]

    with sqlite3.connect(tmp_path / "app.db") as connection:
        task = connection.execute(
            """
            SELECT workflow_id, thread_id, version_id, progress
            FROM task_record
            WHERE id = ?
            """,
            (start_body["task_id"],),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_event WHERE task_id = ?",
            (start_body["task_id"],),
        ).fetchone()[0]

    assert task == (
        start_body["workflow_id"],
        start_body["thread_id"],
        status_body["current_version_id"],
        status_body["progress"],
    )
    assert event_count >= 6
