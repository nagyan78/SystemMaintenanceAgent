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
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.schemas.issue import DiagnosisIssueRecord


def _settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads", export_dir=tmp_path / "exports", report_dir=tmp_path / "reports", dashscope_api_key="", agent_work_item_max_attempts=3)


def _seed(tmp_path, count=5):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    nodes = [TaxonomyNodeRecord(category_id=index, category_name=f"节点{index}", parent_id=None, level=1, path_ids=str(index), path_names=f"节点{index}", syn_list=f"同义词{index}", is_leaf=1) for index in range(1, count + 1)]
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)
    return settings, version_id


class FailOnceForCandidate:
    def __init__(self, candidate_id: int):
        self.candidate_id = candidate_id
        self.calls_by_candidate = {}

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        candidate = json.loads(messages[1].content)["candidate"]
        candidate_id = int(candidate["category_id"])
        self.calls_by_candidate[candidate_id] = self.calls_by_candidate.get(candidate_id, 0) + 1
        if candidate_id == self.candidate_id and self.calls_by_candidate[candidate_id] == 1:
            raise TimeoutError("simulated timeout")
        return AIMessage(content="submit", tool_calls=[{"id": f"submit-{candidate_id}", "name": "submit_diagnosis", "args": {"issue": {"version_id": 1, "node_id": candidate_id, "node_name": candidate["category_name"], "issue_type": "synonym_pollution", "description": "测试问题", "reason": "测试证据", "risk_level": "medium", "confidence": 0.9}}}])


def test_content_subgraph_retries_only_unfinished_candidates(tmp_path):
    settings, version_id = _seed(tmp_path, 5)
    llm = FailOnceForCandidate(4)
    graph = build_content_diagnosis_subgraph(settings=settings, llm=llm)
    first = graph.invoke({"workflow_id": "wf", "version_id": version_id, "plan": {"estimated_candidates": 5}}, config={"max_concurrency": 1})
    counts = AgentRunRepository(settings).counts(first["run_id"])
    assert counts["succeeded"] == 4
    assert counts["retryable_failed"] == 1
    second = graph.invoke(first, config={"max_concurrency": 1})
    counts = AgentRunRepository(settings).counts(second["run_id"])
    assert counts["succeeded"] == 5
    assert llm.calls_by_candidate[1] == 1
    assert llm.calls_by_candidate[4] == 2


class AlwaysTimeoutLLM:
    def __init__(self): self.calls = 0
    def bind_tools(self, tools): return self
    def invoke(self, messages):
        self.calls += 1
        raise TimeoutError("permanent timeout")


def test_retryable_error_becomes_permanent_after_max_attempts(tmp_path):
    settings, version_id = _seed(tmp_path, 1)
    llm = AlwaysTimeoutLLM()
    graph = build_content_diagnosis_subgraph(settings=settings, llm=llm)
    state = {"workflow_id": "wf", "version_id": version_id, "plan": {"estimated_candidates": 1}}
    for _ in range(3):
        state = graph.invoke(state, config={"max_concurrency": 1})
    item = AgentRunRepository(settings).list_work_items(state["run_id"])[0]
    assert item.attempt == 3
    assert item.status == "permanent_failed"
    before = llm.calls
    graph.invoke(state, config={"max_concurrency": 1})
    assert llm.calls == before


def test_suggestion_subgraph_does_not_duplicate_saved_suggestions(tmp_path):
    settings, version_id = _seed(tmp_path, 3)
    diagnosis = DiagnosisRepository(settings)
    for node_id in range(1, 4):
        diagnosis.create_issue(version_id=version_id, issue=DiagnosisIssueRecord(
            issue_type="wide_node", node_id=node_id, node_name=f"节点{node_id}",
            description=f"节点{node_id}过宽", reason="测试", risk_level="medium", confidence=1.0,
        ))
    graph = build_suggestion_subgraph(settings=settings)
    first = graph.invoke({"workflow_id": "wf-suggestions", "version_id": version_id}, config={"max_concurrency": 1})
    graph.invoke(first, config={"max_concurrency": 1})
    suggestions = SuggestionRepository(settings).list_suggestions(version_id=version_id)
    assert len(suggestions) == 3
    assert len({item.work_item_id for item in suggestions}) == 3


def test_candidate_48_failure_preserves_other_49_and_retries_only_it(tmp_path):
    settings, version_id = _seed(tmp_path, 50)
    llm = FailOnceForCandidate(48)
    graph = build_content_diagnosis_subgraph(settings=settings, llm=llm)
    first = graph.invoke({"workflow_id":"wf-50", "version_id":version_id, "plan":{"estimated_candidates":50}}, config={"max_concurrency":4})
    counts = AgentRunRepository(settings).counts(first["run_id"])
    assert counts["succeeded"] == 49
    assert counts["retryable_failed"] == 1
    graph.invoke(first, config={"max_concurrency":4})
    assert AgentRunRepository(settings).counts(first["run_id"])["succeeded"] == 50
    assert llm.calls_by_candidate[47] == 1
    assert llm.calls_by_candidate[48] == 2
    assert llm.calls_by_candidate[49] == 1


class AlwaysFailCandidate(FailOnceForCandidate):
    def invoke(self, messages):
        candidate = json.loads(messages[1].content)["candidate"]
        candidate_id = int(candidate["category_id"])
        self.calls_by_candidate[candidate_id] = self.calls_by_candidate.get(candidate_id, 0) + 1
        if candidate_id == self.candidate_id:
            raise TimeoutError("always timeout")
        return super().invoke(messages)


def test_candidate_48_stops_after_max_attempts(tmp_path):
    settings, version_id = _seed(tmp_path, 50)
    llm = AlwaysFailCandidate(48)
    graph = build_content_diagnosis_subgraph(settings=settings, llm=llm)
    state = {"workflow_id":"wf-permanent-50", "version_id":version_id, "plan":{"estimated_candidates":50}}
    for _ in range(3):
        state = graph.invoke(state, config={"max_concurrency":4})
    item = next(item for item in AgentRunRepository(settings).list_work_items(state["run_id"]) if item.subject_id == "48")
    assert item.status == "permanent_failed"
    before = llm.calls_by_candidate[48]
    graph.invoke(state, config={"max_concurrency":4})
    assert llm.calls_by_candidate[48] == before == 3


def test_run_budget_skips_remaining_candidates_and_records_coverage(tmp_path):
    settings, version_id = _seed(tmp_path, 3)
    llm = FailOnceForCandidate(-1)
    graph = build_content_diagnosis_subgraph(settings=settings, llm=llm)
    result = graph.invoke({
        "workflow_id": "wf-budget", "version_id": version_id,
        "plan": {"estimated_candidates": 3}, "rule_scanned_nodes": 3,
        "rule_issue_count": 0, "budget": {"max_model_calls": 1, "max_tokens": 10000},
    }, config={"max_concurrency": 1})
    counts = AgentRunRepository(settings).counts(result["run_id"])
    assert counts["succeeded"] == 1
    assert counts["skipped"] == 2
    assert result["coverage"]["completion_status"] == "partial"
    assert result["coverage"]["model_calls"] == 1
    assert result["coverage"]["unexamined_reasons"] == {"BUDGET_EXHAUSTED": 2}
