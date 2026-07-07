from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_planned_api_boundaries_return_not_implemented():
    client = TestClient(create_app())

    cases = [
        ("GET", "/api/taxonomy/overview", "taxonomy"),
        ("POST", "/api/diagnosis/run", "diagnosis"),
        ("GET", "/api/versions", "versions"),
        ("POST", "/api/chat", "chat"),
    ]

    for method, path, module in cases:
        response = client.request(method, path)

        assert response.status_code == 501
        assert response.json()["detail"]["module"] == module

