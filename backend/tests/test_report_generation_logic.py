import re

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.report_service import ReportService


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        export_dir=tmp_path / "exports",
        report_dir=tmp_path / "reports",
        max_tree_depth_threshold=7,
        max_children_threshold=80,
    )


def _seed_version(settings: Settings, *, score: float = 97.9, version_no: str = "v1.0") -> int:
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO uploaded_file (id,file_name,file_path) VALUES (1,'产品标准体系_test2_1000.xlsx','test.xlsx')"
        )
    return VersionRepository(settings).create_version(
        file_id=1,
        version_no=version_no,
        description="report fixture",
        quality_score=score,
    )


def _node(category_id: int, name: str, parent_id: int | None, path: str, *, leaf: int = 1) -> TaxonomyNodeRecord:
    return TaxonomyNodeRecord(
        category_id=category_id,
        category_name=name,
        parent_id=parent_id,
        level=len(path.split(" > ")),
        path_ids=str(category_id),
        path_names=path,
        syn_list="别名" if category_id % 8 else None,
        is_leaf=leaf,
    )


def _add_issue(
    settings: Settings,
    version_id: int,
    issue_type: str,
    node_id: int,
    *,
    risk: str,
    source: str = "structure_rule",
    reason: str | None = None,
    evidence: str | None = None,
) -> int:
    node = TaxonomyRepository(settings).get_node_detail(version_id, node_id, include_deprecated=True)
    return DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type=issue_type,
            node_id=node_id,
            node_name=node["category_name"] if node else f"节点{node_id}",
            description=f"{issue_type} 测试问题",
            reason=reason or f"节点 {node_id} 命中 {issue_type} 判断条件",
            risk_level=risk,
            confidence=0.96,
            path=node["path_names"] if node else None,
            evidence=evidence or f"节点 {node_id} 的保存证据",
            source=source,
        ),
    )


def _seed_1058_fixture(settings: Settings) -> int:
    version_id = _seed_version(settings)
    nodes = [_node(1, "产品", None, "产品", leaf=0)]
    for parent_id in range(2, 17):
        nodes.append(_node(parent_id, f"分类{parent_id}", 1, f"产品 > 分类{parent_id}", leaf=0))
    for category_id in range(17, 1059):
        parent_id = 2 + (category_id % 15)
        nodes.append(
            _node(
                category_id,
                f"产品节点{category_id}",
                parent_id,
                f"产品 > 分类{parent_id} > 产品节点{category_id}",
            )
        )
    # 15 个节点共同引用缺失父节点 7035，以验证批量根因。
    for offset, category_id in enumerate(range(1000, 1015)):
        nodes[category_id - 1] = _node(
            category_id,
            ["自航起重机", "非自航起重机", "驳船式起重机"][offset] if offset < 3 else f"断裂节点{category_id}",
            7035,
            f"产品 > 起重运输设备 > 缺失分类 > 断裂节点{category_id}",
        )
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)

    for node_id in range(1000, 1015):
        _add_issue(
            settings,
            version_id,
            "missing_parent",
            node_id,
            risk="high",
            reason="父节点 7035 在当前版本中不存在",
            evidence="节点保存的父节点引用为 7035，但当前版本节点集合中没有该 ID",
        )
    for issue_type, node_ids in {
        "duplicate_name": [20, 21],
        "orphan": [22, 23],
        "duplicate_mount": [24, 25],
    }.items():
        for node_id in node_ids:
            _add_issue(settings, version_id, issue_type, node_id, risk="medium")

    content = [
        ("bad_parent_child_relation", 30, "high", "分散、混合功能与父节点的温度加工分类原则不一致"),
        ("bad_parent_child_relation", 31, "medium", "该节点与同级节点采用了不同分类维度"),
        ("synonym_pollution", 32, "medium", "同义词包含并非完全等价的复合设备名称"),
        ("synonym_pollution", 33, "medium", "同义词包含相关概念而非等价概念"),
        ("synonym_format_issue", 34, "low", "同义词列表包含节点主名称"),
        ("synonym_format_issue", 35, "low", "同义词列表存在重复值"),
    ]
    for issue_type, node_id, risk, reason in content:
        _add_issue(
            settings,
            version_id,
            issue_type,
            node_id,
            risk=risk,
            source="model_analysis" if issue_type != "synonym_format_issue" else "content_rule",
            reason=reason,
            evidence=f"AI/规则保存的证据：{reason}",
        )

    task_repo = TaskRepository(settings)
    task_id = task_repo.create_diagnosis_task(
        file_id=1,
        version_id=version_id,
        enable_ai_analysis=True,
        model_provider="deepseek",
        model_name="deepseek-chat",
    )
    task_repo.update_task(
        task_id=task_id,
        status="completed",
        current_step="completed",
        progress=100,
        result_payload={"ai_analysis_status": "completed", "candidate_count": 6, "ai_processed_count": 6},
    )
    return version_id


def test_1058_fixture_has_exact_dynamic_counts_and_complete_appendix(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_1058_fixture(settings)
    service = ReportService(settings)

    data = service.collect_report_data(version_id)
    text = service.render_markdown_report(data)

    assert data.taxonomy_statistics["node_count"] == 1058
    assert data.issue_summary["structure_total"] == 21
    assert data.issue_summary["content_total"] == 6
    assert data.issue_summary["total"] == 27
    assert sum(group["count"] for group in data.issue_summary["structure_groups"]) == 21
    assert sum(group["count"] for group in data.issue_summary["content_groups"]) == 6
    assert len(data.all_issues) == 27
    assert "| 父节点缺失 | 15 |" in text
    assert "| 重复名称 | 2 |" in text
    assert "| 孤立节点 | 2 |" in text
    assert "| 重复挂载 | 2 |" in text
    assert "| 结构问题 | 21 |" in text
    assert "| 内容问题 | 6 |" in text
    appendix = text.split("## 附录：完整问题清单", 1)[1]
    assert len(re.findall(r"^\| \d+ \|", appendix, flags=re.MULTILINE)) == 27


def test_typical_evidence_contains_structure_and_content_examples(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_1058_fixture(settings)
    text = ReportService(settings).generate_diagnosis_report(version_id).report_path.read_text(encoding="utf-8")

    assert "父子关系异常" in text
    assert "同义词污染" in text
    case_section = text.split("## 四、重点问题说明", 1)[1].split("## 五、", 1)[0]
    assert "典型问题：" in case_section
    assert "所在路径" in case_section
    assert "修改建议" in case_section


def test_no_formal_suggestions_generates_only_relevant_guidance(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_1058_fixture(settings)
    text = ReportService(settings).generate_diagnosis_report(version_id).report_path.read_text(encoding="utf-8")
    section = text.split("## 六、问题处理建议", 1)[1].split("## 七、", 1)[0]

    assert "优先处理" in section
    assert "高风险问题" in section
    assert "层级过深" not in section
    assert "节点过宽" not in section


def test_high_risk_structure_keeps_97_9_but_blocks_excellent_risk_level(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_1058_fixture(settings)
    text = ReportService(settings).generate_diagnosis_report(version_id).report_path.read_text(encoding="utf-8")
    assert "综合评分：97.9/100（需要整改）" in text
    assert "整体**需要重点治理**" in text
    assert "_calc_quality_score" not in text


def test_ai_reason_evidence_and_dynamic_content_types_enter_report(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_1058_fixture(settings)
    _add_issue(
        settings,
        version_id,
        "vague_node",
        40,
        risk="medium",
        source="model_analysis",
        reason="AI 判断该名称无法界定产品范围",
        evidence="节点名称缺少对象和用途限定",
    )
    service = ReportService(settings)
    data = service.collect_report_data(version_id)
    text = service.render_markdown_report(data)

    assert "节点含义模糊" in text
    vague = next(item for item in data.all_issues if item["issue_type"] == "vague_node")
    assert vague["reason"] == "AI 判断该名称无法界定产品范围"
    assert vague["evidence"] == "节点名称缺少对象和用途限定"


def test_empty_diagnosis_has_no_unrelated_guidance_and_all_sections_have_content(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_version(settings, score=100.0)
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[_node(1, "产品", None, "产品", leaf=1)],
    )
    text = ReportService(settings).generate_diagnosis_report(version_id).report_path.read_text(encoding="utf-8")

    assert "| 结构问题 | 0 |" in text
    assert "| 内容问题 | 0 |" in text
    assert "本次未发现需要登记的问题" in text
    guidance = text.split("## 六、问题处理建议", 1)[1].split("## 七、", 1)[0]
    assert "层级过深" not in guidance
    assert "节点过宽" not in guidance
    assert "父节点缺失" not in guidance
    for title in ("一、报告概述", "二、体系基本情况", "三、诊断结果汇总", "四、重点问题说明", "五、AI分析情况", "六、问题处理建议", "七、处理计划", "八、最终结论"):
        assert f"## {title}" in text
    assert "以任务记录为准" not in text


def test_persisted_suggestions_are_separated_from_generated_guidance(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_version(settings)
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[_node(1, "产品", None, "产品", leaf=1)],
    )
    issue_id = _add_issue(settings, version_id, "synonym_pollution", 1, risk="medium", source="model_analysis")
    SuggestionRepository(settings).create_suggestion(
        review_batch_id="report-batch",
        suggestion=AdjustmentSuggestion(
            issue_id=issue_id,
            version_id=version_id,
            action_type="clean_synonym",
            target_node_id=1,
            target_node_name="产品",
            action_payload={"synonyms_to_remove": ["相关词"]},
            reason="正式审核原因",
            suggestion="删除非等价相关词",
            risk_level="medium",
            confidence=0.9,
            need_confirm=True,
            status="pending",
        ),
    )
    text = ReportService(settings).generate_diagnosis_report(version_id).report_path.read_text(encoding="utf-8")

    assert "当前共有 **1** 条已保存建议" in text
    assert "删除非等价相关词" in text


def test_report_body_uses_business_terms_not_internal_runtime_fields(tmp_path):
    settings = _settings(tmp_path)
    version_id = _seed_1058_fixture(settings)
    text = ReportService(settings).generate_diagnosis_report(version_id).report_path.read_text(encoding="utf-8")
    body = text

    for forbidden in (
        "workflow_id",
        "ai_candidate_count",
        "content_rule",
        "model_analysis",
        "issue_type",
        "task_record",
        "_calc_quality_score",
    ):
        assert forbidden not in body
    assert "## 五、AI分析情况" in body
    assert "成功分析数量" in body
