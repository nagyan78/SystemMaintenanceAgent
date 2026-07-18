from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_remaining_planned_api_boundaries_return_not_implemented():
    client = TestClient(create_app())

    cases = [
        ("POST", "/api/diagnosis/run", "diagnosis"),
        ("POST", "/api/chat", "chat"),
    ]

    for method, path, module in cases:
        response = client.request(method, path)

        assert response.status_code == 501
        assert response.json()["detail"]["module"] == module


def test_read_only_taxonomy_api_requires_explicit_version_context():
    response = TestClient(create_app()).get("/api/taxonomy/overview")

    assert response.status_code == 422
