"""Instance-scoped LangChain tools for agent workers."""

import json
from dataclasses import dataclass
import threading
from typing import Any

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.tools.validation_tools import validate_suggestion_action
from backend.app.vectorstores.qdrant_store import QdrantStore
from backend.app.repositories.triage_repo import TriageRepository
from backend.app.services.tool_registry import ToolRegistry, ToolSpec


@dataclass(frozen=True)
class ToolScope:
    workflow_id: str
    version_id: int
    subject_id: int | None = None


@dataclass(frozen=True)
class AgentResourceLimits:
    qdrant: Any
    embedding: Any

    @classmethod
    def from_settings(cls, settings: Settings) -> "AgentResourceLimits":
        return cls(
            qdrant=threading.BoundedSemaphore(max(1, settings.agent_qdrant_max_concurrency)),
            embedding=threading.BoundedSemaphore(max(1, settings.agent_embedding_max_concurrency)),
        )


def _enforce_scope(scope: ToolScope | None, version_id: int) -> None:
    if scope is not None and version_id != scope.version_id:
        raise ValueError("Tool version_id is outside workflow scope")


class AgentToolFactory:
    def __init__(self, settings: Settings, *, qdrant_store: Any | None = None, embeddings: Any | None = None, resource_limits: AgentResourceLimits | None = None) -> None:
        self.settings = settings
        self.taxonomy = TaxonomyRepository(settings)
        self.diagnosis = DiagnosisRepository(settings)
        self.suggestions = SuggestionRepository(settings)
        self.store = qdrant_store
        self.embeddings = embeddings
        self.resource_limits = resource_limits or AgentResourceLimits.from_settings(settings)

    def content_diagnosis_tools(self, scope: ToolScope | None = None) -> list[Any]:
        taxonomy = self.taxonomy
        diagnosis = self.diagnosis
        store = self.store
        settings = self.settings
        registry = ToolRegistry(settings, scope.workflow_id if scope else "unscoped", scope.version_id if scope else 0, "content_diagnosis")
        registry.register(ToolSpec(name="get_node_detail", owner_agents={"content_diagnosis"}, read_only=True, side_effect=False, timeout_ms=3000, cost_level="low", cache_ttl_seconds=300, result_limit=1, scoped_arguments={"version_id"}), lambda version_id, category_id: taxonomy.get_node_detail(version_id, category_id) or {})
        registry.register(ToolSpec(name="get_node_path", owner_agents={"content_diagnosis"}, read_only=True, side_effect=False, timeout_ms=3000, cost_level="low", cache_ttl_seconds=300, result_limit=1, scoped_arguments={"version_id"}), lambda version_id, category_id: taxonomy.get_node_path(version_id, category_id))
        registry.register(ToolSpec(name="get_children", owner_agents={"content_diagnosis"}, read_only=True, side_effect=False, timeout_ms=3000, cost_level="low", cache_ttl_seconds=300, result_limit=100, scoped_arguments={"version_id"}), lambda version_id, parent_id: taxonomy.get_children(version_id, parent_id))

        @tool
        def get_node_detail(version_id: int, category_id: int) -> dict:
            """查询当前版本节点详情。"""
            _enforce_scope(scope, version_id)
            return registry.invoke("get_node_detail", {"version_id": version_id, "category_id": category_id}) if scope else (taxonomy.get_node_detail(version_id, category_id) or {})

        @tool
        def get_node_path(version_id: int, category_id: int) -> str:
            """查询当前版本节点路径。"""
            _enforce_scope(scope, version_id)
            return registry.invoke("get_node_path", {"version_id": version_id, "category_id": category_id}) if scope else taxonomy.get_node_path(version_id, category_id)

        @tool
        def get_children(version_id: int, parent_id: int) -> list[dict]:
            """查询当前版本直接子节点。"""
            _enforce_scope(scope, version_id)
            return registry.invoke("get_children", {"version_id": version_id, "parent_id": parent_id}) if scope else taxonomy.get_children(version_id, parent_id)[:100]

        @tool
        def search_similar_nodes(version_id: int, node_text: str, top_k: int = 10) -> list[dict]:
            """查询当前版本语义相似节点。"""
            _enforce_scope(scope, version_id)
            resolved_store = store or self._create_qdrant_store()
            if resolved_store is None:
                return []
            with self.resource_limits.qdrant:
                return resolved_store.search_similar(version_id, node_text, min(max(top_k, 1), 20))

        @tool
        def submit_diagnosis(issue: dict) -> str:
            """提交当前作用域的一条诊断结果。"""
            version_id = int(issue["version_id"])
            _enforce_scope(scope, version_id)
            confidence = _coerce_confidence(issue.get("confidence", 0.0))
            if confidence < 0.6 or issue.get("detector_disagreement") or issue.get("inconclusive"):
                triage_id = TriageRepository(settings).create(
                    workflow_id=scope.workflow_id if scope else "unscoped",
                    version_id=version_id,
                    issue={**issue, "confidence": confidence},
                )
                return f"triage_{triage_id}"
            record = DiagnosisIssueRecord(
                issue_type=issue["issue_type"], node_id=issue.get("node_id"),
                node_name=issue.get("node_name"),
                description=issue.get("description") or issue.get("reason") or "内容诊断问题",
                reason=issue.get("reason", ""), risk_level=issue.get("risk_level", "low"),
                confidence=confidence,
                status=issue.get("status", "pending"), path=issue.get("path"),
                evidence=issue.get("evidence") or issue.get("reason"), source="model_analysis",
            )
            return f"issue_{diagnosis.create_issue(version_id=version_id, issue=record)}"

        return [get_node_detail, get_node_path, get_children, search_similar_nodes, submit_diagnosis]

    def suggestion_tools(self, submit_tool: Any, scope: ToolScope | None = None) -> list[Any]:
        tools = self.content_diagnosis_tools(scope)[:4]
        settings = self.settings

        @tool
        def validate_action(action_json: str) -> dict:
            """预校验维护建议动作是否合法。"""
            try:
                payload = json.loads(action_json) if isinstance(action_json, str) else action_json
                suggestion = AdjustmentSuggestion.model_validate(payload)
                _enforce_scope(scope, suggestion.version_id)
            except Exception as exc:
                return {"valid": False, "reason": f"建议 JSON 结构非法：{exc}"}
            return validate_suggestion_action(suggestion, settings).model_dump()

        return [*tools, validate_action, submit_tool]

    def _create_qdrant_store(self) -> QdrantStore | None:
        embeddings = self.embeddings
        if embeddings is None:
            if not self.settings.dashscope_api_key:
                return None
            embeddings = OpenAIEmbeddings(
                model=self.settings.embedding_model, base_url=self.settings.embedding_base_url,
                api_key=self.settings.dashscope_api_key, check_embedding_ctx_length=False,
                tiktoken_enabled=False, chunk_size=10,
            )
        return QdrantStore(self.settings, embeddings=embeddings, embedding_semaphore=self.resource_limits.embedding)


def _coerce_confidence(value: Any) -> float:
    if isinstance(value, str):
        mapped = {"high": 0.9, "高": 0.9, "medium": 0.6, "中": 0.6, "low": 0.3, "低": 0.3}
        if value.strip().lower() in mapped:
            return mapped[value.strip().lower()]
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0
