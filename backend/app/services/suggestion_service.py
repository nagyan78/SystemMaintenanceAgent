import json
import logging
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from backend.app.agents.prompts import SUGGESTION_GENERATION_SYSTEM_PROMPT
from backend.app.config import Settings, get_settings
from backend.app.services.model_service import ModelService
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion, SuggestionGenerationResult, SuggestionRecord
from backend.app.services.tool_factory import AgentResourceLimits, AgentToolFactory
from backend.app.tools.validation_tools import (
    validate_suggestion_action,
)

logger = logging.getLogger(__name__)


class SuggestionAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm: Any | None = None,
        tools: list[Any] | None = None,
        max_iter: int = 8,
        max_retry: int = 3,
        enable_ai: bool = True,
        review_batch_id: str | None = None,
        work_item_id: str | None = None,
        analysis_run_id: str | None = None,
        workflow_id: str | None = None,
        event_sink: Any | None = None,
        resource_limits: AgentResourceLimits | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.review_batch_id = review_batch_id or f"review_{uuid4().hex[:12]}"
        self.work_item_id = work_item_id
        self.analysis_run_id = analysis_run_id
        self.workflow_id = workflow_id
        self.event_sink = event_sink
        self.suggestion_repo = SuggestionRepository(self.settings)
        self.llm = (llm or self._create_llm()) if enable_ai else None
        self.uses_internal_submit_tool = tools is None
        self.tools = tools or AgentToolFactory(self.settings, resource_limits=resource_limits).suggestion_tools(self._submit_suggestion_tool())
        self.tool_map = {item.name: item for item in self.tools}
        self.max_iter = max_iter
        self.max_retry = max_retry
        self.trace_log: list[str] = []

    def run(self, version_id: int, issue_ids: list[int] | None = None) -> SuggestionGenerationResult:
        issues = DiagnosisRepository(self.settings).list_pending_issues(version_id)
        if issue_ids is not None:
            allowed = set(issue_ids)
            issues = [issue for issue in issues if int(issue["id"]) in allowed]
        records: list[SuggestionRecord] = []
        for issue in issues:
            record = self._rule_based_suggestion_record(version_id, issue)
            if record is None and self.llm is not None:
                record = self._generate_llm_suggestion_record(version_id, issue)
            if record is None:
                continue
            records.append(record)
        return SuggestionGenerationResult(
            version_id=version_id,
            review_batch_id=self.review_batch_id if records else None,
            generated_count=len(records),
            suggestions=records,
        )

    def _generate_llm_suggestion_record(self, version_id: int, issue: dict[str, Any]) -> SuggestionRecord | None:
        llm_with_tools = self.llm.bind_tools(self.tools)
        messages: list[Any] = [
            SystemMessage(content=SUGGESTION_GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=_issue_prompt(version_id, issue)),
        ]
        for _ in range(self.max_retry):
            for _ in range(self.max_iter):
                response = llm_with_tools.invoke(messages)
                self._trace(f"Thought: {response.content}")
                tool_calls = getattr(response, "tool_calls", []) or []
                if not tool_calls:
                    messages.append(response)
                    messages.append(HumanMessage(content="请继续调用工具查询、validate_action 校验，或 submit_suggestion 提交建议。"))
                    continue
                messages.append(response)
                for tool_call in tool_calls:
                    record = self._execute_tool_call(tool_call, messages)
                    if record is None:
                        continue
                    validation = validate_suggestion_action(
                        AdjustmentSuggestion.model_validate(record.model_dump(exclude={"id", "review_batch_id"})),
                        self.settings,
                    )
                    if validation.valid:
                        return record
                    messages.append(HumanMessage(content=f"校验失败：{validation.reason}。请修正建议后重新生成。"))
                    break
        logger.warning("Suggestion agent max_retry exhausted for issue %s", issue.get("id"))
        return None

    def _execute_tool_call(self, tool_call: dict[str, Any], messages: list[Any]) -> SuggestionRecord | None:
        name = tool_call["name"]
        args = tool_call.get("args") or {}
        self._trace(f"Action: {name} {json.dumps(args, ensure_ascii=False)}")
        if self.event_sink:
            self.event_sink({"event_type": "agent_step", "tool_name": name, "status": "running", "summary": {"action": "tool_started"}})
        observation = self.tool_map[name].invoke(args)
        self._trace(f"Observation: {observation}")
        if self.event_sink:
            self.event_sink({"event_type": "agent_tool_completed", "tool_name": name, "status": "completed", "summary": {"result_type": type(observation).__name__}})
        messages.append(
            ToolMessage(
                content=json.dumps(observation, ensure_ascii=False),
                tool_call_id=tool_call.get("id", name),
            )
        )
        if name != "submit_suggestion":
            return None
        suggestion = AdjustmentSuggestion.model_validate(args["suggestion"])
        if self.uses_internal_submit_tool:
            payload = _load_observation(observation)
            suggestion_id = int(payload["suggestion_id"])
        else:
            suggestion_id = self.suggestion_repo.create_suggestion(
                review_batch_id=self.review_batch_id,
                suggestion=suggestion,
                work_item_id=self.work_item_id,
                analysis_run_id=self.analysis_run_id,
                workflow_id=self.workflow_id,
            )
        return SuggestionRecord(
            id=suggestion_id,
            review_batch_id=self.review_batch_id,
            **suggestion.model_dump(),
        )

    def _rule_based_suggestion_record(self, version_id: int, issue: dict[str, Any]) -> SuggestionRecord | None:
        issue_type = issue["issue_type"]
        if issue_type == "wide_node":
            suggestion = _suggestion_from_issue(
                version_id,
                issue,
                action_type="split_subtree",
                suggestion="建议为该过宽节点设计更细的中间分类，拆分前需人工确认拆分方案。",
                risk_level="high",
                action_payload={"strategy": "manual_split_plan"},
            )
        elif issue_type in {"duplicate_name", "deep_level"}:
            suggestion = _suggestion_from_issue(
                version_id,
                issue,
                action_type="mark_as_valid",
                suggestion="建议先标记为需人工判断的合理复用或可接受结构，不自动调整节点。",
                risk_level="low",
                action_payload={"mark_reason": issue.get("description", "")},
                need_confirm=False,
            )
        elif issue_type == "missing_parent":
            suggestion = _suggestion_from_issue(
                version_id,
                issue,
                action_type="add_node",
                suggestion="建议补齐缺失父节点或中间分类，新增前需人工确认名称与位置。",
                risk_level="medium",
                action_payload={"source": "missing_parent"},
            )
        else:
            return None
        validation = validate_suggestion_action(suggestion, self.settings)
        if not validation.valid:
            logger.warning("suggestion validation failed: %s", validation.reason)
            return None
        suggestion_id = self.suggestion_repo.create_suggestion(
            review_batch_id=self.review_batch_id,
            suggestion=suggestion,
            work_item_id=self.work_item_id,
            analysis_run_id=self.analysis_run_id,
            workflow_id=self.workflow_id,
        )
        return SuggestionRecord(
            id=suggestion_id,
            review_batch_id=self.review_batch_id,
            **suggestion.model_dump(),
        )

    def _submit_suggestion_tool(self):
        agent = self

        @tool
        def submit_suggestion(suggestion: dict) -> str:
            """提交一条维护建议，返回建议 ID。"""
            record = AdjustmentSuggestion.model_validate(suggestion)
            validation = validate_suggestion_action(record, agent.settings)
            if not validation.valid:
                return json.dumps({"valid": False, "reason": validation.reason}, ensure_ascii=False)
            suggestion_id = agent.suggestion_repo.create_suggestion(
                review_batch_id=agent.review_batch_id,
                suggestion=record,
                work_item_id=agent.work_item_id,
                analysis_run_id=agent.analysis_run_id,
                workflow_id=agent.workflow_id,
            )
            return json.dumps(
                {
                    "valid": True,
                    "suggestion_id": suggestion_id,
                    "review_batch_id": agent.review_batch_id,
                },
                ensure_ascii=False,
            )

        return submit_suggestion

    def _create_llm(self) -> Any:
        return ModelService(self.settings).get_chat_model(temperature=0.1)

    def _trace(self, message: str) -> None:
        self.trace_log.append(message)
        logger.info("suggestion_generation_react %s", message)


def _issue_prompt(version_id: int, issue: dict[str, Any]) -> str:
    return json.dumps(
        {
            "version_id": version_id,
            "issue": issue,
            "instruction": "请按 Thought-Action-Observation 循环生成维护建议。",
        },
        ensure_ascii=False,
    )


def _suggestion_from_issue(
    version_id: int,
    issue: dict[str, Any],
    *,
    action_type: str,
    suggestion: str,
    risk_level: str,
    action_payload: dict[str, Any],
    need_confirm: bool = True,
) -> AdjustmentSuggestion:
    return AdjustmentSuggestion(
        issue_id=int(issue["id"]),
        version_id=version_id,
        action_type=action_type,
        target_node_id=issue.get("node_id"),
        target_node_name=issue.get("node_name"),
        action_payload=action_payload,
        reason=issue.get("reason") or issue.get("description") or "诊断问题需要治理建议。",
        suggestion=suggestion,
        risk_level=risk_level,
        confidence=float(issue.get("confidence") or 0.5),
        need_confirm=need_confirm,
    )


def _load_observation(observation: Any) -> dict[str, Any]:
    if isinstance(observation, dict):
        return observation
    if isinstance(observation, str):
        loaded = json.loads(observation)
        if isinstance(loaded, dict):
            return loaded
    raise ValueError("submit_suggestion observation must be a JSON object.")
