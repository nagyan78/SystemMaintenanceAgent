import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from backend.app.agents.prompts import SUGGESTION_GENERATION_SYSTEM_PROMPT
from backend.app.config import Settings, get_settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion, SuggestionGenerationResult, SuggestionRecord
from backend.app.tools.tree_tools import (
    configure_tree_tool_runtime,
    get_children,
    get_node_detail,
    get_node_path,
    search_similar_nodes,
)
from backend.app.tools.validation_tools import (
    configure_validation_tool_runtime,
    validate_action,
    validate_suggestion_action,
)
from backend.app.tools.payload_tools import coerce_json_object

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
    ) -> None:
        self.settings = settings or get_settings()
        configure_tree_tool_runtime(settings=self.settings)
        configure_validation_tool_runtime(self.settings)
        self.suggestion_repo = SuggestionRepository(self.settings)
        self.llm = llm or self._create_llm()
        self.uses_internal_submit_tool = tools is None
        self.tools = tools or [
            get_node_detail,
            get_node_path,
            get_children,
            search_similar_nodes,
            validate_action,
            self._submit_suggestion_tool(),
        ]
        self.tool_map = {item.name: item for item in self.tools}
        self.max_iter = max_iter
        self.max_retry = max_retry
        self.trace_log: list[str] = []
        self.workflow_id: str | None = None
        self.analysis_run_id: str | None = None

    def run(
        self,
        version_id: int,
        *,
        workflow_id: str | None = None,
        analysis_run_id: str | None = None,
    ) -> SuggestionGenerationResult:
        self.workflow_id = workflow_id
        self.analysis_run_id = analysis_run_id
        issues = DiagnosisRepository(self.settings).list_pending_issues(
            version_id,
            analysis_run_id=analysis_run_id,
        )
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
                invalid_tool_calls = getattr(response, "invalid_tool_calls", []) or []
                if not tool_calls and not invalid_tool_calls:
                    messages.append(response)
                    messages.append(HumanMessage(content="请继续调用工具查询、validate_action 校验，或 submit_suggestion 提交建议。"))
                    continue
                messages.append(response)
                for invalid_tool_call in invalid_tool_calls:
                    self._record_tool_error(
                        str(invalid_tool_call.get("name") or "unknown_tool"),
                        invalid_tool_call,
                        messages,
                        str(invalid_tool_call.get("error") or "工具参数不是合法 JSON，请使用 JSON 对象重试。"),
                    )
                submitted_records: list[SuggestionRecord] = []
                for tool_call in tool_calls:
                    if (
                        str(tool_call.get("name") or "") == "submit_suggestion"
                        and submitted_records
                    ):
                        self._record_tool_error(
                            "submit_suggestion",
                            tool_call,
                            messages,
                            "同一轮只能提交一条建议，请在下一轮继续。",
                        )
                        continue
                    record = self._execute_tool_call(tool_call, messages)
                    if record is not None:
                        submitted_records.append(record)

                # Every tool call from this assistant response must receive a
                # ToolMessage before we validate, retry, or invoke the model
                # again.  OpenAI-compatible tool APIs reject an incomplete
                # tool-call batch with a 400 error.
                for record in submitted_records:
                    validation = validate_suggestion_action(
                        AdjustmentSuggestion.model_validate(record.model_dump(exclude={"id"})),
                        self.settings,
                    )
                    if validation.valid:
                        return record
                    messages.append(HumanMessage(content=f"校验失败：{validation.reason}。请修正建议后重新生成。"))
        logger.warning("Suggestion agent max_retry exhausted for issue %s", issue.get("id"))
        return None

    def _execute_tool_call(self, tool_call: dict[str, Any], messages: list[Any]) -> SuggestionRecord | None:
        name = str(tool_call.get("name") or "")
        try:
            args = coerce_json_object(tool_call.get("args") or {}, field_name=f"{name} 参数")
            if name == "submit_suggestion":
                args["suggestion"] = coerce_json_object(
                    args.get("suggestion", {}), field_name="suggestion"
                )
            tool_obj = self.tool_map[name]
        except (KeyError, ValueError) as exc:
            self._record_tool_error(name, tool_call, messages, str(exc))
            return None
        self._trace(f"Action: {name} {json.dumps(args, ensure_ascii=False)}")
        try:
            observation = tool_obj.invoke(args)
        except Exception as exc:
            self._record_tool_error(name, tool_call, messages, str(exc))
            return None
        self._trace(f"Observation: {observation}")
        messages.append(
            ToolMessage(
                content=json.dumps(observation, ensure_ascii=False),
                tool_call_id=str(tool_call.get("id") or name),
            )
        )
        if name != "submit_suggestion":
            return None
        try:
            suggestion = AdjustmentSuggestion.model_validate(args["suggestion"])
            if self.uses_internal_submit_tool:
                payload = _load_observation(observation)
                if not payload.get("valid"):
                    return None
                suggestion_id = int(payload["suggestion_id"])
            else:
                suggestion_id = self.suggestion_repo.create_suggestion(
                    workflow_id=self.workflow_id,
                    analysis_run_id=self.analysis_run_id,
                    suggestion=suggestion,
                )
        except Exception as exc:
            # The tool response has already been appended above.  Convert any
            # local parsing/persistence failure into agent feedback instead of
            # abandoning other calls in the same batch.
            self._trace(f"Observation: submit_suggestion response could not be processed: {exc}")
            return None
        return SuggestionRecord(
            id=suggestion_id,
            **suggestion.model_dump(),
        )

    def _rule_based_suggestion_record(self, version_id: int, issue: dict[str, Any]) -> SuggestionRecord | None:
        issue_type = issue["issue_type"]
        if issue_type == "wide_node":
            return None
        elif issue_type in {"duplicate_name", "deep_level"}:
            suggestion = _suggestion_from_issue(
                version_id,
                issue,
                action_type="mark_as_valid",
                suggestion="将该问题标记为当前分类体系中的有效结构。",
                risk_level="low",
                action_payload={"mark_reason": issue.get("description", "")},
            )
        elif issue_type == "missing_parent":
            return None
        else:
            return None
        validation = validate_suggestion_action(suggestion, self.settings)
        if not validation.valid:
            logger.warning("suggestion validation failed: %s", validation.reason)
            return None
        suggestion_id = self.suggestion_repo.create_suggestion(
            workflow_id=self.workflow_id,
            analysis_run_id=self.analysis_run_id,
            suggestion=suggestion,
        )
        return SuggestionRecord(
            id=suggestion_id,
            **suggestion.model_dump(),
        )

    def _submit_suggestion_tool(self):
        agent = self

        @tool
        def submit_suggestion(suggestion: dict[str, Any] | str) -> str:
            """提交维护建议；suggestion 可为对象或 JSON 对象字符串，返回建议 ID。"""
            record = AdjustmentSuggestion.model_validate(
                coerce_json_object(suggestion, field_name="suggestion")
            )
            validation = validate_suggestion_action(record, agent.settings)
            if not validation.valid:
                return json.dumps({"valid": False, "reason": validation.reason}, ensure_ascii=False)
            suggestion_id = agent.suggestion_repo.create_suggestion(
                workflow_id=agent.workflow_id,
                analysis_run_id=agent.analysis_run_id,
                suggestion=record,
            )
            return json.dumps(
                {
                    "valid": True,
                    "suggestion_id": suggestion_id,
                },
                ensure_ascii=False,
            )

        return submit_suggestion

    def _record_tool_error(
        self,
        name: str,
        tool_call: dict[str, Any],
        messages: list[Any],
        reason: str,
    ) -> None:
        self._trace(f"Observation: tool error for {name}: {reason}")
        messages.append(
            ToolMessage(
                content=json.dumps({"valid": False, "reason": reason}, ensure_ascii=False),
                tool_call_id=str(tool_call.get("id") or name),
            )
        )

    def _create_llm(self) -> ChatOpenAI | None:
        if not self.settings.deepseek_api_key:
            return None
        return ChatOpenAI(
            model=self.settings.deepseek_model,
            base_url=self.settings.deepseek_base_url,
            api_key=self.settings.deepseek_api_key,
            temperature=0.1,
            request_timeout=60,
        )

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
    )


def _load_observation(observation: Any) -> dict[str, Any]:
    if isinstance(observation, dict):
        return observation
    if isinstance(observation, str):
        loaded = json.loads(observation)
        if isinstance(loaded, dict):
            return loaded
    raise ValueError("submit_suggestion observation must be a JSON object.")
