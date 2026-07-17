from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import connect, init_db
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


def _seed_versions(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT OR IGNORE INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    repo = VersionRepository(settings)
    taxonomy_repo = TaxonomyRepository(settings)
    v1 = repo.create_version(file_id=1, version_no="v1.0", description="base")
    v2 = repo.create_version(file_id=1, version_no="v1.1", description="changed")
    taxonomy_repo.bulk_insert_nodes(
        version_id=v1,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="根",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="根",
                syn_list=None,
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=2,
                category_name="苹果",
                parent_id=1,
                level=2,
                path_ids="1,2",
                path_names="根 > 苹果",
                syn_list="AirPods, 红富士",
                is_leaf=1,
            ),
        ],
    )
    taxonomy_repo.bulk_insert_nodes(
        version_id=v2,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="根",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="根",
                syn_list=None,
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=2,
                category_name="苹果",
                parent_id=1,
                level=2,
                path_ids="1,2",
                path_names="根 > 苹果",
                syn_list="红富士",
                is_leaf=1,
            ),
        ],
    )
    return v1, v2


def test_versions_api_lists_details_diffs_and_exports(tmp_path):
    settings = _settings(tmp_path)
    v1, v2 = _seed_versions(settings)
    client = TestClient(create_app(settings))

    list_response = client.get("/api/versions", params={"file_id": 1})
    assert list_response.status_code == 200
    assert [item["version_no"] for item in list_response.json()] == ["v1.0", "v1.1"]

    detail_response = client.get(f"/api/versions/{v1}")
    assert detail_response.status_code == 200
    assert detail_response.json()["node_count"] == 2

    diff_response = client.get(
        f"/api/versions/{v1}/diff",
        params={"target_version_id": v2},
    )
    assert diff_response.status_code == 200
    assert diff_response.json()["synonym_changed"][0]["removed_synonyms"] == ["AirPods"]

    export_response = client.get(f"/api/versions/{v2}/export")
    assert export_response.status_code == 200
    export_body = export_response.json()
    assert export_body["file_name"] == f"file-1_v1.1_version-{v2}_taxonomy.xlsx"
    assert (settings.export_dir / export_body["file_name"]).exists()


def test_versions_api_rolls_back_without_deleting_history(tmp_path):
    settings = _settings(tmp_path)
    v1, _ = _seed_versions(settings)
    client = TestClient(create_app(settings))

    response = client.post(f"/api/versions/{v1}/rollback")

    assert response.status_code == 200
    assert response.json()["new_version_no"] == "v1.2"
    versions = client.get("/api/versions", params={"file_id": 1}).json()
    assert [item["version_no"] for item in versions] == ["v1.0", "v1.1", "v1.2"]
