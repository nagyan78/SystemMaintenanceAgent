from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.model_service import ModelService
from backend.app.services.model_router import ModelBudgetExceededError


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
    assert result["status"] == "waiting_review"
    assert result["enable_ai_analysis"] is False
    summary = client.get(f"/api/diagnosis/summary?version_id={result['version_id']}").json()
    assert summary["enable_ai_analysis"] is False
    assert summary["model_name"] is None
    task = client.get(f"/api/workflows/{result['task_id']}").json()
    assert task["status"] == "waiting_review"
    assert task["enable_ai_analysis"] is False
    assert task["start_time"]
    assert task["end_time"] is None
    assert client.get(f"/workflow/{result['task_id']}").status_code == 200
    assert client.get(f"/diagnosis/summary?version_id={result['version_id']}").status_code == 200
    assert client.get(f"/versions?file_id={upload['file_id']}").json()[0]["quality_score"] is not None
    assert client.get(f"/reports?file_id={upload['file_id']}").status_code == 200

    rerun = client.post(
        "/api/diagnosis/run",
        json={"version_id": result["version_id"], "enable_ai_analysis": False},
    )
    assert rerun.status_code == 200
    assert rerun.json()["status"] == "waiting_review"


def test_diagnosis_rejects_mismatched_provider_model(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    response = client.post(
        "/api/diagnosis/run",
        json={"version_id": 1, "enable_ai_analysis": True, "model_provider": "ollama", "model_name": "deepseek-chat"},
    )
    assert response.status_code == 400


def test_explicit_high_coverage_request_overrides_planner_sample(tmp_path, monkeypatch):
    from backend.app.schemas.issue import DiagnosisPlan
    from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent, DiagnosisPlanningAgent

    captured = {}
    monkeypatch.setattr(
        DiagnosisPlanningAgent,
        "run",
        lambda *args, **kwargs: DiagnosisPlan(estimated_candidates=10),
    )

    def capture_plan(self, version_id, plan):
        captured["estimated_candidates"] = plan.estimated_candidates
        captured["wall_seconds"] = self.settings.diagnosis_ai_wall_seconds
        return []

    monkeypatch.setattr(ContentDiagnosisAgent, "run", capture_plan)
    client = TestClient(create_app(_settings(tmp_path)))
    upload = client.post(
        "/upload",
        files={"file": ("taxonomy.xlsx", _workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    response = client.post(
        "/api/diagnosis/run",
        json={
            "file_id": upload["file_id"],
            "enable_ai_analysis": True,
            "model_provider": "ollama",
            "model_name": "qwen3:8b",
            "ai_candidate_limit": 927,
            "ai_wall_seconds": 14400,
        },
    )

    assert response.status_code == 200
    assert captured == {"estimated_candidates": 927, "wall_seconds": 14400}
    assert response.json()["ai_candidate_limit"] == 927
    assert response.json()["ai_wall_seconds"] == 14400


def test_ai_budget_exhaustion_keeps_results_and_generates_report(tmp_path, monkeypatch):
    from backend.app.services.content_diagnosis_service import DiagnosisPlanningAgent

    client = TestClient(create_app(_settings(tmp_path)))
    upload = client.post(
        "/upload",
        files={"file": ("taxonomy.xlsx", _workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()

    def exhaust_budget(*args, **kwargs):
        raise ModelBudgetExceededError("MODEL_BUDGET_EXCEEDED: tokens")

    monkeypatch.setattr(DiagnosisPlanningAgent, "run", exhaust_budget)
    response = client.post(
        "/api/diagnosis/run",
        json={
            "file_id": upload["file_id"],
            "enable_ai_analysis": True,
            "model_provider": "ollama",
            "model_name": "qwen3:8b",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "waiting_review"
    assert result["ai_analysis_status"] == "partial"
    assert result["report_path"]
    preview = client.get(f"/api/reports/{result['version_id']}/preview?report_type=draft")
    assert preview.status_code == 200
    markdown = preview.json()["markdown"]
    assert "诊断模式：AI 增强模式" in markdown
    assert "## 五、AI分析情况" in markdown
    assert "综合评分：暂不评级" in markdown
    task = client.get(f"/api/workflows/{result['task_id']}").json()
    assert task["status"] == "waiting_review"
    assert task["current_step"] == "review_pending"


def test_ai_connection_error_keeps_results_and_generates_report(tmp_path, monkeypatch):
    from backend.app.services.content_diagnosis_service import DiagnosisPlanningAgent

    client = TestClient(create_app(_settings(tmp_path)))
    upload = client.post(
        "/upload",
        files={"file": ("taxonomy.xlsx", _workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()

    def connection_failed(*args, **kwargs):
        raise ConnectionError("DeepSeek is unreachable")

    monkeypatch.setattr(DiagnosisPlanningAgent, "run", connection_failed)
    response = client.post(
        "/api/diagnosis/run",
        json={
            "file_id": upload["file_id"],
            "enable_ai_analysis": True,
            "model_provider": "ollama",
            "model_name": "qwen3:8b",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "waiting_review"
    assert result["ai_analysis_status"] == "partial"
    assert "无法连接所选模型" in result["ai_warning"]
    assert result["report_path"]
    task = client.get(f"/api/workflows/{result['task_id']}").json()
    assert task["status"] == "waiting_review"
    assert task["current_step"] == "review_pending"
    preview = client.get(f"/api/reports/{result['version_id']}/preview?report_type=draft").json()["markdown"]
    assert "诊断模式：AI 增强模式" in preview
    assert "AI 分析因模型连接失败未完整完成" in preview
    assert "模型未发现问题" not in preview
