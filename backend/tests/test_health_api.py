from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_check_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_local_frontend_origin_is_allowed_for_api_demo():
    client = TestClient(create_app())

    response = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
