import pytest

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.remediation_planning_service import RemediationPlanningService
from backend.app.services.version_service import VersionService
from backend.app.services.version_verification_service import VersionVerificationService


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
        max_children_threshold=3,
    )


def _seed(settings: Settings) -> int:
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'test.xlsx','test.xlsx')"
        )
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    raw = [
        (1, "产品", None),
        (2, "食品", 1),
        (3, "其他", 2),
        (4, "苹果", 2),
        (5, "重复分类", 2),
        (6, "重复分类", 2),
        (7, "宽节点", 1),
        (20, "停用候选", 1),
        (21, "废弃叶子", 1),
        (50, "断裂节点", 99),
        (60, "过深节点", 2),
    ] + [(number, f"子类{number}", 7) for number in range(10, 14)]
    nodes = []
    for category_id, name, parent_id in raw:
        if category_id == 50:
            path_ids, path_names, level = "1,99,50", "产品 > 缺失分类 > 断裂节点", 3
        elif parent_id is None:
            path_ids, path_names, level = str(category_id), name, 1
        else:
            path_ids, path_names, level = f"1,{category_id}", f"产品 > {name}", 2
        nodes.append(TaxonomyNodeRecord(
            category_id=category_id,
            category_name=name,
            parent_id=parent_id,
            level=level,
            path_ids=path_ids,
            path_names=path_names,
            syn_list="苹果, 红富士, 红富士" if category_id == 4 else None,
            is_leaf=0 if category_id in {1, 2, 7} else 1,
        ))
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)
    return version_id


@pytest.mark.parametrize(
    ("issue_type", "node_id", "node_name", "expected"),
    [
        ("ambiguous_name", 3, "其他", "review_only"),
        ("synonym_format_issue", 4, "苹果", "update_synonyms"),
        ("missing_parent", 50, "断裂节点", "add_node"),
        ("deep_level", 60, "过深节点", "move_node"),
        ("wide_node", 7, "宽节点", "split_subtree"),
        ("duplicate_name", None, "重复分类", "review_only"),
        ("obsolete_node", 20, "停用候选", "review_only"),
        ("redundant_leaf", 21, "废弃叶子", "review_only"),
        ("insufficient_evidence", 21, "废弃叶子", "review_only"),
    ],
)
def test_issue_type_maps_to_executable_action(
    tmp_path, issue_type, node_id, node_name, expected
):
    settings = _settings(tmp_path)
    version_id = _seed(settings)
    issue_id = DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type=issue_type,
            node_id=node_id,
            node_name=node_name,
            description="test",
            reason="test evidence",
            risk_level="medium",
            confidence=0.9,
        ),
    )
    issue = DiagnosisRepository(settings).get_issue_detail(issue_id)

    suggestion = RemediationPlanningService(settings).plan(version_id, issue)

    assert suggestion.action_type == expected
    assert suggestion.need_confirm is True


def test_version_save_is_idempotent_and_verification_exports_excel(tmp_path):
    settings = _settings(tmp_path)
    base_version_id = _seed(settings)
    service = VersionService(settings)

    first = service.save_new_version(
        base_version_id,
        "review_1",
        action_batch_id="action_stable",
        source_workflow_id="workflow_1",
    )
    second = service.save_new_version(
        base_version_id,
        "review_1",
        action_batch_id="action_stable",
        source_workflow_id="workflow_1",
    )
    verification = VersionVerificationService(settings).verify(
        base_version_id=base_version_id,
        new_version_id=first.new_version_id,
    )
    saved = VersionRepository(settings).get_version(first.new_version_id)

    assert second.new_version_id == first.new_version_id
    assert second.reused is True
    assert saved["parent_version_id"] == base_version_id
    assert saved["source_workflow_id"] == "workflow_1"
    assert saved["verification_status"] == "partial"
    assert verification.export_path.endswith(f"file-1_v1.1_version-{first.new_version_id}_taxonomy.xlsx")
