from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.agents.nodes import (
    build_tree_node,
    configure_workflow_runtime,
    content_diagnosis_node,
    diagnosis_planning_node,
    execute_action_node,
    generate_report_node,
    generate_suggestion_node,
    index_vector_node,
    parse_excel_node,
    save_initial_version_node,
    save_new_version_node,
    structure_diagnosis_node,
    validate_action_node,
    wait_human_review_node,
)
from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings


def create_workflow_id(file_id: int) -> str:
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")
    return f"import_{file_id}_{timestamp}"


def create_thread_id(workflow_id: str) -> str:
    return f"taxonomy_workflow:{workflow_id}"


def create_initial_state(
    file_id: int,
    task_id: str | None = None,
    workflow_id: str | None = None,
) -> TaxonomyGraphState:
    resolved_workflow_id = workflow_id or create_workflow_id(file_id)
    return TaxonomyGraphState(
        workflow_id=resolved_workflow_id,
        thread_id=create_thread_id(resolved_workflow_id),
        file_id=file_id,
        task_id=task_id or resolved_workflow_id,
        status="pending",
    )


def create_memory_checkpointer() -> InMemorySaver:
    return InMemorySaver()


def route_after_review(state: TaxonomyGraphState) -> str:
    if state.review_decision == "reject":
        return "generate_report_node"
    if state.approved_action_count == 0:
        return "generate_report_node"
    return "validate_action_node"


def route_after_validate(state: TaxonomyGraphState) -> str:
    if state.error_code:
        return "wait_human_review_node"
    return "execute_action_node"


def build_taxonomy_graph(checkpointer=None, settings: Settings | None = None):
    if settings is not None:
        configure_workflow_runtime(settings)
    builder = StateGraph(TaxonomyGraphState)

    builder.add_node("parse_excel_node", parse_excel_node)
    builder.add_node("build_tree_node", build_tree_node)
    builder.add_node("save_initial_version_node", save_initial_version_node)
    builder.add_node("index_vector_node", index_vector_node)
    builder.add_node("structure_diagnosis_node", structure_diagnosis_node)
    builder.add_node("diagnosis_planning_node", diagnosis_planning_node)
    builder.add_node("content_diagnosis_node", content_diagnosis_node)
    builder.add_node("generate_suggestion_node", generate_suggestion_node)
    builder.add_node("wait_human_review_node", wait_human_review_node)
    builder.add_node("validate_action_node", validate_action_node)
    builder.add_node("execute_action_node", execute_action_node)
    builder.add_node("save_new_version_node", save_new_version_node)
    builder.add_node("generate_report_node", generate_report_node)

    builder.add_edge(START, "parse_excel_node")
    builder.add_edge("parse_excel_node", "build_tree_node")
    builder.add_edge("build_tree_node", "save_initial_version_node")
    builder.add_edge("save_initial_version_node", "index_vector_node")
    builder.add_edge("index_vector_node", "structure_diagnosis_node")
    builder.add_edge("structure_diagnosis_node", "diagnosis_planning_node")
    builder.add_edge("diagnosis_planning_node", "content_diagnosis_node")
    builder.add_edge("content_diagnosis_node", "generate_report_node")
    builder.add_conditional_edges(
        "wait_human_review_node",
        route_after_review,
        {
            "validate_action_node": "validate_action_node",
            "generate_report_node": "generate_report_node",
        },
    )
    builder.add_conditional_edges(
        "validate_action_node",
        route_after_validate,
        {
            "wait_human_review_node": "wait_human_review_node",
            "execute_action_node": "execute_action_node",
        },
    )
    builder.add_edge("execute_action_node", "save_new_version_node")
    builder.add_edge("save_new_version_node", "generate_report_node")
    builder.add_edge("generate_report_node", END)

    return builder.compile(checkpointer=checkpointer)
