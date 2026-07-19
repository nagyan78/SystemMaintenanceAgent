from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.task_repo import TaskRepository
from backend.app.services.quality_score_service import calculate_quality_score
from backend.app.services.ai_review_service import AIReviewService
from backend.app.schemas.suggestion import SuggestionRecord


def test_quality_score_uses_weighted_affected_node_ratio_at_large_scale():
    issues = [
        {"id": 1, "node_id": 10, "issue_type_code": "missing_parent", "status": "pending"},
        # The same node is charged only its maximum issue weight.
        {"id": 2, "node_id": 10, "issue_type_code": "synonym_format", "status": "pending"},
        {"id": 3, "node_id": 20, "issue_type_code": "synonym_format", "status": "deferred"},
        {"id": 4, "node_id": 30, "issue_type_code": "duplicate_sibling", "status": "false_positive"},
    ]

    result = calculate_quality_score(10_000, issues)

    assert result.weighted_error_count == 1.2
    assert result.weighted_error_rate == 0.00012
    assert result.score == 99.99
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
