from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from backend.app.config import Settings


class QdrantStore:
    def __init__(
        self,
        settings: Settings,
        *,
        embeddings: OpenAIEmbeddings | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        self.settings = settings
        self.collection_name = settings.qdrant_collection
        self.embeddings = embeddings or _create_embeddings(settings)
        self.client = client or QdrantClient(url=settings.qdrant_url)

    def create_collection(self, vector_size: int = 1536) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def index_nodes(self, points: list[dict[str, Any]]) -> int:
        if not points:
            return 0
        qdrant_points = [
            PointStruct(
                id=_qdrant_point_id(str(point["id"])),
                vector=point["vector"],
                payload={**point["payload"], "logical_point_id": point["id"]},
            )
            for point in points
        ]
        for chunk in _chunked(qdrant_points, 256):
            self.client.upsert(
                collection_name=self.collection_name,
                points=chunk,
            )
        return len(qdrant_points)

    def search_similar(
        self,
        version_id: int,
        node_text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        query_vector = self.embeddings.embed_query(node_text)
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="version_id",
                    match=MatchValue(value=version_id),
                )
            ]
        )
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            points = response.points
        except AttributeError:
            points = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        return [_point_to_result(point) for point in points]


def _create_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        api_key=settings.dashscope_api_key,
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
        chunk_size=10,
    )


def _point_to_result(point: Any) -> dict[str, Any]:
    payload = dict(getattr(point, "payload", None) or {})
    payload["score"] = float(getattr(point, "score", 0.0) or 0.0)
    payload["point_id"] = getattr(point, "id", None)
    return payload


def _qdrant_point_id(logical_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"taxonomy-node:{logical_id}"))


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
