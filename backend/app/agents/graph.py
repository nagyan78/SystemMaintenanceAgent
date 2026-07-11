from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.agents.nodes import (
    build_tree_node,
    bind_workflow_node,
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
from backend.app.config import Settings, get_settings


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


def route_after_suggestion(state: TaxonomyGraphState, *, enable_suggestion_review: bool = True) -> str:
    if not enable_suggestion_review:
        return "generate_report_node"
    if state.suggestion_count == 0 or state.review_batch_id is None:
        return "generate_report_node"
    return "wait_human_review_node"


def route_after_review(state: TaxonomyGraphState) -> str:
    if state.review_decision == "reject":
        return "generate_report_node"
    if state.approved_action_count == 0:
        return "generate_report_node"
    return "validate_action_node"


def route_after_validate(state: TaxonomyGraphState) -> str:
    if state.status == "failed" and state.current_step == "validate_action_node":
        return "generate_report_node"
    return "execute_action_node"


def build_taxonomy_graph(
    checkpointer=None,
    settings: Settings | None = None,
    *,
    enable_suggestion_review: bool = True,
):
    runtime_settings = settings or get_settings()
    builder = StateGraph(TaxonomyGraphState)

    builder.add_node("parse_excel_node", bind_workflow_node(parse_excel_node, runtime_settings))
    builder.add_node("build_tree_node", bind_workflow_node(build_tree_node, runtime_settings))
    builder.add_node("save_initial_version_node", bind_workflow_node(save_initial_version_node, runtime_settings))
    builder.add_node("index_vector_node", bind_workflow_node(index_vector_node, runtime_settings))
    builder.add_node("structure_diagnosis_node", bind_workflow_node(structure_diagnosis_node, runtime_settings))
    builder.add_node("diagnosis_planning_node", bind_workflow_node(diagnosis_planning_node, runtime_settings))
    builder.add_node("content_diagnosis_node", bind_workflow_node(content_diagnosis_node, runtime_settings))
    builder.add_node("generate_suggestion_node", bind_workflow_node(generate_suggestion_node, runtime_settings))
    builder.add_node("wait_human_review_node", bind_workflow_node(wait_human_review_node, runtime_settings))
    builder.add_node("validate_action_node", bind_workflow_node(validate_action_node, runtime_settings))
    builder.add_node("execute_action_node", bind_workflow_node(execute_action_node, runtime_settings))
    builder.add_node("save_new_version_node", bind_workflow_node(save_new_version_node, runtime_settings))
    builder.add_node("generate_report_node", bind_workflow_node(generate_report_node, runtime_settings))

    builder.add_edge(START, "parse_excel_node")
    builder.add_edge("parse_excel_node", "build_tree_node")
    builder.add_edge("build_tree_node", "save_initial_version_node")
    builder.add_edge("save_initial_version_node", "index_vector_node")
    builder.add_edge("index_vector_node", "structure_diagnosis_node")
    builder.add_edge("structure_diagnosis_node", "diagnosis_planning_node")
    builder.add_edge("diagnosis_planning_node", "content_diagnosis_node")
    builder.add_edge("content_diagnosis_node", "generate_suggestion_node")
    builder.add_conditional_edges(
        "generate_suggestion_node",
        lambda state: route_after_suggestion(
            state,
            enable_suggestion_review=enable_suggestion_review,
        ),
        {
            "wait_human_review_node": "wait_human_review_node",
            "generate_report_node": "generate_report_node",
        },
    )
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
            "execute_action_node": "execute_action_node",
            "generate_report_node": "generate_report_node",
        },
    )
    builder.add_edge("execute_action_node", "save_new_version_node")
    builder.add_edge("save_new_version_node", "generate_report_node")
    builder.add_edge("generate_report_node", END)

    return builder.compile(checkpointer=checkpointer)
