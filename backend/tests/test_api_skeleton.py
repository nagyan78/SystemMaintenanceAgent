from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_planned_api_boundaries_return_not_implemented():
    client = TestClient(create_app())

    cases = [("POST", "/api/chat", "chat")]

    for method, path, module in cases:
        response = client.request(method, path)

        assert response.status_code == 501
        assert response.json()["detail"]["module"] == module


def test_manual_review_mutations_are_disabled_by_default(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        export_dir=tmp_path / "exports",
        report_dir=tmp_path / "reports",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/reviews/review-example/decision",
        json={"decision": "approve", "operator": "local_user"},
    )

    assert response.status_code == 410
    assert "人工审核接口已停用" in response.json()["detail"]

    resume = client.post("/api/workflows/legacy-task/resume", json={"decision": "approve"})
    assert resume.status_code == 410
    assert "独立 AI 复核" in resume.json()["detail"]
