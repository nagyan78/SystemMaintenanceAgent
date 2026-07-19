from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.version_service import VersionService


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _seed_two_versions(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT OR IGNORE INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    repo = VersionRepository(settings)
    taxonomy_repo = TaxonomyRepository(settings)
    v1 = repo.create_version(file_id=1, version_no="v1.0", description="base")
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
            TaxonomyNodeRecord(
                category_id=3,
                category_name="饮料",
                parent_id=1,
                level=2,
                path_ids="1,3",
                path_names="根 > 饮料",
                is_leaf=1,
            ),
        ],
    )
    v2 = repo.create_version(file_id=1, version_no="v1.1", description="changed")
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
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=2,
                category_name="鲜果",
                parent_id=3,
                level=3,
                path_ids="1,3,2",
                path_names="根 > 饮料 > 鲜果",
                syn_list="红富士",
                is_leaf=1,
            ),
            TaxonomyNodeRecord(
                category_id=3,
                category_name="饮料",
                parent_id=1,
                level=2,
                path_ids="1,3",
                path_names="根 > 饮料",
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=4,
                category_name="梨",
                parent_id=1,
                level=2,
                path_ids="1,4",
                path_names="根 > 梨",
                is_leaf=1,
            ),
        ],
    )
    return v1, v2


def test_version_diff_reports_rename_move_synonym_and_add(tmp_path):
    settings = _settings(tmp_path)
    v1, v2 = _seed_two_versions(settings)

    diff = VersionService(settings).get_version_diff(v1, v2)

    assert diff.from_version_id == v1
    assert diff.to_version_id == v2
    assert [item["category_id"] for item in diff.added] == [4]
    assert diff.deleted == []
    assert diff.renamed[0]["old_name"] == "苹果"
    assert diff.renamed[0]["new_name"] == "鲜果"
    assert diff.moved[0]["old_parent_id"] == 1
    assert diff.moved[0]["new_parent_id"] == 3
    assert diff.synonym_changed[0]["removed_synonyms"] == ["AirPods"]


def test_rollback_creates_new_version_from_historical_snapshot(tmp_path):
    settings = _settings(tmp_path)
    v1, _ = _seed_two_versions(settings)

    result = VersionService(settings).rollback_version(v1, operator="tester")

    assert result.new_version_no == "v1.2"
    rolled_back_nodes = TaxonomyRepository(settings).list_nodes(result.new_version_id)
    assert [item["category_id"] for item in rolled_back_nodes] == [1, 2, 3]
    assert rolled_back_nodes[1]["category_name"] == "苹果"


def test_m4_graph_routes_validate_to_execute_save_and_report(tmp_path):
    from backend.app.agents.graph import build_taxonomy_graph

    graph = build_taxonomy_graph(settings=_settings(tmp_path), enable_suggestion_review=True)
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("validate_action_node", "execute_action_node") in edges
    assert ("execute_action_node", "save_new_version_node") in edges
    assert ("save_new_version_node", "verify_new_version_node") in edges
    assert ("verify_new_version_node", "generate_report_node") in edges
