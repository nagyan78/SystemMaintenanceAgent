import json

from langchain_core.messages import AIMessage

from backend.app.agents.content_diagnosis_subgraph import build_content_diagnosis_subgraph
from backend.app.agents.suggestion_subgraph import build_suggestion_subgraph
from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        export_dir=tmp_path / "exports",
        report_dir=tmp_path / "reports",
        dashscope_api_key="",
    )


def _seed(tmp_path, count=5):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    nodes = [
        TaxonomyNodeRecord(
            category_id=index,
            category_name=f"节点{index}",
            parent_id=None,
            level=1,
            path_ids=str(index),
            path_names=f"节点{index}",
            syn_list=f"同义词{index}",
            is_leaf=1,
        )
        for index in range(1, count + 1)
    ]
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)
    return settings, version_id


class BatchLLM:
    def __init__(self, *, invalid=False):
        self.invalid = invalid
        self.batch_sizes = []

    def invoke(self, messages):
        candidates = json.loads(messages[1].content)["candidates"]
        self.batch_sizes.append(len(candidates))
        if self.invalid:
            return AIMessage(content="invalid")
        assessments = [
            {
                "node_id": item["node_id"],
                "conclusion": "problem",
                "issue_type": "synonym_pollution",
                "reason": "测试证据",
                "evidence": item["path"],
                "risk_level": "medium",
                "confidence": 0.9,
            }
            for item in candidates
        ]
        return AIMessage(content=json.dumps({"assessments": assessments}, ensure_ascii=False))


def test_content_subgraph_batches_fifty_candidates_into_five_calls(tmp_path):
    settings, version_id = _seed(tmp_path, 50)
    llm = BatchLLM()

    result = build_content_diagnosis_subgraph(settings=settings, llm=llm).invoke(
        {"workflow_id": "wf", "version_id": version_id, "plan": {"estimated_candidates": 50}}
    )

    counts = AgentRunRepository(settings).counts(result["run_id"])
    assert counts["succeeded"] == 50
    assert llm.batch_sizes == [10, 10, 10, 10, 10]
    assert result["coverage"]["model_calls"] == 5
    assert result["coverage"]["completion_status"] == "completed"


def test_invalid_batches_retry_once_and_finish_partial(tmp_path):
    settings, version_id = _seed(tmp_path, 10)
    llm = BatchLLM(invalid=True)

    result = build_content_diagnosis_subgraph(settings=settings, llm=llm).invoke(
        {"workflow_id": "wf-partial", "version_id": version_id, "plan": {"estimated_candidates": 10}}
    )

    counts = AgentRunRepository(settings).counts(result["run_id"])
    assert counts["inconclusive"] == 10
    assert llm.batch_sizes == [10, 10]
    assert result["coverage"]["model_calls"] == 2
    assert result["coverage"]["completion_status"] == "partial"
    assert result["coverage"]["unexamined_reasons"] == {"AI_UNCERTAIN": 10}


def test_suggestion_subgraph_does_not_duplicate_saved_suggestions(tmp_path):
    settings, version_id = _seed(tmp_path, 3)
    diagnosis = DiagnosisRepository(settings)
    for node_id in range(1, 4):
        diagnosis.create_issue(
            version_id=version_id,
            issue=DiagnosisIssueRecord(
                issue_type="wide_node",
                node_id=node_id,
                node_name=f"节点{node_id}",
                description=f"节点{node_id}过宽",
                reason="测试",
                risk_level="medium",
                confidence=1.0,
            ),
        )
    graph = build_suggestion_subgraph(settings=settings)
    first = graph.invoke({"workflow_id": "wf-suggestions", "version_id": version_id})
    graph.invoke(first)
    suggestions = SuggestionRepository(settings).list_suggestions(version_id=version_id)
    assert len(suggestions) == 3
    assert len({item.work_item_id for item in suggestions}) == 1
