import json
from pathlib import Path

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.diagnosis_service import DiagnosisService


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
    )


def test_depth_reports_one_issue_per_overdeep_leaf_path(tmp_path):
    service = DiagnosisService(_settings(tmp_path))
    nodes = [
        {"category_id": 8, "category_name": "中间层", "level": 8, "is_leaf": 0, "path_names": "路径 A"},
        {"category_id": 9, "category_name": "叶节点 A", "level": 8, "is_leaf": 1, "path_names": "路径 A > 叶节点 A"},
        {"category_id": 10, "category_name": "叶节点 B", "level": 9, "is_leaf": 1, "path_names": "路径 B > 叶节点 B"},
        {"category_id": 11, "category_name": "正常叶节点", "level": 7, "is_leaf": 1, "path_names": "路径 C"},
    ]

    issues = service._deep_level_issues(nodes, 7)

    assert [(item.node_id, item.risk_level) for item in issues] == [(9, "low"), (10, "medium")]
    assert "需减少层数：1" in (issues[0].evidence or "")


def test_width_risk_follows_required_group_count(tmp_path):
    service = DiagnosisService(_settings(tmp_path))
    nodes = []
    for parent_id, count in ((1, 81), (2, 161), (3, 241)):
        nodes.append({"category_id": parent_id, "category_name": f"父节点{parent_id}", "parent_id": None})
        nodes.extend(
            {"category_id": parent_id * 1000 + index, "category_name": f"子节点{index}", "parent_id": parent_id}
            for index in range(count)
        )

    issues = service._wide_node_issues(nodes, 80)

    assert [(item.node_id, item.risk_level) for item in issues] == [
        (1, "low"),
        (2, "medium"),
        (3, "high"),
    ]


def test_duplicate_name_only_flags_duplicate_siblings(tmp_path):
    service = DiagnosisService(_settings(tmp_path))
    nodes = [
        {"category_id": 1, "category_name": "产品", "parent_id": None, "path_names": "产品"},
        {"category_id": 2, "category_name": "设备", "parent_id": 1, "path_names": "产品 > 设备"},
        {"category_id": 3, "category_name": "设备", "parent_id": 1, "path_names": "产品 > 设备"},
        {"category_id": 4, "category_name": "设备", "parent_id": 99, "path_names": "另一根 > 设备"},
    ]

    issues = service._duplicate_name_issues(nodes)

    assert len(issues) == 1
    assert issues[0].issue_type == "duplicate_sibling"
    assert issues[0].node_id == 3


def test_golden_business_names_do_not_trigger_deterministic_content_rules(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'test.xlsx','test.xlsx')"
        )
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    golden = json.loads(
        (Path(__file__).parent / "fixtures" / "business_name_regression_golden.json").read_text(encoding="utf-8")
    )
    nodes = [
        TaxonomyNodeRecord(
            category_id=1,
            category_name="产品",
            parent_id=None,
            level=1,
            path_ids="1",
            path_names="产品",
            is_leaf=0,
        ),
    ]
    nodes.extend(
        TaxonomyNodeRecord(
            category_id=index,
            category_name=item["category_name"],
            parent_id=1,
            level=2,
            path_ids=f"1,{index}",
            path_names=f"产品 > {item['category_name']}",
            syn_list=item.get("syn_list"),
            is_leaf=1,
        )
        for index, item in enumerate(golden, start=2)
    )
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)

    issue_count = DiagnosisService(settings).run_content_rule_diagnosis(version_id)
    issues = DiagnosisRepository(settings).list_issues(version_id=version_id)

    assert issue_count == 0
    assert issues == []
