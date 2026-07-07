from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
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


def _insert_version_with_issue(settings: Settings, issue_type: str = "wide_node") -> int:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(
        file_id=1,
        version_no="v1.0",
        description="test",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=10,
                category_name="水果",
                parent_id=None,
                level=1,
                path_ids="10",
                path_names="水果",
                syn_list=None,
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=11,
                category_name="苹果",
                parent_id=10,
                level=2,
                path_ids="10,11",
                path_names="水果 > 苹果",
                syn_list="AirPods, iPhone, Apple Pencil, Apple Music",
                is_leaf=1,
            ),
        ],
    )
    DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type=issue_type,
            node_id=11,
            node_name="苹果",
            description="测试诊断问题",
            reason="测试原因",
            risk_level="medium",
            confidence=0.8,
        ),
    )
    return version_id


class FakeSuggestionLLM:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="Thought: 查询节点详情。",
                tool_calls=[
                    {
                        "id": "call_detail",
                        "name": "get_node_detail",
                        "args": {"version_id": 1, "category_id": 11},
                    }
                ],
            )
        if self.calls == 2:
            return AIMessage(
                content="Thought: 先校验建议。",
                tool_calls=[
                    {
                        "id": "call_validate",
                        "name": "validate_action",
                        "args": {
                            "action_json": '{"issue_id":1,"version_id":1,"action_type":"clean_synonym","target_node_id":11,"target_node_name":"苹果","old_parent_id":null,"new_parent_id":null,"old_name":null,"new_name":null,"action_payload":{"synonyms_to_remove":["AirPods"]},"reason":"水果节点混入电子产品词","suggestion":"删除 AirPods 同义词","risk_level":"medium","confidence":0.9,"need_confirm":true}'
                        },
                    }
                ],
            )
        return AIMessage(
            content="Thought: 校验通过，提交建议。",
            tool_calls=[
                {
                    "id": "call_submit",
                    "name": "submit_suggestion",
                    "args": {
                        "suggestion": {
                            "issue_id": 1,
                            "version_id": 1,
                            "action_type": "clean_synonym",
                            "target_node_id": 11,
                            "target_node_name": "苹果",
                            "old_parent_id": None,
                            "new_parent_id": None,
                            "old_name": None,
                            "new_name": None,
                            "action_payload": {"synonyms_to_remove": ["AirPods"]},
                            "reason": "水果节点混入电子产品词",
                            "suggestion": "删除 AirPods 同义词",
                            "risk_level": "medium",
                            "confidence": 0.9,
                            "need_confirm": True,
                        }
                    },
                }
            ],
        )


def test_init_db_adds_review_batch_id_column(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)

    with connect(settings) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(adjustment_suggestion)").fetchall()
        }

    assert "review_batch_id" in columns


def test_diagnosis_repository_lists_pending_issues(tmp_path):
    settings = _settings(tmp_path)
    version_id = _insert_version_with_issue(settings)

    issues = DiagnosisRepository(settings).list_pending_issues(version_id)

    assert len(issues) == 1
    assert issues[0]["issue_type"] == "wide_node"


def test_suggestion_agent_generates_rule_based_review_batch(tmp_path):
    from backend.app.services.suggestion_service import SuggestionAgent

    settings = _settings(tmp_path)
    version_id = _insert_version_with_issue(settings, "wide_node")

    result = SuggestionAgent(settings).run(version_id)

    assert result.generated_count == 1
    assert result.review_batch_id is not None
    assert result.suggestions[0].action_type == "split_subtree"
    assert result.suggestions[0].status == "pending"


def test_suggestion_agent_runs_llm_tool_loop_and_trace(tmp_path):
    from backend.app.services.suggestion_service import SuggestionAgent

    settings = _settings(tmp_path)
    version_id = _insert_version_with_issue(settings, "synonym_pollution")
    submitted: list[dict[str, Any]] = []

    @tool
    def get_node_detail(version_id: int, category_id: int) -> dict:
        """Return node detail."""
        return {"category_id": 11, "category_name": "苹果", "syn_list": "AirPods, iPhone"}

    @tool
    def validate_action(action_json: str) -> dict:
        """Validate action."""
        return {"valid": True, "reason": ""}

    @tool
    def submit_suggestion(suggestion: dict) -> str:
        """Submit suggestion."""
        submitted.append(suggestion)
        return "ok"

    agent = SuggestionAgent(
        settings,
        llm=FakeSuggestionLLM(),
        tools=[get_node_detail, validate_action, submit_suggestion],
    )

    result = agent.run(version_id)

    assert result.generated_count == 1
    assert submitted[0]["action_type"] == "clean_synonym"
    repo_records = SuggestionRepository(settings).list_suggestions(
        review_batch_id=result.review_batch_id,
    )
    assert len(repo_records) == 1
    assert any("Action: get_node_detail" in item for item in agent.trace_log)
    assert any("Action: validate_action" in item for item in agent.trace_log)


def test_review_service_approves_and_logs_without_modifying_nodes(tmp_path):
    from backend.app.services.review_service import ReviewService
    from backend.app.services.suggestion_service import SuggestionAgent

    settings = _settings(tmp_path)
    version_id = _insert_version_with_issue(settings, "duplicate_name")
    before_nodes = TaxonomyRepository(settings).list_nodes(version_id)
    suggestion = SuggestionAgent(settings).run(version_id).suggestions[0]

    approved = ReviewService(settings).approve_suggestion(suggestion.id, "tester")

    assert approved.status == "approved"
    assert TaxonomyRepository(settings).list_nodes(version_id) == before_nodes
    with connect(settings) as connection:
        log_count = connection.execute("SELECT COUNT(*) FROM operation_log").fetchone()[0]
    assert log_count == 1


def test_review_service_rejects_batch_approve_for_medium_risk(tmp_path):
    from backend.app.services.review_service import ReviewService
    from backend.app.services.suggestion_service import SuggestionAgent

    settings = _settings(tmp_path)
    version_id = _insert_version_with_issue(settings, "wide_node")
    suggestion = SuggestionAgent(settings).run(version_id).suggestions[0]

    try:
        ReviewService(settings).batch_approve([suggestion.id], "tester")
    except ValueError as exc:
        assert "low 风险" in str(exc)
    else:
        raise AssertionError("Expected batch approve to reject medium risk suggestion.")


def test_validate_approved_actions_returns_passed_result(tmp_path):
    from backend.app.services.action_service import ActionService
    from backend.app.services.review_service import ReviewService
    from backend.app.services.suggestion_service import SuggestionAgent

    settings = _settings(tmp_path)
    version_id = _insert_version_with_issue(settings, "duplicate_name")
    result = SuggestionAgent(settings).run(version_id)
    suggestion = result.suggestions[0]
    ReviewService(settings).approve_suggestion(suggestion.id, "tester")

    validations = ActionService(settings).validate_approved_actions(result.review_batch_id)

    assert validations[0].valid is True
    assert validations[0].suggestion_id == suggestion.id


def test_graph_topology_routes_content_to_suggestion_and_m4_execution_after_validate(tmp_path):
    from backend.app.agents.graph import build_taxonomy_graph

    graph = build_taxonomy_graph(settings=_settings(tmp_path))
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("content_diagnosis_node", "generate_suggestion_node") in edges
    assert ("generate_suggestion_node", "wait_human_review_node") in edges
    assert ("validate_action_node", "execute_action_node") in edges
    assert ("execute_action_node", "save_new_version_node") in edges
    assert ("save_new_version_node", "generate_report_node") in edges
