from typing import Any

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

from backend.app.config import Settings, get_settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.vectorstores.qdrant_store import QdrantStore


_runtime_settings: Settings = get_settings()
_runtime_qdrant_store: Any | None = None
_runtime_embeddings: Any | None = None
_runtime_workflow_id: str | None = None
_runtime_analysis_run_id: str | None = None


def configure_tree_tool_runtime(
    *,
    settings: Settings,
    qdrant_store: Any | None = None,
    embeddings: Any | None = None,
    workflow_id: str | None = None,
    analysis_run_id: str | None = None,
) -> None:
    global _runtime_settings, _runtime_qdrant_store, _runtime_embeddings
    global _runtime_workflow_id, _runtime_analysis_run_id
    _runtime_settings = settings
    _runtime_qdrant_store = qdrant_store
    _runtime_embeddings = embeddings
    _runtime_workflow_id = workflow_id
    _runtime_analysis_run_id = analysis_run_id


@tool
def get_node_detail(version_id: int, category_id: int) -> dict:
    """查询单个节点详情：名称、路径、同义词、层级、是否叶子"""
    node = TaxonomyRepository(_runtime_settings).get_node_detail(version_id, category_id)
    return node or {}


@tool
def get_node_path(version_id: int, category_id: int) -> str:
    """查询节点完整路径（path_names）"""
    return TaxonomyRepository(_runtime_settings).get_node_path(version_id, category_id)


@tool
def get_children(version_id: int, parent_id: int) -> list[dict]:
    """查询直接子节点列表"""
    return TaxonomyRepository(_runtime_settings).get_children(version_id, parent_id)


@tool
def search_similar_nodes(
    version_id: int,
    node_text: str,
    top_k: int = 10,
) -> list[dict]:
    """Qdrant 语义召回，返回相似节点列表"""
    store = _runtime_qdrant_store or _create_qdrant_store()
    if store is None:
        return []
    return store.search_similar(version_id, node_text, top_k)


@tool
def submit_diagnosis(issue: dict) -> str:
    """提交一条诊断结果，返回 issue_id"""
    version_id = int(issue["version_id"])
    record = DiagnosisIssueRecord(
        issue_type=issue["issue_type"],
        node_id=issue.get("node_id"),
        node_name=issue.get("node_name"),
        description=issue.get("description") or issue.get("reason") or "内容诊断问题",
        reason=issue.get("reason", ""),
        risk_level=issue.get("risk_level", "low"),
        confidence=_coerce_confidence(issue.get("confidence", 0.0)),
        status=issue.get("status", "pending"),
    )
    issue_id = DiagnosisRepository(_runtime_settings).create_issue(
        version_id=version_id,
        workflow_id=_runtime_workflow_id,
        analysis_run_id=_runtime_analysis_run_id,
        detector_version="content-v1",
        issue=record,
    )
    return f"issue_{issue_id}"


def _create_qdrant_store() -> QdrantStore | None:
    embeddings = _runtime_embeddings
    if embeddings is None:
        if not _runtime_settings.dashscope_api_key:
            return None
        embeddings = OpenAIEmbeddings(
            model=_runtime_settings.embedding_model,
            base_url=_runtime_settings.embedding_base_url,
            api_key=_runtime_settings.dashscope_api_key,
            check_embedding_ctx_length=False,
            tiktoken_enabled=False,
            chunk_size=10,
        )
    return QdrantStore(_runtime_settings, embeddings=embeddings)


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
