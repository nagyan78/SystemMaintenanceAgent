"""Instance-scoped LangChain tools for agent workers."""

from dataclasses import dataclass
import json
import threading
from typing import Any

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

from backend.app.config import Settings
from backend.app.domain.issue_types import normalize_issue_type_code
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.tools.validation_tools import validate_suggestion_action
from backend.app.tools.payload_tools import coerce_json_object
from backend.app.vectorstores.qdrant_store import QdrantStore
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

        def persist_issue(issue: dict[str, Any] | str) -> str:
            issue = coerce_json_object(issue, field_name="issue")
            version_id = int(issue["version_id"])
            _enforce_scope(scope, version_id)
            confidence = _coerce_confidence(issue.get("confidence", 0.0))
            record = DiagnosisIssueRecord(
                issue_type=normalize_issue_type_code(issue.get("issue_type")), node_id=issue.get("node_id"),
                node_name=issue.get("node_name"),
                description=issue.get("description") or issue.get("reason") or "内容诊断问题",
                reason=issue.get("reason", ""), risk_level=issue.get("risk_level", "low"),
                confidence=confidence,
                status=issue.get("status", "pending"), path=issue.get("path"),
                evidence=issue.get("evidence") or issue.get("reason"), source="model_analysis",
            )
            return f"issue_{diagnosis.create_issue(version_id=version_id, issue=record)}"

        @tool
        def submit_diagnosis(issue: dict[str, Any] | str) -> str:
            """兼容提交当前作用域的一条问题诊断。"""
            return persist_issue(issue)

        @tool
        def submit_content_assessment(assessment: dict[str, Any] | str) -> str:
            """提交合理或存在问题的二分类结论。"""
            value = coerce_json_object(assessment, field_name="assessment")
            conclusion = str(value.get("conclusion") or "").strip()
            if conclusion not in {"reasonable", "problem"}:
                raise ValueError("conclusion must be reasonable or problem")
            version_id = scope.version_id if scope is not None else int(value["version_id"])
            _enforce_scope(scope, version_id)
            node_id = (
                int(scope.subject_id)
                if scope is not None and scope.subject_id is not None
                else int(value["node_id"])
            )
            scoped_node = (
                taxonomy.get_node_detail(version_id, node_id) or {}
                if scope is not None
                else {}
            )
            node_name = scoped_node.get("category_name") or value.get("node_name")
            issue_id = None
            if conclusion == "problem":
                issue = coerce_json_object(value.get("issue") or {}, field_name="assessment.issue")
                issue["version_id"] = version_id
                issue["node_id"] = node_id
                issue["node_name"] = node_name
                issue_id = persist_issue(issue)
            return json.dumps({
                "accepted": True,
                "conclusion": conclusion,
                "node_id": node_id,
                "node_name": node_name,
                "issue_id": issue_id,
            }, ensure_ascii=False)

        return [get_node_detail, get_node_path, get_children, search_similar_nodes, submit_diagnosis, submit_content_assessment]

    def suggestion_tools(self, submit_tool: Any, scope: ToolScope | None = None) -> list[Any]:
        tools = self.content_diagnosis_tools(scope)[:4]
        settings = self.settings

        @tool
        def validate_action(action_json: dict[str, Any] | str) -> dict:
            """预校验维护建议动作是否合法。"""
            try:
                payload = coerce_json_object(action_json, field_name="action_json")
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
