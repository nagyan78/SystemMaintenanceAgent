from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _insert_version(settings: Settings, nodes: list[TaxonomyNodeRecord]) -> int:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(
        file_id=1,
        version_no="v1.0",
        description="test",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)
    return version_id


def _sample_nodes() -> list[TaxonomyNodeRecord]:
    return [
        TaxonomyNodeRecord(
            category_id=10,
            category_name="水果",
            parent_id=None,
            level=1,
            path_ids="10",
            path_names="水果",
            syn_list=None,
            is_leaf=0,
        ),
        TaxonomyNodeRecord(
            category_id=11,
            category_name="苹果",
            parent_id=10,
            level=2,
            path_ids="10,11",
            path_names="水果 > 苹果",
            syn_list="AirPods, iPhone, Apple Pencil, Apple Music",
            is_leaf=1,
        ),
    ]


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), 0.1, 0.2] for index, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [0.5, 0.1, 0.2]


class FakeVectorStore:
    def __init__(self) -> None:
        self.created = False
        self.vector_size = 0
        self.indexed_points: list[dict[str, Any]] = []

    def create_collection(self, vector_size: int = 1536) -> None:
        self.created = True
        self.vector_size = vector_size

    def index_nodes(self, points: list[dict[str, Any]]) -> int:
        self.indexed_points.extend(points)
        return len(points)


def test_settings_reads_deepseek_and_dashscope_keys_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://example.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")

    settings = Settings()

    assert settings.deepseek_api_key == "deepseek-key"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.dashscope_api_key == "dashscope-key"
    assert settings.embedding_base_url == "https://example.aliyuncs.com/compatible-mode/v1"
    assert settings.embedding_model == "text-embedding-v4"


def test_vector_index_service_indexes_nodes_with_version_category_point_ids(tmp_path):
    from backend.app.services.vector_index_service import VectorIndexService

    settings = _settings(tmp_path)
    version_id = _insert_version(settings, _sample_nodes())
    store = FakeVectorStore()

    result = VectorIndexService(
        settings,
        embeddings=FakeEmbeddings(),
        store=store,
    ).index_version(version_id)

    assert result.indexed_count == 2
    assert store.created is True
    assert store.vector_size == 3
    assert store.indexed_points[1]["id"] == f"{version_id}_11"
    assert store.indexed_points[1]["payload"]["category_name"] == "苹果"
    assert "AirPods" in store.indexed_points[1]["payload"]["node_text"]


def test_qdrant_store_accepts_logical_version_category_point_ids(tmp_path):
    from qdrant_client import QdrantClient

    from backend.app.vectorstores.qdrant_store import QdrantStore

    settings = _settings(tmp_path)
    store = QdrantStore(
        settings,
        embeddings=FakeEmbeddings(),
        client=QdrantClient(location=":memory:"),
    )

    store.create_collection(vector_size=3)
    indexed_count = store.index_nodes(
        [
            {
                "id": "1_11",
                "vector": [0.5, 0.1, 0.2],
                "payload": {
                    "version_id": 1,
                    "category_id": 11,
                    "category_name": "苹果",
                    "path_names": "水果 > 苹果",
                },
            }
        ]
    )
    results = store.search_similar(1, "苹果", top_k=1)

    assert indexed_count == 1
    assert results[0]["logical_point_id"] == "1_11"


def test_taxonomy_repository_returns_node_detail_path_children_and_candidates(tmp_path):
    settings = _settings(tmp_path)
    version_id = _insert_version(settings, _sample_nodes())
    repo = TaxonomyRepository(settings)

    detail = repo.get_node_detail(version_id, 11)
    children = repo.get_children(version_id, 10)
    candidates = repo.list_content_diagnosis_candidates(version_id, limit=10)

    assert detail["path_names"] == "水果 > 苹果"
    assert detail["is_leaf"] == 1
    assert repo.get_node_path(version_id, 11) == "水果 > 苹果"
    assert children == [
        {
            "category_id": 11,
            "category_name": "苹果",
            "path_names": "水果 > 苹果",
            "syn_list": "AirPods, iPhone, Apple Pencil, Apple Music",
            "level": 2,
            "is_leaf": 1,
        }
    ]
    assert candidates[0]["category_id"] == 11


def test_tree_tools_use_repository_and_vector_store_runtime(tmp_path):
    from backend.app.tools.tree_tools import configure_tree_tool_runtime, get_node_detail

    settings = _settings(tmp_path)
    version_id = _insert_version(settings, _sample_nodes())
    configure_tree_tool_runtime(settings=settings, qdrant_store=None, embeddings=None)

    detail = get_node_detail.invoke({"version_id": version_id, "category_id": 11})

    assert detail["category_name"] == "苹果"
    assert detail["path_names"] == "水果 > 苹果"


class FakePlannerLLM:
    def invoke(self, messages):
        return AIMessage(
            content=(
                '{"priority_subtrees":["食品"],"sample_strategy":"focused",'
                '"focus_issues":["synonym_pollution"],"estimated_candidates":50}'
            )
        )


def test_diagnosis_planning_agent_parses_structured_plan():
    from backend.app.services.content_diagnosis_service import DiagnosisPlanningAgent

    plan = DiagnosisPlanningAgent(llm=FakePlannerLLM()).run(
        structure_stats={"missing_parent": 44},
        tree_overview={"root_categories": ["食品"]},
    )

    assert plan.priority_subtrees == ["食品"]
    assert plan.sample_strategy == "focused"
    assert plan.focus_issues == ["synonym_pollution"]
    assert plan.estimated_candidates == 50


class FakeToolCallingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="Thought: 先召回相似节点。",
                tool_calls=[
                    {
                        "id": "call_search",
                        "name": "search_similar_nodes",
                        "args": {"version_id": 1, "node_text": "苹果 AirPods iPhone"},
                    }
                ],
            )
        if self.calls == 2:
            return AIMessage(
                content="Thought: 需要确认节点路径。",
                tool_calls=[
                    {
                        "id": "call_path",
                        "name": "get_node_path",
                        "args": {"version_id": 1, "category_id": 11},
                    }
                ],
            )
        return AIMessage(
            content="Thought: 同义词明显污染，提交诊断。",
            tool_calls=[
                {
                    "id": "call_submit",
                    "name": "submit_diagnosis",
                    "args": {
                        "issue": {
                            "version_id": 1,
                            "node_id": 11,
                            "node_name": "苹果",
                            "issue_type": "synonym_pollution",
                            "description": "水果节点同义词包含电子产品词",
                            "reason": "AirPods/iPhone 与水果分类语义不一致",
                            "risk_level": "medium",
                            "confidence": 0.92,
                        }
                    },
                }
            ],
        )


def test_content_diagnosis_agent_runs_react_tool_loop_and_returns_submitted_issue():
    from backend.app.schemas.issue import DiagnosisPlan
    from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent

    submitted: list[dict[str, Any]] = []

    @tool
    def search_similar_nodes(version_id: int, node_text: str, top_k: int = 10) -> list[dict]:
        """Qdrant semantic search."""
        return [{"category_id": 91, "category_name": "手机", "score": 0.91}]

    @tool
    def get_node_path(version_id: int, category_id: int) -> str:
        """Return node path."""
        return "水果 > 苹果"

    @tool
    def submit_diagnosis(issue: dict) -> str:
        """Submit issue."""
        submitted.append(issue)
        return "issue_1"

    agent = ContentDiagnosisAgent(
        llm=FakeToolCallingLLM(),
        tools=[search_similar_nodes, get_node_path, submit_diagnosis],
        candidate_selector=lambda version_id, plan: [
            {
                "category_id": 11,
                "category_name": "苹果",
                "path_names": "水果 > 苹果",
                "syn_list": "AirPods, iPhone, Apple Pencil, Apple Music",
            }
        ],
    )

    issues = agent.run(version_id=1, plan=DiagnosisPlan())

    assert len(issues) == 1
    assert submitted[0]["issue_type"] == "synonym_pollution"
    assert any("Action: search_similar_nodes" in item for item in agent.trace_log)
    assert any("Observation:" in item for item in agent.trace_log)


def test_graph_topology_runs_planning_between_structure_and_content(tmp_path):
    from backend.app.agents.graph import build_taxonomy_graph

    graph = build_taxonomy_graph(settings=_settings(tmp_path))
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("structure_diagnosis_node", "diagnosis_planning_node") in edges
    assert ("diagnosis_planning_node", "content_diagnosis_node") in edges
