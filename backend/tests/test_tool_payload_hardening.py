import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord, DiagnosisPlan
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.services.tool_factory import AgentToolFactory
from backend.app.tools.payload_tools import coerce_json_object


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _seed(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO uploaded_file (id, file_name, file_path) VALUES (1, 'test.xlsx', 'test.xlsx')"
        )
    version_id = VersionRepository(settings).create_version(
        file_id=1, version_no="v1.0", description="tool payload test"
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


def _suggestion(version_id: int, issue_id: int) -> dict[str, Any]:
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
        "need_confirm": True,
    }


def test_coerce_json_object_accepts_mapping_and_string_only() -> None:
    assert coerce_json_object({"a": 1}, field_name="payload") == {"a": 1}
    assert coerce_json_object('{"a": 1}', field_name="payload") == {"a": 1}
    with pytest.raises(ValueError, match="JSON 对象"):
        coerce_json_object("[1]", field_name="payload")


def test_factory_validation_accepts_object_and_json_string(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)

    @tool
    def submit_suggestion(suggestion: dict[str, Any]) -> str:
        """Submit a suggestion."""
        return "ok"

    validate = next(
        item
        for item in AgentToolFactory(settings).suggestion_tools(submit_suggestion)
        if item.name == "validate_action"
    )
    payload = _suggestion(version_id, issue_id)

    assert validate.invoke({"action_json": payload})["valid"] is True
    assert validate.invoke({"action_json": json.dumps(payload)})["valid"] is True


def test_suggestion_agent_coerces_nested_json_string(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, issue_id = _seed(settings)
    agent = SuggestionAgent(settings=settings, llm=None)

    result = agent._execute_tool_call(
        {
            "id": "call_submit",
            "name": "submit_suggestion",
            "args": {"suggestion": json.dumps(_suggestion(version_id, issue_id), ensure_ascii=False)},
        },
        [],
    )

    assert result is not None
    assert result.action_type == "update_synonyms"


def test_unknown_tool_call_returns_feedback_instead_of_raising(tmp_path) -> None:
    agent = SuggestionAgent(settings=_settings(tmp_path), llm=None)
    messages: list[Any] = []

    assert agent._execute_tool_call(
        {"id": "call_unknown", "name": "unknown_tool", "args": {}}, messages
    ) is None
    assert isinstance(messages[0], ToolMessage)
    assert messages[0].tool_call_id == "call_unknown"


def test_content_agent_finishes_entire_tool_batch_after_submit(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    observed_details: list[int] = []

    class BatchedToolLLM:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return AIMessage(
                content="submit and inspect",
                tool_calls=[
                    {
                        "id": "call_issue",
                        "name": "submit_diagnosis",
                        "args": {"issue": {
                            "version_id": version_id,
                            "node_id": 1,
                            "node_name": "水果",
                            "issue_type": "synonym_pollution",
                            "description": "同义词包含电子产品词",
                            "reason": "跨领域词汇",
                            "risk_level": "medium",
                            "confidence": 0.9,
                        }},
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
        """Submit a diagnosis."""
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
        candidate_selector=lambda current_version_id, plan: [
            {"category_id": 1, "category_name": "水果"}
        ],
    )

    issues = agent.run(version_id=version_id, plan=DiagnosisPlan())

    assert len(issues) == 1
    assert observed_details == [1]


def test_suggestion_agent_answers_invalid_tool_call_before_retry(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    protocol_checked = False

    class InvalidToolCallLLM:
        calls = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            nonlocal protocol_checked
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="invalid call",
                    invalid_tool_calls=[{
                        "id": "call_bad_json",
                        "name": "submit_suggestion",
                        "args": '{"suggestion":',
                        "error": "arguments is not valid JSON",
                    }],
                )
            protocol_checked = any(
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call_bad_json"
                for message in messages
            )
            return AIMessage(content="stop")

    @tool
    def get_node_detail(version_id: int, category_id: int) -> dict[str, Any]:
        """Return node details."""
        return {"category_id": category_id}

    agent = SuggestionAgent(
        settings=settings,
        llm=InvalidToolCallLLM(),
        tools=[get_node_detail],
        max_iter=2,
        max_retry=1,
    )

    assert agent.run(version_id).generated_count == 0
    assert protocol_checked is True


def test_content_agent_answers_invalid_tool_call_before_retry(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id, _ = _seed(settings)
    protocol_checked = False

    class InvalidToolCallLLM:
        calls = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            nonlocal protocol_checked
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="invalid call",
                    invalid_tool_calls=[{
                        "id": "call_bad_issue",
                        "name": "submit_diagnosis",
                        "args": '{"issue":',
                        "error": "arguments is not valid JSON",
                    }],
                )
            protocol_checked = any(
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call_bad_issue"
                for message in messages
            )
            return AIMessage(content="stop")

    agent = ContentDiagnosisAgent(
        settings=settings,
        llm=InvalidToolCallLLM(),
        candidate_selector=lambda current_version_id, plan: [
            {"category_id": 1, "category_name": "水果"}
        ],
        max_iter=2,
    )

    assert agent.run(version_id=version_id, plan=DiagnosisPlan()) == []
    assert protocol_checked is True
