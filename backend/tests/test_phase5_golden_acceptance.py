import json

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.fixtures.golden_taxonomy import DATASET_VERSION, EXPECTED_ISSUES, workbook_bytes


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path/'app.db'}", upload_dir=tmp_path/'uploads',
        report_dir=tmp_path/'reports', export_dir=tmp_path/'exports',
        deepseek_api_key="", dashscope_api_key="", enable_legacy_manual_review_api=True,
    )


def _run_golden(client: TestClient) -> dict:
    upload = client.post(
        "/api/files/upload",
        files={"file": ("phase5_golden.xlsx", workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200
    diagnosis = client.post("/api/diagnosis/run", json={
        "file_id": upload.json()["file_id"], "enable_ai_analysis": False,
        "model_provider": "deepseek", "model_name": "deepseek-chat",
    })
    assert diagnosis.status_code == 200
    body = diagnosis.json()
    coverage = body["coverage"]
    assert coverage["total_nodes"] == coverage["rule_scanned_nodes"] == 11
    assert coverage["coverage_complete"] is True
    issues = client.get(f"/api/diagnosis/issues?version_id={body['version_id']}").json()
    signature = {(item["node_id"], item["issue_type_code"]) for item in issues}
    assert signature == EXPECTED_ISSUES
    assert all(body["run_id"] in item["run_ids"] for item in issues)

    evaluation = client.post("/api/evaluations", json={
        "workflow_id": body["workflow_id"], "dataset_version": DATASET_VERSION,
        "agent_bundle_version": "phase5",
    })
    assert evaluation.status_code == 200
    metrics = evaluation.json()["result"]
    assert metrics["detection_recall"] == 1.0
    assert metrics["detection_precision"] == 1.0

    evidence = client.get(f"/api/workflows/{body['task_id']}/evidence")
    assert evidence.status_code == 200
    facts = evidence.json()
    assert facts["workflow_id"] == body["workflow_id"]
    assert {item["id"] for item in facts["issues"]} == {item["id"] for item in issues}
    assert any(item["id"] == body["run_id"] for item in facts["runs"])
    draft = next(item for item in facts["reports"] if item["report_type"] == "draft")
    assert draft["workflow_id"] == body["workflow_id"] and draft["run_id"] == body["run_id"]
    report_facts = json.loads(draft["fact_payload"])
    assert report_facts["issue_summary"]["total"] == len(EXPECTED_ISSUES)
    assert report_facts["runtime_info"]["coverage"]["rule_scanned_nodes"] == 11

    completed = client.post(
        f"/api/reviews/{body['review_batch_id']}/auto-complete", json={"operator": "golden"}
    )
    assert completed.status_code == 200
    if completed.json()["approved_ids"]:
        preview = client.post(f"/api/reviews/{body['review_batch_id']}/execution-preview", json={})
        assert preview.status_code == 200 and preview.json()["valid"] is True
        executed = client.post(
            f"/api/reviews/{body['review_batch_id']}/execute", json={"operator": "golden"}
        )
        assert executed.status_code == 200
        assert executed.json()["new_version_id"] != body["version_id"]
        final_report = client.get(
            f"/api/reports/{executed.json()['new_version_id']}/preview?report_type=final"
        )
        assert final_report.status_code == 200
    return {"signature": signature, "metrics": metrics}


def test_fixed_golden_excel_is_repeatable_and_closes_business_loop(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    first = _run_golden(client)
    second = _run_golden(client)
    assert second["signature"] == first["signature"]
    assert second["metrics"]["detection_recall"] == first["metrics"]["detection_recall"]
