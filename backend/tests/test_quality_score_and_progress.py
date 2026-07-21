from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.task_repo import TaskRepository
from backend.app.services.quality_score_service import (
    calculate_composite_quality_score,
    calculate_quality_score,
)
from backend.app.services.ai_review_service import AIReviewService
from backend.app.schemas.suggestion import SuggestionRecord


def test_quality_score_deducts_risk_points_per_thousand_nodes():
    issues = [
        {"id": 1, "node_id": 10, "issue_type_code": "missing_parent", "status": "pending"},
        # The same node is charged only its maximum issue weight.
        {"id": 2, "node_id": 10, "issue_type_code": "synonym_format", "status": "pending"},
        {"id": 3, "node_id": 20, "issue_type_code": "synonym_format", "status": "deferred"},
        {"id": 4, "node_id": 30, "issue_type_code": "duplicate_sibling", "status": "false_positive"},
    ]

    result = calculate_quality_score(10_000, issues)

    assert result.weighted_error_count == 11.0
    assert result.weighted_error_rate == 0.0011
    assert result.score == 98.9
    assert result.verdict == "需要整改"


def test_quality_score_is_exactly_100_only_without_active_issues():
    clean = calculate_quality_score(10_000, [{"node_id": 1, "status": "resolved"}])
    tiny_active = calculate_quality_score(
        1_000_000,
        [{"node_id": 1, "issue_type_code": "synonym_format", "status": "pending"}],
    )

    assert clean.score == 100.0
    assert clean.verdict == "质量通过"
    assert tiny_active.score == 99.99
    assert tiny_active.verdict == "需要整改"


def test_composite_quality_score_uses_all_three_components():
    issues = [
        {
            "node_id": 1,
            "issue_type_code": "missing_parent",
            "risk_level": "high",
            "source": "structure_rule",
            "status": "pending",
        },
        {
            "node_id": 2,
            "issue_type_code": "synonym_format",
            "risk_level": "low",
            "source": "content_rule",
            "status": "pending",
        },
        # AI 深诊断问题只进入抽样评分，不在规则内容分中重复扣分。
        {
            "node_id": 3,
            "issue_type_code": "semantic_misplacement",
            "risk_level": "high",
            "source": "model_analysis",
            "status": "pending",
        },
    ]

    result = calculate_composite_quality_score(
        100,
        issues,
        ai_content_sample_score=75.0,
    )

    assert result.structure_score == 90.0
    assert result.content_rule_score == 99.0
    assert result.ai_content_sample_score == 75.0
    assert result.overall_quality_score == 83.4


def test_composite_quality_score_is_unrated_without_ai_sample():
    result = calculate_composite_quality_score(
        100,
        [],
        ai_content_sample_score=None,
    )

    assert result.structure_score == 100.0
    assert result.content_rule_score == 100.0
    assert result.overall_quality_score is None


def test_successful_terminal_task_forces_execution_progress_to_100(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO uploaded_file (id, file_name, file_path, file_size, status) VALUES (1, 'test.xlsx', 'test.xlsx', 1, 'uploaded')"
        )
    repo = TaskRepository(settings)
    task_id = repo.create_task(file_id=1, task_type="test")

    repo.update_task(task_id=task_id, status="partial", progress=62)

    assert repo.get_task(task_id)["progress"] == 100


def test_independent_ai_review_accepts_high_risk_action_without_human_gate():
    class Response:
        content = '{"decisions":[{"suggestion_id":7,"verdict":"approve","decision_summary":"目标与完整路径一致"}]}'

    class LLM:
        def invoke(self, _messages):
            return Response()

    suggestion = SuggestionRecord(
        id=7,
        review_batch_id="review-test",
        issue_id=3,
        version_id=1,
        action_type="move_node",
        target_node_id=10,
        new_parent_id=20,
        action_payload={"old_path": "A > B", "new_path": "A > C > B"},
        reason="产品维度归属错误",
        suggestion="迁移整棵子树",
        risk_level="high",
        confidence=0.9,
        need_confirm=True,
    )

    result = AIReviewService(LLM()).review([suggestion])

    assert result.completed is True
    assert result.decisions[0]["verdict"] == "approve"


def test_incomplete_independent_ai_review_is_not_an_execution_pass():
    class Response:
        content = '{"decisions":[]}'

    class LLM:
        def invoke(self, _messages):
            return Response()

    suggestion = SuggestionRecord(
        id=8,
        review_batch_id="review-test",
        issue_id=4,
        version_id=1,
        action_type="rename_node",
        target_node_id=10,
        old_name="旧名称",
        new_name="新名称",
        action_payload={"new_name": "新名称"},
        reason="命名不规范",
        suggestion="修改名称",
        risk_level="low",
        confidence=0.9,
        need_confirm=True,
    )

    result = AIReviewService(LLM()).review([suggestion])

    assert result.completed is False
    assert "禁止自动执行" in (result.warning or "")
