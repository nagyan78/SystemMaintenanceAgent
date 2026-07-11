from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.model_service import ModelService


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        export_dir=tmp_path / "exports",
        report_dir=tmp_path / "reports",
    )


def _workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["category_id", "category_name", "category_group_id", "category_pids", "category_group_name", "syn_list"])
    sheet.append([1, "产品", "", "", "", ""])
    sheet.append([2, "设备", "1", "1", "产品", ""])
    sheet.append([3, "设备", "1", "1", "产品", ""])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_quick_diagnosis_skips_model_and_records_configuration(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("quick diagnosis must not construct a model")

    monkeypatch.setattr(ModelService, "get_chat_model", fail_if_called)
    client = TestClient(create_app(_settings(tmp_path)))
    upload = client.post(
        "/upload",
        files={"file": ("taxonomy.xlsx", _workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()

    response = client.post(
        "/api/diagnosis/run",
        json={
            "file_id": upload["file_id"],
            "enable_ai_analysis": False,
            "model_provider": "ollama",
            "model_name": "qwen3:8b",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["enable_ai_analysis"] is False
    summary = client.get(f"/api/diagnosis/summary?version_id={result['version_id']}").json()
    assert summary["enable_ai_analysis"] is False
    assert summary["model_name"] is None
    task = client.get(f"/api/workflows/{result['task_id']}").json()
    assert task["status"] == "completed"
    assert task["enable_ai_analysis"] is False
    assert task["start_time"]
    assert task["end_time"]
    assert client.get(f"/workflow/{result['task_id']}").status_code == 200
    assert client.get(f"/diagnosis/summary?version_id={result['version_id']}").status_code == 200
    assert client.get(f"/versions?file_id={upload['file_id']}").json()[0]["quality_score"] is not None
    assert client.get(f"/reports?file_id={upload['file_id']}").status_code == 200


def test_diagnosis_rejects_mismatched_provider_model(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    response = client.post(
        "/api/diagnosis/run",
        json={"version_id": 1, "enable_ai_analysis": True, "model_provider": "ollama", "model_name": "deepseek-chat"},
    )
    assert response.status_code == 400
