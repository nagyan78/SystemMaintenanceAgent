import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from backend.app.agents.prompts import (
    CONTENT_DIAGNOSIS_FEW_SHOT,
    CONTENT_DIAGNOSIS_SYSTEM_PROMPT,
    DIAGNOSIS_PLANNING_PROMPT,
)
from backend.app.config import Settings, get_settings
from backend.app.services.model_service import ModelService
from backend.app.services.model_router import ModelBudgetExceededError
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.issue import ContentIssue, ContentSampleAssessment, DiagnosisPlan
from backend.app.services.tool_factory import AgentResourceLimits, AgentToolFactory
from backend.app.domain.issue_types import normalize_issue_type_code
from backend.app.tools.payload_tools import coerce_json_object
from backend.app.services.stratified_sampling_service import StratifiedSamplingService


logger = logging.getLogger(__name__)
CandidateSelector = Callable[[int, DiagnosisPlan], list[dict[str, Any]]]
CandidateProgressSink = Callable[[int, int], None]


class ModelConclusionError(RuntimeError):
    """The model exhausted its bounded turns without a valid binary conclusion."""


class DiagnosisPlanningAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or self._create_llm()

    def run(self, structure_stats: dict, tree_overview: dict) -> DiagnosisPlan:
        if self.llm is None:
            return _fallback_plan(tree_overview)
        response = self.llm.invoke(
            [
                SystemMessage(content=DIAGNOSIS_PLANNING_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "structure_stats": structure_stats,
                            "tree_overview": tree_overview,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        return DiagnosisPlan.model_validate(_extract_json(response.content))

    def _create_llm(self) -> Any:
        return ModelService(self.settings).get_chat_model(temperature=0.1)


class ContentDiagnosisAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm: Any | None = None,
        tools: list[Any] | None = None,
        candidate_selector: CandidateSelector | None = None,
        max_iter: int = 8,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        progress_sink: CandidateProgressSink | None = None,
        resource_limits: AgentResourceLimits | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or self._create_llm()
        self.tools = tools or AgentToolFactory(self.settings, resource_limits=resource_limits).content_diagnosis_tools()
        self.tool_map = {item.name: item for item in self.tools}
        self.candidate_selector = candidate_selector or self.select_candidates
        self.max_iter = max_iter
        self.trace_log: list[str] = []
        self.event_sink = event_sink
        self.progress_sink = progress_sink
        self.model_calls_used = 0
        self.tokens_used = 0
        self.last_assessments: list[ContentSampleAssessment] = []

    def run(self, version_id: int, plan: DiagnosisPlan) -> list[ContentIssue]:
        assessments = self.run_assessments(version_id, plan)
        return [item.issue for item in assessments if item.conclusion == "problem" and item.issue is not None]

    def run_assessments(self, version_id: int, plan: DiagnosisPlan) -> list[ContentSampleAssessment]:
        if self.llm is None:
            logger.warning("Content diagnosis skipped because DeepSeek API key is not configured.")
            self.last_assessments = []
            return []
        llm_with_tools = self.llm.bind_tools(self.tools)
        assessments: list[ContentSampleAssessment] = []
        candidates = list(self.candidate_selector(version_id, plan))
        deadline = time.monotonic() + max(1, self.settings.diagnosis_ai_wall_seconds)
        for index, candidate in enumerate(candidates, start=1):
            self._ensure_within_deadline(deadline)
            assessment = self._diagnose_candidate(llm_with_tools, version_id, candidate, plan, deadline)
            assessments.append(assessment)
            if self.progress_sink:
                self.progress_sink(index, len(candidates))
        self.last_assessments = assessments
        return assessments

    def select_candidates(self, version_id: int, plan: DiagnosisPlan) -> list[dict[str, Any]]:
        if plan.sample_strategy == "sampling":
            nodes = TaxonomyRepository(self.settings).list_nodes(version_id)
            return StratifiedSamplingService().select(
                nodes,
                sample_size=self.settings.diagnosis_sample_size,
                seed=self.settings.diagnosis_sample_seed,
            )
        limit = max(1, min(int(plan.estimated_candidates or 200), 1000))
        return TaxonomyRepository(self.settings).list_content_diagnosis_candidates(
            version_id,
            priority_subtrees=plan.priority_subtrees,
            priority_subtree_ids=plan.priority_subtree_ids,
            focus_issues=plan.focus_issues,
            sample_strategy=plan.sample_strategy,
            limit=limit,
        )

    def _diagnose_candidate(
        self,
        llm_with_tools: Any,
        version_id: int,
        candidate: dict[str, Any],
        plan: DiagnosisPlan,
        deadline: float,
    ) -> ContentSampleAssessment:
        messages = [
            SystemMessage(
                content=f"{CONTENT_DIAGNOSIS_SYSTEM_PROMPT}\n\n{CONTENT_DIAGNOSIS_FEW_SHOT}"
            ),
            HumanMessage(content=_candidate_prompt(version_id, candidate, plan)),
        ]
        submit_only_llm = None
        submit_tool = next(
            (item for item in self.tools if item.name == "submit_content_assessment"),
            None,
        )
        context_queried = False
        for _ in range(self.max_iter):
            self._ensure_within_deadline(deadline)
            active_llm = submit_only_llm if context_queried and submit_only_llm is not None else llm_with_tools
            response = active_llm.invoke(messages)
            self.model_calls_used += 1
            usage = getattr(response, "usage_metadata", None) or {}
            call_tokens = int(usage.get("total_tokens", 0) or 0)
            self.tokens_used += call_tokens
            if self.event_sink:
                self.event_sink({
                    "event_type": "model_call_completed", "status": "completed",
                    "token_usage": {"total_tokens": call_tokens},
                    "summary": {"model_calls": 1},
                })
            self._trace(f"Thought: {response.content}")
            tool_calls = getattr(response, "tool_calls", []) or []
            invalid_tool_calls = getattr(response, "invalid_tool_calls", []) or []
            if not tool_calls and not invalid_tool_calls:
                messages.append(response)
                messages.append(HumanMessage(content="请继续分析，并调用 submit_content_assessment 提交合理或不合理结论。"))
                continue
            messages.append(response)
            for invalid_tool_call in invalid_tool_calls:
                self._record_tool_error(
                    str(invalid_tool_call.get("name") or "unknown_tool"),
                    invalid_tool_call,
                    messages,
                    str(invalid_tool_call.get("error") or "工具参数不是合法 JSON，请使用 JSON 对象重试。"),
                )
            submitted_assessment: ContentSampleAssessment | None = None
            for tool_call in tool_calls:
                if str(tool_call.get("name") or "") not in {"submit_diagnosis", "submit_content_assessment"}:
                    context_queried = True
                if str(tool_call.get("name") or "") in {"submit_diagnosis", "submit_content_assessment"} and submitted_assessment is not None:
                    self._record_tool_error(
                        str(tool_call.get("name") or "submit_content_assessment"),
                        tool_call,
                        messages,
                        "同一轮只能提交一个样本结论。",
                    )
                    continue
                assessment = self._execute_tool_call(tool_call, messages, plan.focus_issues)
                if assessment and submitted_assessment is None:
                    submitted_assessment = assessment
            if submitted_assessment:
                return submitted_assessment
            if context_queried and submit_tool is not None and submit_only_llm is None:
                try:
                    submit_only_llm = self.llm.bind_tools(
                        [submit_tool], tool_choice="submit_content_assessment"
                    )
                except TypeError:
                    # Test doubles and some compatible providers do not expose tool_choice.
                    submit_only_llm = self.llm.bind_tools([submit_tool])
            messages.append(HumanMessage(
                content=(
                    "上下文查询阶段已经结束。请勿继续调用查询工具；"
                    "现在必须调用 submit_content_assessment 提交 reasonable 或 problem；"
                    "若为 problem，必须给出具体问题类型和完整 issue。"
                )
            ))
        logger.warning("Content diagnosis max_iter exhausted for candidate %s", candidate)
        raise ModelConclusionError(
            f"MODEL_NO_VALID_BINARY_CONCLUSION: node_id={int(candidate['category_id'])}"
        )

    @staticmethod
    def _ensure_within_deadline(deadline: float) -> None:
        if time.monotonic() >= deadline:
            raise ModelBudgetExceededError("MODEL_BUDGET_EXCEEDED: wall_time")

    def _execute_tool_call(
        self, tool_call: dict[str, Any], messages: list[Any], focus_issues: list[str] | None = None,
    ) -> ContentSampleAssessment | None:
        name = str(tool_call.get("name") or "")
        try:
            args = coerce_json_object(tool_call.get("args") or {}, field_name=f"{name} 参数")
            if name == "submit_diagnosis":
                args["issue"] = coerce_json_object(args.get("issue", {}), field_name="issue")
            elif name == "submit_content_assessment":
                args["assessment"] = coerce_json_object(args.get("assessment", {}), field_name="assessment")
            tool_obj = self.tool_map[name]
        except (KeyError, ValueError) as exc:
            self._record_tool_error(name, tool_call, messages, str(exc))
            return None
        self._trace(f"Action: {name} {json.dumps(args, ensure_ascii=False)}")
        if self.event_sink:
            self.event_sink({"event_type": "agent_step", "tool_name": name, "status": "running", "summary": {"action": "tool_started"}})
        if name == "submit_diagnosis" and focus_issues:
            submitted = normalize_issue_type_code((args.get("issue") or {}).get("issue_type"))
            allowed = {normalize_issue_type_code(value) for value in focus_issues}
            if submitted not in allowed:
                observation = {"accepted": False, "reason": "issue_type is outside DiagnosisPlan.focus_issues"}
                messages.append(ToolMessage(content=json.dumps(observation, ensure_ascii=False), tool_call_id=tool_call.get("id", name)))
                return None
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
        if name == "submit_diagnosis":
            try:
                issue = _issue_from_tool_args(args, str(observation))
                return ContentSampleAssessment(
                    conclusion="problem",
                    node_id=int(issue.node_id),
                    node_name=issue.node_name,
                    reason=issue.reason,
                    issue=issue,
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._trace(f"Observation: submit_diagnosis response could not be parsed: {exc}")
                return None
        if name == "submit_content_assessment":
            try:
                return _assessment_from_tool_args(args, observation)
            except (KeyError, TypeError, ValueError) as exc:
                self._trace(f"Observation: submit_content_assessment response could not be parsed: {exc}")
                return None
        return None

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
        logger.info("content_diagnosis_react %s", message)


def run_plan(
    *,
    settings: Settings,
    structure_stats: dict,
    tree_overview: dict,
) -> DiagnosisPlan:
    return DiagnosisPlanningAgent(settings).run(structure_stats, tree_overview)


def run_agent(
    *,
    settings: Settings,
    version_id: int,
    plan: DiagnosisPlan,
) -> list[ContentIssue]:
    return ContentDiagnosisAgent(settings).run(version_id, plan)


def _candidate_prompt(version_id: int, candidate: dict[str, Any], plan: DiagnosisPlan) -> str:
    return json.dumps(
        {
            "version_id": version_id,
            "candidate": candidate,
            "focus_issue_types": plan.focus_issues,
            "sample_strategy": plan.sample_strategy,
            "instruction": "请按 Thought-Action-Observation 循环诊断该节点。",
        },
        ensure_ascii=False,
    )


def _issue_from_tool_args(args: dict[str, Any], issue_id: str) -> ContentIssue:
    issue = args["issue"]
    return ContentIssue(
        issue_id=issue_id,
        issue_type=issue["issue_type"],
        node_id=issue.get("node_id"),
        node_name=issue.get("node_name"),
        description=issue.get("description") or issue.get("reason") or "内容诊断问题",
        reason=issue.get("reason", ""),
        risk_level=issue.get("risk_level", "low"),
        confidence=_coerce_confidence(issue.get("confidence", 0.0)),
        status=issue.get("status", "pending"),
        path=issue.get("path"),
        evidence=issue.get("evidence") or issue.get("reason"),
        source="model_analysis",
    )


def _assessment_from_tool_args(args: dict[str, Any], observation: Any) -> ContentSampleAssessment:
    value = args["assessment"]
    conclusion = str(value["conclusion"])
    parsed_observation = json.loads(str(observation)) if isinstance(observation, str) else (observation or {})
    issue = None
    if conclusion == "problem":
        issue_id = str(parsed_observation.get("issue_id") or "")
        issue = _issue_from_tool_args({"issue": value["issue"]}, issue_id)
        issue = issue.model_copy(update={
            "node_id": int(parsed_observation.get("node_id", issue.node_id)),
            "node_name": parsed_observation.get("node_name") or issue.node_name,
        })
    return ContentSampleAssessment(
        conclusion=conclusion,
        node_id=int(parsed_observation.get("node_id", value["node_id"])),
        node_name=parsed_observation.get("node_name") or value.get("node_name"),
        reason=str(value.get("reason") or "未提供判断摘要"),
        issue=issue,
    )


def _fallback_plan(tree_overview: dict) -> DiagnosisPlan:
    roots = tree_overview.get("root_categories") or []
    priority_subtrees = [
        item["category_name"] if isinstance(item, dict) else str(item)
        for item in roots[:5]
    ]
    return DiagnosisPlan(
        priority_subtrees=priority_subtrees,
        sample_strategy="sampling",
        focus_issues=["synonym_pollution", "semantic_duplicate"],
        estimated_candidates=200,
    )


def _coerce_confidence(value: Any) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"high", "高"}:
            return 0.9
        if normalized in {"medium", "中"}:
            return 0.6
        if normalized in {"low", "低"}:
            return 0.3
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _extract_json(content: str) -> dict:
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        raise ValueError("LLM planning output did not contain JSON.")
    return json.loads(match.group(0))
