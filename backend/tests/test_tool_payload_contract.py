import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord, DiagnosisPlan
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.tools.tree_tools import configure_tree_tool_runtime, submit_diagnosis
from backend.app.tools.validation_tools import configure_validation_tool_runtime, validate_action


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def _seed(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(
        file_id=1, version_no="v1.0", description="test"
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="水果",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="水果",
                syn_list="AirPods, 红富士",
                is_leaf=1,
            )
        ],
    )
    issue_id = DiagnosisRepository(settings).create_issue(
        version_id=version_id,
        issue=DiagnosisIssueRecord(
            issue_type="synonym_pollution",
            node_id=1,
            node_name="水果",
            description="同义词污染",
            reason="测试",
            risk_level="medium",
            confidence=0.9,
        ),
    )
    return version_id, issue_id


def _suggestion(version_id: int, issue_id: int) -> dict:
    return {
        "issue_id": issue_id,
        "version_id": version_id,
        "action_type": "clean_synonym",
        "target_node_id": 1,
        "target_node_name": "水果",
        "action_payload": {"synonyms_to_remove": ["AirPods"]},
        "reason": "电子产品词不属于水果同义词",
        "suggestion": "删除 AirPods",
        "risk_level": "medium",
        "confidence": 0.95,
    }


def test_suggestion_tool_coerces_json_string_before_pydantic_validation(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)
    agent = SuggestionAgent(settings=settings, llm=None)
    payload = _suggestion(version_id, issue_id)

    result = agent._execute_tool_call(
        {
            "id": "call_submit",
            "name": "submit_suggestion",
            "args": {"suggestion": json.dumps(payload, ensure_ascii=False)},
        },
        [],
    )

    assert result is not None
    assert result.action_type == "clean_synonym"
    assert result.target_node_id == 1


def test_validate_action_accepts_object_and_json_string(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)
    configure_validation_tool_runtime(settings)
    payload = _suggestion(version_id, issue_id)

    assert validate_action.invoke({"action_json": payload})["valid"] is True
    assert validate_action.invoke({"action_json": json.dumps(payload)})["valid"] is True


def test_content_diagnosis_coerces_json_string_before_submit(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    configure_tree_tool_runtime(settings=settings)
    agent = ContentDiagnosisAgent(settings=settings, llm=None, tools=[submit_diagnosis])
    issue = {
        "version_id": version_id,
        "node_id": 1,
        "node_name": "水果",
        "issue_type": "synonym_pollution",
        "description": "同义词包含电子产品词",
        "reason": "跨领域词汇",
        "risk_level": "medium",
        "confidence": 0.9,
    }

    result = agent._execute_tool_call(
        {
            "id": "call_diagnosis",
            "name": "submit_diagnosis",
            "args": {"issue": json.dumps(issue, ensure_ascii=False)},
        },
        [],
    )

    assert result is not None
    assert result.issue_type == "synonym_pollution"
    assert result.node_id == 1


def test_malformed_or_unknown_tool_call_is_returned_to_the_agent_for_correction(tmp_path) -> None:
    settings = _settings(tmp_path)
    agent = SuggestionAgent(settings=settings, llm=None)
    messages: list[object] = []

    result = agent._execute_tool_call(
        {"id": "call_unknown", "name": "unknown_tool", "args": {}}, messages
    )

    assert result is None
    assert len(messages) == 1
    assert "unknown_tool" in agent.trace_log[-1]


def test_suggestion_agent_responds_to_every_tool_call_before_retrying(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)
    checked_protocol = False

    class ProtocolCheckingLLM:
        calls = 0

        def bind_tools(self, tools: list[Any]):
            return self

        def invoke(self, messages: list[Any]):
            nonlocal checked_protocol
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="先提交建议，再补充节点上下文。",
                    tool_calls=[
                        {
                            "id": "call_submit",
                            "name": "submit_suggestion",
                            "args": {"suggestion": _suggestion(version_id, issue_id) | {"action_payload": {"synonyms_to_remove": ["不存在"]}}},
                        },
                        {
                            "id": "call_detail",
                            "name": "get_node_detail",
                            "args": {"version_id": version_id, "category_id": 1},
                        },
                    ],
                )
            tool_ids = {message.tool_call_id for message in messages if isinstance(message, ToolMessage)}
            assert {"call_submit", "call_detail"}.issubset(tool_ids)
            checked_protocol = True
            return AIMessage(content="没有可提交的修正建议。")

    @tool
    def submit_suggestion(suggestion: dict[str, Any]) -> dict[str, Any]:
        """Accept a suggestion."""
        return {"valid": True}

    @tool
    def get_node_detail(version_id: int, category_id: int) -> dict[str, Any]:
        """Return node details."""
        return {"category_id": category_id}

    agent = SuggestionAgent(
        settings=settings,
        llm=ProtocolCheckingLLM(),
        tools=[submit_suggestion, get_node_detail],
        max_iter=2,
        max_retry=1,
    )

    result = agent.run(version_id)

    assert result.generated_count == 0
    assert checked_protocol is True


def test_content_agent_completes_tool_batch_after_submitting_issue(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    observed_details: list[int] = []

    class BatchedToolLLM:
        def bind_tools(self, tools: list[Any]):
            return self

        def invoke(self, messages: list[Any]):
            return AIMessage(
                content="确认问题后补充节点详情。",
                tool_calls=[
                    {
                        "id": "call_issue",
                        "name": "submit_diagnosis",
                        "args": {
                            "issue": {
                                "version_id": version_id,
                                "node_id": 1,
                                "node_name": "水果",
                                "issue_type": "synonym_pollution",
                                "description": "同义词包含电子产品词",
                                "reason": "跨领域词汇",
                                "risk_level": "medium",
                                "confidence": 0.9,
                            }
                        },
                    },
                    {
                        "id": "call_detail",
                        "name": "get_node_detail",
                        "args": {"version_id": version_id, "category_id": 1},
                    },
                ],
            )

    @tool
    def submit_diagnosis(issue: dict[str, Any]) -> str:
        """Accept a diagnosis issue."""
        return "issue-1"

    @tool
    def get_node_detail(version_id: int, category_id: int) -> dict[str, Any]:
        """Return node details."""
        observed_details.append(category_id)
        return {"category_id": category_id}

    agent = ContentDiagnosisAgent(
        settings=settings,
        llm=BatchedToolLLM(),
        tools=[submit_diagnosis, get_node_detail],
        candidate_selector=lambda version_id, plan: [{"category_id": 1, "category_name": "水果"}],
    )

    issues = agent.run(version_id=version_id, plan=DiagnosisPlan())

    assert len(issues) == 1
    assert observed_details == [1]


def test_suggestion_agent_responds_to_invalid_tool_calls_before_retrying(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    checked_protocol = False

    class InvalidToolCallLLM:
        calls = 0

        def bind_tools(self, tools: list[Any]):
            return self

        def invoke(self, messages: list[Any]):
            nonlocal checked_protocol
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="调用建议工具。",
                    invalid_tool_calls=[
                        {
                            "id": "call_bad_json",
                            "name": "submit_suggestion",
                            "args": '{"suggestion":',
                            "error": "arguments is not valid JSON",
                        }
                    ],
                )
            assert any(
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call_bad_json"
                for message in messages
            )
            checked_protocol = True
            return AIMessage(content="停止。")

    agent = SuggestionAgent(
        settings=settings,
        llm=InvalidToolCallLLM(),
        max_iter=2,
        max_retry=1,
    )

    assert agent.run(version_id).generated_count == 0
    assert checked_protocol is True


def test_content_agent_responds_to_invalid_tool_calls_before_retrying(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    checked_protocol = False

    class InvalidToolCallLLM:
        calls = 0

        def bind_tools(self, tools: list[Any]):
            return self

        def invoke(self, messages: list[Any]):
            nonlocal checked_protocol
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="调用诊断工具。",
                    invalid_tool_calls=[
                        {
                            "id": "call_bad_issue",
                            "name": "submit_diagnosis",
                            "args": '{"issue":',
                            "error": "arguments is not valid JSON",
                        }
                    ],
                )
            assert any(
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call_bad_issue"
                for message in messages
            )
            checked_protocol = True
            return AIMessage(content="停止。")

    agent = ContentDiagnosisAgent(
        settings=settings,
        llm=InvalidToolCallLLM(),
        candidate_selector=lambda version_id, plan: [{"category_id": 1, "category_name": "水果"}],
        max_iter=2,
    )

    assert agent.run(version_id=version_id, plan=DiagnosisPlan()) == []
    assert checked_protocol is True
