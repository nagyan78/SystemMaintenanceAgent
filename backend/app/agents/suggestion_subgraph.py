from typing import Annotated, Any, TypedDict
import operator

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.app.config import Settings
from backend.app.services.agent_run_service import AgentRunService


class SuggestionSubgraphState(TypedDict, total=False):
    workflow_id: str
    version_id: int
    analysis_run_id: str | None
    run_id: str
    review_batch_id: str
    work_item_ids: list[str]
    work_item_id: str
    processed_count: Annotated[int, operator.add]
    suggestion_count: Annotated[int, operator.add]
    failed_count: Annotated[int, operator.add]
    work_item_counts: dict[str, int]


def build_suggestion_subgraph(*, settings: Settings, llm: Any | None = None):
    service = AgentRunService(settings, llm=llm)

    def prepare(state: SuggestionSubgraphState) -> dict:
        if state.get("run_id"):
            run = service.repo.get_run(state["run_id"])
            return {"run_id": state["run_id"], "review_batch_id": run["budget"]["review_batch_id"], "work_item_ids": [item.id for item in service.repo.list_work_items(state["run_id"])]}
        return service.prepare_suggestion_issues(workflow_id=state["workflow_id"], version_id=state["version_id"], analysis_run_id=state.get("analysis_run_id"))

    def fan_out(state: SuggestionSubgraphState):
        runnable = [item_id for item_id in state.get("work_item_ids", []) if service.repo.is_runnable(item_id)]
        if not runnable:
            return "reduce"
        return [Send("generate_issue_suggestion", {"workflow_id": state["workflow_id"], "version_id": state["version_id"], "run_id": state["run_id"], "work_item_id": item_id}) for item_id in runnable]

    def generate(state: SuggestionSubgraphState) -> dict:
        return service.execute_suggestion_work_item(state["work_item_id"])

    def reduce(state: SuggestionSubgraphState) -> dict:
        return {"work_item_counts": service.finalize_run(state["run_id"])}

    graph = StateGraph(SuggestionSubgraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("generate_issue_suggestion", generate)
    graph.add_node("reduce", reduce)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", fan_out, ["generate_issue_suggestion", "reduce"])
    graph.add_edge("generate_issue_suggestion", "reduce")
    graph.add_edge("reduce", END)
    return graph.compile()
