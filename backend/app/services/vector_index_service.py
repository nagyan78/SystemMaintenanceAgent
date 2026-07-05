from typing import Any
from concurrent.futures import ThreadPoolExecutor

from langchain_openai import OpenAIEmbeddings

from backend.app.config import Settings, get_settings
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import IndexResult
from backend.app.vectorstores.qdrant_store import QdrantStore


class VectorIndexService:
    def __init__(
        self,
        settings: Settings,
        *,
        embeddings: Any | None = None,
        store: Any | None = None,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.store = store

    def index_version(self, version_id: int) -> IndexResult:
        if VersionRepository(self.settings).get_version(version_id) is None:
            raise ValueError(f"Taxonomy version {version_id} was not found.")
        embeddings = self.embeddings or self._create_embeddings()
        if embeddings is None:
            return IndexResult(version_id=version_id, status="skipped", indexed_count=0)
        store = self.store or QdrantStore(self.settings, embeddings=embeddings)
        nodes = TaxonomyRepository(self.settings).list_nodes(version_id)
        texts = [_node_text(node) for node in nodes]
        vectors = self._embed_documents(embeddings, texts)
        vector_size = len(vectors[0]) if vectors else 1536
        store.create_collection(vector_size=vector_size)
        indexed_count = store.index_nodes(
            [
                {
                    "id": f"{version_id}_{node['category_id']}",
                    "vector": vector,
                    "payload": {
                        "version_id": version_id,
                        "category_id": int(node["category_id"]),
                        "category_name": node["category_name"],
                        "parent_id": node["parent_id"],
                        "level": node["level"],
                        "path_names": node["path_names"],
                        "syn_list": node["syn_list"],
                        "is_leaf": node["is_leaf"],
                        "node_text": text,
                    },
                }
                for node, text, vector in zip(nodes, texts, vectors, strict=True)
            ]
        )
        return IndexResult(
            version_id=version_id,
            status="completed",
            indexed_count=indexed_count,
        )

    def _create_embeddings(self) -> OpenAIEmbeddings | None:
        if not self.settings.dashscope_api_key:
            return None
        return OpenAIEmbeddings(
            model=self.settings.embedding_model,
            base_url=self.settings.embedding_base_url,
            api_key=self.settings.dashscope_api_key,
            check_embedding_ctx_length=False,
            tiktoken_enabled=False,
            chunk_size=self.settings.embedding_batch_size,
        )

    def _embed_documents(self, embeddings: Any, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        chunks = list(_chunked(texts, self.settings.embedding_batch_size))
        if self.settings.embedding_max_workers <= 1 or len(chunks) == 1:
            return [
                vector
                for chunk in chunks
                for vector in embeddings.embed_documents(chunk)
            ]
        with ThreadPoolExecutor(max_workers=self.settings.embedding_max_workers) as executor:
            return [
                vector
                for chunk_vectors in executor.map(embeddings.embed_documents, chunks)
                for vector in chunk_vectors
            ]


def index_version(version_id: int) -> IndexResult:
    return VectorIndexService(get_settings()).index_version(version_id)


def _node_text(node: dict[str, Any]) -> str:
    parts = [
        f"名称：{node['category_name']}",
        f"路径：{node.get('path_names') or ''}",
    ]
    if node.get("syn_list"):
        parts.append(f"同义词：{node['syn_list']}")
    return "\n".join(parts)


def _chunked(items: list[str], size: int) -> list[list[str]]:
    chunk_size = max(1, size)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]
