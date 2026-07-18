import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.taxonomy_fixture import write_taxonomy_workbook


EXPECTED_COLUMNS = [
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
]


def _create_workbook(path, headers=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or EXPECTED_COLUMNS)
    sheet.append([1, "根节点", "", "", "根节点", ""])
    workbook.save(path)
    return path


def _create_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
    )
    return TestClient(create_app(settings)), settings


def _upload(client, workbook_path, file_name="taxonomy.xlsx"):
    with workbook_path.open("rb") as file_obj:
        return client.post(
            "/api/files/upload",
            files={
                "file": (
                    file_name,
                    file_obj,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )


def test_upload_xlsx_saves_file_and_returns_metadata(tmp_path):
    workbook_path = _create_workbook(tmp_path / "taxonomy.xlsx")
    client, settings = _create_client(tmp_path)

    response = _upload(client, workbook_path)

    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == 1
    assert body["task_id"].startswith("import_excel_")
    assert body["row_count"] == 1
    assert body["column_count"] == 6
    assert body["status"] == "uploaded"
    assert len(list(settings.upload_dir.iterdir())) == 1

    with sqlite3.connect(tmp_path / "app.db") as conn:
        uploaded_count = conn.execute("SELECT COUNT(*) FROM uploaded_file").fetchone()[0]
        upload_time = conn.execute("SELECT upload_time FROM uploaded_file").fetchone()[0]
        task = conn.execute(
            "SELECT file_id, task_type, status, current_step, progress FROM task_record"
        ).fetchone()

    assert uploaded_count == 1
    assert datetime.fromisoformat(upload_time).tzinfo is not None
    assert task == (1, "import_excel", "pending", "uploaded", 0)


def test_upload_generated_xlsx_returns_expected_metadata(tmp_path):
    sample_path = write_taxonomy_workbook(tmp_path / "taxonomy.xlsx")
    client, _settings = _create_client(tmp_path)

    response = _upload(client, sample_path, file_name=sample_path.name)

    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "taxonomy.xlsx"
    assert body["row_count"] == 3
    assert body["column_count"] == 6
    assert body["columns"] == EXPECTED_COLUMNS
    assert body["task_id"].startswith("import_excel_")


def test_upload_rejects_empty_xlsx_without_creating_records(tmp_path):
    empty_path = tmp_path / "empty.xlsx"
    empty_path.write_bytes(b"")
    client, _settings = _create_client(tmp_path)

    response = _upload(client, empty_path, file_name="empty.xlsx")

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "error_code": "EMPTY_FILE",
        "message": "Excel file is empty.",
    }

    with sqlite3.connect(tmp_path / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM uploaded_file").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM task_record").fetchone()[0] == 0


def test_upload_rejects_missing_required_columns_without_creating_records(tmp_path):
    workbook_path = _create_workbook(
        tmp_path / "taxonomy.xlsx",
        headers=[
            "category_id",
            "category_group_id",
            "category_pids",
            "category_group_name",
            "syn_list",
        ],
    )
    client, _settings = _create_client(tmp_path)

    response = _upload(client, workbook_path)

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "error_code": "INVALID_COLUMNS",
        "message": "Excel missing required columns: category_name",
    }

    with sqlite3.connect(tmp_path / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM uploaded_file").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM task_record").fetchone()[0] == 0


def test_file_list_and_detail_return_uploaded_file_metadata(tmp_path):
    workbook_path = _create_workbook(tmp_path / "taxonomy.xlsx")
    client, _settings = _create_client(tmp_path)

    upload_response = _upload(client, workbook_path)
    file_id = upload_response.json()["file_id"]

    list_response = client.get("/api/files")
    detail_response = client.get(f"/api/files/{file_id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == file_id
    assert list_response.json()[0]["file_id"] == file_id
    assert list_response.json()[0]["file_name"] == "taxonomy.xlsx"
    assert list_response.json()[0]["columns"] == EXPECTED_COLUMNS
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == file_id
    assert detail_response.json()["row_count"] == 1
    assert detail_response.json()["columns"] == EXPECTED_COLUMNS
