from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.main import create_app


def test_upload_xlsx_saves_file_and_returns_metadata(tmp_path):
    workbook_path = tmp_path / "taxonomy.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "category_id",
            "category_name",
            "category_group_id",
            "category_pids",
            "category_group_name",
            "syn_list",
        ]
    )
    sheet.append([1, "根节点", "", "", "根节点", ""])
    workbook.save(workbook_path)

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings))

    with workbook_path.open("rb") as file_obj:
        response = client.post(
            "/api/files/upload",
            files={
                "file": (
                    "taxonomy.xlsx",
                    file_obj,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["file_id"] == 1
    assert body["row_count"] == 1
    assert body["column_count"] == 6
    assert body["status"] == "uploaded"

