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
from backend.app.services.agent_memory_service import AgentMemoryService
from backend.app.services.remediation_planning_service import RemediationPlanningService
from backend.app.services.suggestion_consistency_service import SuggestionConsistencyService
from backend.app.tools.validation_tools import (
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
        completed_issue_ids: set[int] = set()
        if self.llm is not None and len(issues) > 1:
            batch_records = self._generate_llm_batch_suggestion_records(version_id, issues)
            records.extend(batch_records)
            completed_issue_ids = {item.issue_id for item in batch_records}
        for issue in issues:
            if int(issue["id"]) in completed_issue_ids:
                continue
            # AI-enhanced maintenance must reason about every detected issue.
            # Deterministic planning remains a fallback and a validation source,
            # never a reason to skip model analysis.
            record = self._generate_llm_suggestion_record(version_id, issue) if self.llm is not None else None
            if record is None and self.llm is None:
                record = self._rule_based_suggestion_record(version_id, issue)
            if record is None:
                continue
            records.append(record)
        return SuggestionGenerationResult(
            version_id=version_id,
            review_batch_id=self.review_batch_id,
            generated_count=len(records),
            suggestions=records,
        )

    def _generate_llm_batch_suggestion_records(
        self, version_id: int, issues: list[dict[str, Any]],
    ) -> list[SuggestionRecord]:
        planner = RemediationPlanningService(self.settings)
        items = []
        for issue in issues:
            baseline = planner.plan(version_id, issue)
            items.append({
                "issue": issue,
                "deterministic_baseline": baseline.model_dump(mode="json") if baseline else None,
            })
        prompt = {
            "version_id": version_id,
            "items": items,
            "instruction": (
                "逐条返回修改方案，输出 JSON 对象 {\"suggestions\": [...]}。每条必须对应输入 issue_id，"
                "包含 AdjustmentSuggestion 的全部字段；不得返回 review_only，不得要求人工核对。"
                "高风险删除、合并或移动也必须给出完整动作，但删除仅限无子节点且无外部引用的叶子节点。"
            ),
        }
        try:
            response = self.llm.invoke([
                SystemMessage(content=SUGGESTION_GENERATION_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(prompt, ensure_ascii=False)),
            ])
            payload = _extract_json_object(str(response.content))
        except Exception as exc:
            logger.warning("Batch suggestion generation failed; retrying individually: %s", exc)
            return []
        issue_ids = {int(item["id"]) for item in issues}
        records: list[SuggestionRecord] = []
        for raw in payload.get("suggestions", []):
            try:
                suggestion = AdjustmentSuggestion.model_validate(raw)
                if suggestion.risk_level in {"medium", "high"}:
                    suggestion = suggestion.model_copy(update={"need_confirm": True})
                if suggestion.issue_id not in issue_ids or suggestion.version_id != version_id or suggestion.action_type == "review_only":
                    continue
                record = self._persist_ai_suggestion(suggestion)
                if record is not None:
                    records.append(record)
            except Exception as exc:
                logger.warning("Invalid batch suggestion item: %s", exc)
        return records

    def _persist_ai_suggestion(self, suggestion: AdjustmentSuggestion) -> SuggestionRecord | None:
        checked = SuggestionConsistencyService(self.settings).check(suggestion, normalize_new=True)
        suggestion = checked.suggestion
        if suggestion.risk_level in {"medium", "high"}:
            suggestion = suggestion.model_copy(update={"need_confirm": True})
        validation = validate_suggestion_action(suggestion, self.settings)
        if not validation.valid:
            return None
        suggestion_id = self.suggestion_repo.create_suggestion(
            review_batch_id=self.review_batch_id,
            suggestion=suggestion,
            work_item_id=self.work_item_id,
            analysis_run_id=self.analysis_run_id,
            workflow_id=self.workflow_id,
        )
        self.suggestion_repo.update_consistency(
            suggestion_id,
            suggestion=suggestion,
            change_preview=checked.change_preview,
            status="invalid" if checked.downgraded else "valid",
            reason=checked.reason,
        )
        return SuggestionRecord(
            id=suggestion_id,
            review_batch_id=self.review_batch_id,
            change_preview=checked.change_preview,
            consistency_status="invalid" if checked.downgraded else "valid",
            consistency_reason=checked.reason,
            **suggestion.model_dump(),
        )

    def _generate_llm_suggestion_record(self, version_id: int, issue: dict[str, Any]) -> SuggestionRecord | None:
        llm_with_tools = self.llm.bind_tools(self.tools)
        memory_context = AgentMemoryService(self.settings).get_suggestion_context(
            version_id=version_id,
            issue_type=str(issue.get("issue_type") or "unknown"),
            target_node_id=issue.get("node_id"),
            limit=5,
        )
        messages: list[Any] = [
            SystemMessage(content=SUGGESTION_GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=_issue_prompt(version_id, issue) + "\n历史用户反馈（仅供参考，不得跳过本轮确定性校验和快照预演）：\n" + json.dumps(memory_context, ensure_ascii=False)),
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
                    if str(tool_call.get("name") or "") == "submit_suggestion" and submitted_records:
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
                for record in submitted_records:
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
        if self.event_sink:
            self.event_sink({"event_type": "agent_step", "tool_name": name, "status": "running", "summary": {"action": "tool_started"}})
        try:
            observation = tool_obj.invoke(args)
        except Exception as exc:
            self._record_tool_error(name, tool_call, messages, str(exc))
            return None
        self._trace(f"Observation: {observation}")
        if self.event_sink:
            self.event_sink({"event_type": "agent_tool_completed", "tool_name": name, "status": "completed", "summary": {"result_type": type(observation).__name__}})
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
        except Exception as exc:
            self._trace(f"Observation: submit_suggestion response could not be processed: {exc}")
            return None
        checked = SuggestionConsistencyService(self.settings).check(suggestion, normalize_new=True)
        suggestion = checked.suggestion
        if self.uses_internal_submit_tool:
            payload = _load_observation(observation)
            if not payload.get("valid") or not payload.get("suggestion_id"):
                return None
            suggestion_id = int(payload["suggestion_id"])
        else:
            suggestion_id = self.suggestion_repo.create_suggestion(
                review_batch_id=self.review_batch_id,
                suggestion=suggestion,
                work_item_id=self.work_item_id,
                analysis_run_id=self.analysis_run_id,
                workflow_id=self.workflow_id,
            )
            self.suggestion_repo.update_consistency(suggestion_id, suggestion=suggestion,
                change_preview=checked.change_preview, status="invalid" if checked.downgraded else "valid", reason=checked.reason)
        return SuggestionRecord(
            id=suggestion_id,
            review_batch_id=self.review_batch_id,
            change_preview=checked.change_preview,
            consistency_status="invalid" if checked.downgraded else "valid",
            consistency_reason=checked.reason,
            **suggestion.model_dump(),
        )

    def _rule_based_suggestion_record(self, version_id: int, issue: dict[str, Any]) -> SuggestionRecord | None:
        suggestion = RemediationPlanningService(self.settings).plan(version_id, issue)
        checked = SuggestionConsistencyService(self.settings).check(suggestion, normalize_new=True)
        suggestion = checked.suggestion
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
        self.suggestion_repo.update_consistency(suggestion_id, suggestion=suggestion,
            change_preview=checked.change_preview, status="invalid" if checked.downgraded else "valid", reason=checked.reason)
        return SuggestionRecord(
            id=suggestion_id,
            review_batch_id=self.review_batch_id,
            change_preview=checked.change_preview,
            consistency_status="invalid" if checked.downgraded else "valid",
            consistency_reason=checked.reason,
            **suggestion.model_dump(),
        )

    def _submit_suggestion_tool(self):
        agent = self

        @tool
        def submit_suggestion(suggestion: dict[str, Any] | str) -> str:
            """提交一条维护建议；suggestion 可为对象或 JSON 对象字符串。"""
            try:
                record = AdjustmentSuggestion.model_validate(
                    coerce_json_object(suggestion, field_name="suggestion")
                )
            except Exception as exc:
                return json.dumps({"valid": False, "reason": f"模型建议解析失败：{exc}"}, ensure_ascii=False)
            checked = SuggestionConsistencyService(agent.settings).check(record, normalize_new=True)
            record = checked.suggestion
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
            agent.suggestion_repo.update_consistency(suggestion_id, suggestion=record,
                change_preview=checked.change_preview, status="invalid" if checked.downgraded else "valid", reason=checked.reason)
            return json.dumps(
                {
                    "valid": True,
                    "suggestion_id": suggestion_id,
                    "review_batch_id": agent.review_batch_id,
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
        if self.event_sink:
            self.event_sink({
                "event_type": "agent_tool_completed",
                "tool_name": name,
                "status": "failed",
                "summary": {"reason": reason},
            })
        messages.append(
            ToolMessage(
                content=json.dumps({"valid": False, "reason": reason}, ensure_ascii=False),
                tool_call_id=str(tool_call.get("id") or name),
            )
        )

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


def _extract_json_object(content: str) -> dict[str, Any]:
    import re

    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        raise ValueError("model response did not contain a JSON object")
    loaded = json.loads(match.group(0))
    if not isinstance(loaded, dict):
        raise ValueError("model response must be a JSON object")
    return loaded
