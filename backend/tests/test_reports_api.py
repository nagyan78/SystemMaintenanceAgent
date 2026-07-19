from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.main import create_app
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _seed_version(settings) -> int:
    with connect(settings) as connection:
        connection.execute("INSERT OR IGNORE INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    version_id = VersionRepository(settings).create_version(
        file_id=1,
        version_no="v1.0",
        description="report api test",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="根",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="根",
                syn_list=None,
                is_leaf=1,
            )
        ],
    )
    return version_id


def test_report_api_generates_previews_and_downloads_markdown(tmp_path):
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings))
    version_id = _seed_version(settings)

    generated_on_demand = client.get(f"/api/reports/{version_id}/preview?report_type=draft")
    assert generated_on_demand.status_code == 200

    generated = client.post(
        "/api/reports/generate",
        json={"version_id": version_id, "format": "markdown", "report_type": "draft"},
    )
    assert generated.status_code == 200
    assert generated.json()["download_url"] == f"/api/reports/{version_id}/download?report_type=draft"
    assert generated.json()["pdf_download_url"] == f"/api/reports/{version_id}/download-pdf?report_type=draft"

    preview = client.get(f"/api/reports/{version_id}/preview?report_type=draft")
    assert preview.status_code == 200
    assert "# 产品标准体系诊断报告" in preview.json()["markdown"]

    download = client.get(f"/api/reports/{version_id}/download?report_type=draft")
    assert download.status_code == 200
    assert "产品标准体系诊断报告" in download.content.decode("utf-8")

    pdf_download = client.get(f"/api/reports/{version_id}/download-pdf?report_type=draft")
    assert pdf_download.status_code == 200
    assert pdf_download.headers["content-type"] == "application/pdf"
    assert pdf_download.content.startswith(b"%PDF-")
    assert len(pdf_download.content) > 5_000
