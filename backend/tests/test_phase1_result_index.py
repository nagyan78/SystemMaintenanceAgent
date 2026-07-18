from typing import Any

from backend.app.agents.graph import build_taxonomy_graph
from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.vector_index_service import VectorIndexService


def _settings(tmp_path, *, key: str = "") -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        dashscope_api_key=key,
    )


def _version(settings: Settings) -> int:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="根",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="根",
                is_leaf=1,
            )
        ],
    )
    return version_id


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class FakeStore:
    def __init__(self, *, indexed: bool = False, fail: bool = False) -> None:
        self.indexed = indexed
        self.fail = fail

    def version_indexed(self, version_id: int) -> bool:  # noqa: ARG002
        return self.indexed

    def create_collection(self, vector_size: int) -> None:  # noqa: ARG002
        if self.fail:
            raise RuntimeError("qdrant unavailable")

    def index_nodes(self, points: list[dict[str, Any]]) -> int:
        return len(points)


def test_index_success_marks_version_ready_and_increments_generation(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id = _version(settings)

    result = VectorIndexService(
        settings,
        embeddings=FakeEmbeddings(),
        store=FakeStore(),
    ).index_version(version_id)

    version = VersionRepository(settings).get_version(version_id)
    assert result.status == "ready"
    assert result.indexed_count == 1
    assert version["vector_index_status"] == "ready"
    assert version["vector_index_generation"] == 1


def test_missing_embeddings_marks_skipped_without_fake_count(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id = _version(settings)

    result = VectorIndexService(settings).index_version(version_id)

    assert result.status == "skipped"
    assert result.indexed_count == 0
    assert VersionRepository(settings).get_version(version_id)[
        "vector_index_status"
    ] == "skipped"


def test_qdrant_failure_is_persisted_without_deleting_version(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id = _version(settings)

    result = VectorIndexService(
        settings,
        embeddings=FakeEmbeddings(),
        store=FakeStore(fail=True),
    ).index_version(version_id)

    assert result.status == "failed"
    assert "qdrant unavailable" in result.error_message
    assert VersionRepository(settings).get_version(version_id) is not None
    assert VersionRepository(settings).get_version(version_id)[
        "vector_index_status"
    ] == "failed"


def test_saved_version_uses_post_change_index_path() -> None:
    edges = {
        (edge.source, edge.target)
        for edge in build_taxonomy_graph().get_graph().edges
    }

    assert ("save_new_version_node", "index_result_version_node") in edges
    assert ("index_result_version_node", "result_quality_evaluation_node") in edges
