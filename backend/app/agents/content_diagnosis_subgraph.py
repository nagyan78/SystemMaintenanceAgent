from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.app.agents.reducers import ContentDiagnosisSubgraphState
from backend.app.config import Settings
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.agent_run_service import AgentRunService


def build_content_diagnosis_subgraph(*, settings: Settings, llm: Any | None = None):
    service = AgentRunService(settings, llm=llm)

    def prepare(state: ContentDiagnosisSubgraphState) -> dict:
        if state.get("run_id"):
            return {"run_id": state["run_id"], "work_item_ids": [item.id for item in service.repo.list_work_items(state["run_id"])]}
        prepared = service.prepare_content_candidates(
            workflow_id=state["workflow_id"], version_id=state["version_id"],
            plan=DiagnosisPlan.model_validate(state.get("plan") or {}),
            rule_scanned_nodes=int(state.get("rule_scanned_nodes", 0)),
            rule_issue_count=int(state.get("rule_issue_count", 0)),
            budget=dict(state.get("budget") or {}),
        )
        return prepared

    def diagnose(state: ContentDiagnosisSubgraphState) -> dict:
        return service.execute_content_batches(state["run_id"])

    def reduce(state: ContentDiagnosisSubgraphState) -> dict:
        counts = service.finalize_run(state["run_id"])
        return {"work_item_counts": counts, "coverage": service.coverage_for_run(state["run_id"])}

    graph = StateGraph(ContentDiagnosisSubgraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("diagnose_batches", diagnose)
    graph.add_node("reduce", reduce)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "diagnose_batches")
    graph.add_edge("diagnose_batches", "reduce")
    graph.add_edge("reduce", END)
    return graph.compile()
