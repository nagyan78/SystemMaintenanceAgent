import json
import logging
import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from backend.app.agents.prompts import (
    CONTENT_DIAGNOSIS_FEW_SHOT,
    CONTENT_DIAGNOSIS_SYSTEM_PROMPT,
    DIAGNOSIS_PLANNING_PROMPT,
)
from backend.app.config import Settings, get_settings
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.issue import ContentIssue, DiagnosisPlan
from backend.app.tools.tree_tools import (
    configure_tree_tool_runtime,
    get_children,
    get_node_detail,
    get_node_path,
    search_similar_nodes,
    submit_diagnosis,
)


logger = logging.getLogger(__name__)
CandidateSelector = Callable[[int, DiagnosisPlan], list[dict[str, Any]]]


class DiagnosisPlanningAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        configure_tree_tool_runtime(settings=self.settings)
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

    def _create_llm(self) -> ChatOpenAI | None:
        if not self.settings.deepseek_api_key:
            return None
        return ChatOpenAI(
            model=self.settings.deepseek_model,
            base_url=self.settings.deepseek_base_url,
            api_key=self.settings.deepseek_api_key,
            temperature=0.1,
        )


class ContentDiagnosisAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm: Any | None = None,
        tools: list[Any] | None = None,
        candidate_selector: CandidateSelector | None = None,
        max_iter: int = 8,
    ) -> None:
        self.settings = settings or get_settings()
        configure_tree_tool_runtime(settings=self.settings)
        self.llm = llm or self._create_llm()
        self.tools = tools or [
            search_similar_nodes,
            get_node_detail,
            get_node_path,
            get_children,
            submit_diagnosis,
        ]
        self.tool_map = {item.name: item for item in self.tools}
        self.candidate_selector = candidate_selector or self.select_candidates
        self.max_iter = max_iter
        self.trace_log: list[str] = []

    def run(self, version_id: int, plan: DiagnosisPlan) -> list[ContentIssue]:
        if self.llm is None:
            logger.warning("Content diagnosis skipped because DeepSeek API key is not configured.")
            return []
        llm_with_tools = self.llm.bind_tools(self.tools)
        issues: list[ContentIssue] = []
        for candidate in self.candidate_selector(version_id, plan):
            issue = self._diagnose_candidate(llm_with_tools, version_id, candidate)
            if issue:
                issues.append(issue)
        return issues

    def select_candidates(self, version_id: int, plan: DiagnosisPlan) -> list[dict[str, Any]]:
        limit = max(1, min(int(plan.estimated_candidates or 200), 1000))
        return TaxonomyRepository(self.settings).list_content_diagnosis_candidates(
            version_id,
            priority_subtrees=plan.priority_subtrees,
            limit=limit,
        )

    def _diagnose_candidate(
        self,
        llm_with_tools: Any,
        version_id: int,
        candidate: dict[str, Any],
    ) -> ContentIssue | None:
        messages = [
            SystemMessage(
                content=f"{CONTENT_DIAGNOSIS_SYSTEM_PROMPT}\n\n{CONTENT_DIAGNOSIS_FEW_SHOT}"
            ),
            HumanMessage(content=_candidate_prompt(version_id, candidate)),
        ]
        for _ in range(self.max_iter):
            response = llm_with_tools.invoke(messages)
            self._trace(f"Thought: {response.content}")
            tool_calls = getattr(response, "tool_calls", []) or []
            if not tool_calls:
                messages.append(response)
                messages.append(HumanMessage(content="请继续分析，或调用 submit_diagnosis 提交问题。"))
                continue
            messages.append(response)
            for tool_call in tool_calls:
                issue = self._execute_tool_call(tool_call, messages)
                if issue:
                    return issue
        logger.warning("Content diagnosis max_iter exhausted for candidate %s", candidate)
        return None

    def _execute_tool_call(self, tool_call: dict[str, Any], messages: list[Any]) -> ContentIssue | None:
        name = tool_call["name"]
        args = tool_call.get("args") or {}
        tool_obj = self.tool_map[name]
        self._trace(f"Action: {name} {json.dumps(args, ensure_ascii=False)}")
        observation = tool_obj.invoke(args)
        self._trace(f"Observation: {observation}")
        messages.append(
            ToolMessage(
                content=json.dumps(observation, ensure_ascii=False),
                tool_call_id=tool_call.get("id", name),
            )
        )
        if name == "submit_diagnosis":
            return _issue_from_tool_args(args, str(observation))
        return None

    def _create_llm(self) -> ChatOpenAI | None:
        if not self.settings.deepseek_api_key:
            return None
        return ChatOpenAI(
            model=self.settings.deepseek_model,
            base_url=self.settings.deepseek_base_url,
            api_key=self.settings.deepseek_api_key,
            temperature=0.1,
        )

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
    configure_tree_tool_runtime(settings=settings)
    return ContentDiagnosisAgent(settings).run(version_id, plan)


def _candidate_prompt(version_id: int, candidate: dict[str, Any]) -> str:
    return json.dumps(
        {
            "version_id": version_id,
            "candidate": candidate,
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
    )


def _fallback_plan(tree_overview: dict) -> DiagnosisPlan:
    roots = tree_overview.get("root_categories") or []
    priority_subtrees = [
        item["category_name"] if isinstance(item, dict) else str(item)
        for item in roots[:5]
    ]
    return DiagnosisPlan(
        priority_subtrees=priority_subtrees,
        sample_strategy="focused",
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
