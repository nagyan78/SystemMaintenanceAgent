from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.agents.nodes import (
    ai_review_action_node,
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
    verify_new_version_node,
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
    enable_ai_analysis: bool = False,
    model_provider: str | None = None,
    model_name: str | None = None,
    priority_subtree_ids: list[int] | None = None,
    sample_strategy: str = "sampling",
    focus_issues: list[str] | None = None,
    ai_candidate_limit: int | None = None,
    ai_max_model_calls: int | None = None,
    ai_token_budget: int | None = None,
    ai_wall_seconds: int | None = None,
) -> TaxonomyGraphState:
    resolved_workflow_id = workflow_id or create_workflow_id(file_id)
    return TaxonomyGraphState(
        workflow_id=resolved_workflow_id,
        thread_id=create_thread_id(resolved_workflow_id),
        file_id=file_id,
        task_id=task_id or resolved_workflow_id,
        status="pending",
        enable_ai_analysis=enable_ai_analysis,
        model_provider=model_provider,
        model_name=model_name,
        priority_subtree_ids=priority_subtree_ids or [],
        sample_strategy=sample_strategy,
        focus_issues=focus_issues or [],
        ai_candidate_limit=ai_candidate_limit,
        ai_max_model_calls=ai_max_model_calls,
        ai_token_budget=ai_token_budget,
        ai_wall_seconds=ai_wall_seconds,
    )


def create_memory_checkpointer() -> InMemorySaver:
    return InMemorySaver()


def route_after_suggestion(state: TaxonomyGraphState) -> str:
    if state.status in {"failed", "cancelled"}:
        return "end"
    if state.suggestion_count == 0 or state.review_batch_id is None:
        return "generate_report_node"
    return "ai_review_action_node"


def route_after_diagnosis(state: TaxonomyGraphState) -> str:
    if state.status in {"failed", "cancelled"}:
        return "end"
    return "generate_suggestion_node" if state.enable_ai_analysis else "generate_report_node"


def route_after_review(state: TaxonomyGraphState) -> str:
    if state.status in {"failed", "cancelled"}:
        return "end"
    if state.review_decision == "reject":
        return "generate_report_node"
    if state.approved_action_count == 0:
        return "generate_report_node"
    return "validate_action_node"


def route_after_validate(state: TaxonomyGraphState) -> str:
    if state.status in {"failed", "cancelled"}:
        return "end"
    return "execute_action_node"


def route_if_success(state: TaxonomyGraphState, next_node: str) -> str:
    return "end" if state.status in {"failed", "cancelled"} else next_node


def build_taxonomy_graph(
    checkpointer=None,
    settings: Settings | None = None,
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
    builder.add_node("ai_review_action_node", bind_workflow_node(ai_review_action_node, runtime_settings))
    builder.add_node("validate_action_node", bind_workflow_node(validate_action_node, runtime_settings))
    builder.add_node("execute_action_node", bind_workflow_node(execute_action_node, runtime_settings))
    builder.add_node("save_new_version_node", bind_workflow_node(save_new_version_node, runtime_settings))
    builder.add_node("verify_new_version_node", bind_workflow_node(verify_new_version_node, runtime_settings))
    builder.add_node("generate_report_node", bind_workflow_node(generate_report_node, runtime_settings))

    builder.add_edge(START, "parse_excel_node")
    for source, target in (
        ("parse_excel_node", "build_tree_node"),
        ("build_tree_node", "save_initial_version_node"),
        ("save_initial_version_node", "index_vector_node"),
        ("index_vector_node", "structure_diagnosis_node"),
        ("structure_diagnosis_node", "diagnosis_planning_node"),
        ("diagnosis_planning_node", "content_diagnosis_node"),
    ):
        builder.add_conditional_edges(
            source,
            lambda state, target=target: route_if_success(state, target),
            {target: target, "end": END},
        )
    builder.add_conditional_edges(
        "content_diagnosis_node",
        route_after_diagnosis,
        {"generate_suggestion_node": "generate_suggestion_node", "generate_report_node": "generate_report_node", "end": END},
    )
    builder.add_conditional_edges(
        "generate_suggestion_node",
        route_after_suggestion,
        {
            "ai_review_action_node": "ai_review_action_node",
            "generate_report_node": "generate_report_node",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "ai_review_action_node",
        route_after_review,
        {"validate_action_node": "validate_action_node", "generate_report_node": "generate_report_node", "end": END},
    )
    builder.add_conditional_edges(
        "validate_action_node",
        route_after_validate,
        {"execute_action_node": "execute_action_node", "end": END},
    )
    for source, target in (
        ("execute_action_node", "save_new_version_node"),
        ("save_new_version_node", "verify_new_version_node"),
        ("verify_new_version_node", "generate_report_node"),
    ):
        builder.add_conditional_edges(
            source,
            lambda state, target=target: route_if_success(state, target),
            {target: target, "end": END},
        )
    builder.add_edge("generate_report_node", END)

    return builder.compile(checkpointer=checkpointer)
