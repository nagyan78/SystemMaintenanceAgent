from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

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
        )
        return prepared

    def fan_out(state: ContentDiagnosisSubgraphState):
        runnable = [item_id for item_id in state.get("work_item_ids", []) if service.repo.is_runnable(item_id)]
        if not runnable:
            return "reduce"
        return [Send("diagnose_candidate", {"workflow_id": state["workflow_id"], "version_id": state["version_id"], "run_id": state["run_id"], "work_item_id": item_id}) for item_id in runnable]

    def diagnose(state: ContentDiagnosisSubgraphState) -> dict:
        return service.execute_content_work_item(state["work_item_id"])

    def reduce(state: ContentDiagnosisSubgraphState) -> dict:
        return {"work_item_counts": service.finalize_run(state["run_id"])}

    graph = StateGraph(ContentDiagnosisSubgraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("diagnose_candidate", diagnose)
    graph.add_node("reduce", reduce)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", fan_out, ["diagnose_candidate", "reduce"])
    graph.add_edge("diagnose_candidate", "reduce")
    graph.add_edge("reduce", END)
    return graph.compile()
