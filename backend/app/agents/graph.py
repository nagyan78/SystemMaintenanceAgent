from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.agents.nodes import (
    build_tree_node,
    baseline_quality_evaluation_node,
    configure_workflow_runtime,
    content_diagnosis_node,
    create_analysis_run_node,
    diagnosis_planning_node,
    execute_action_node,
    generate_report_node,
    generate_failed_report_node,
    generate_degraded_report_node,
    generate_suggestion_node,
    index_vector_node,
    index_result_version_node,
    index_verification_versions_node,
    load_verification_context_node,
    load_version_context_node,
    parse_excel_node,
    resolve_input_node,
    save_initial_version_node,
    save_new_version_node,
    result_quality_evaluation_node,
    structure_diagnosis_node,
    validate_action_node,
    verify_base_quality_evaluation_node,
    verify_result_quality_evaluation_node,
    verification_node,
    wait_continue_node,
    wait_manual_intervention_node,
    wait_human_review_node,
)
from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings


def create_workflow_id(file_id: int) -> str:
    return f"workflow_{uuid4().hex}"


def create_thread_id(workflow_id: str) -> str:
    return f"taxonomy_workflow:{workflow_id}"


def create_initial_state(
    file_id: int,
    task_id: str | None = None,
    workflow_id: str | None = None,
    workflow_mode: str = "import",
    base_version_id: int | None = None,
    result_version_id: int | None = None,
    affected_node_ids: list[int] | None = None,
    max_rounds: int = 2,
) -> TaxonomyGraphState:
    resolved_workflow_id = workflow_id or create_workflow_id(file_id)
    return TaxonomyGraphState(
        workflow_id=resolved_workflow_id,
        thread_id=create_thread_id(resolved_workflow_id),
        file_id=file_id,
        workflow_mode=workflow_mode,
        base_version_id=base_version_id,
        result_version_id=result_version_id,
        affected_node_ids=affected_node_ids or [],
        max_rounds=max_rounds,
        task_id=task_id or resolved_workflow_id,
        status="pending",
    )


def create_memory_checkpointer() -> InMemorySaver:
    return InMemorySaver()


def route_after_suggestion(state: TaxonomyGraphState, *, enable_suggestion_review: bool = True) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    if not enable_suggestion_review:
        return "generate_report_node"
    if state.suggestion_count == 0 or state.review_batch_id is None:
        return "generate_report_node"
    return "wait_human_review_node"


def route_after_review(state: TaxonomyGraphState) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    if state.review_decision == "reject":
        return "generate_report_node"
    if state.approved_action_count == 0:
        return "generate_report_node"
    return "validate_action_node"


def route_after_validate(state: TaxonomyGraphState) -> str:
    if state.status == "failed" and state.current_step == "validate_action_node":
        return "generate_failed_report_node"
    return "execute_action_node"


def route_after_resolve(state: TaxonomyGraphState) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    return {
        "import": "parse_excel_node",
        "maintain": "load_version_context_node",
        "verify": "load_verification_context_node",
    }[state.workflow_mode]


def route_after_required_node(
    state: TaxonomyGraphState,
    success_target: str,
) -> str:
    return "generate_failed_report_node" if state.status == "failed" else success_target


def route_after_index(state: TaxonomyGraphState) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    if state.workflow_mode == "verify":
        return "verify_base_quality_evaluation_node"
    return "structure_diagnosis_node"


def route_after_analysis_run(state: TaxonomyGraphState) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    if state.workflow_mode == "verify":
        return "index_verification_versions_node"
    return "index_vector_node"


def route_after_verification(state: TaxonomyGraphState) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    payload = state.verification_payload or {}
    next_decision = payload.get("next_decision")
    verification_status = payload.get("status")
    if next_decision == "manual_intervention":
        return "wait_manual_intervention_node"
    if next_decision == "ask_continue":
        return "wait_continue_node"
    if verification_status == "degraded" or state.vector_index_status == "skipped":
        return "generate_degraded_report_node"
    return "generate_report_node"


def route_after_continue(state: TaxonomyGraphState) -> str:
    if state.status == "failed":
        return "generate_failed_report_node"
    if (state.review_payload or {}).get("decision") == "continue":
        return "create_analysis_run_node"
    return "generate_report_node"


def build_taxonomy_graph(
    checkpointer=None,
    settings: Settings | None = None,
    *,
    enable_suggestion_review: bool = True,
):
    if settings is not None:
        configure_workflow_runtime(settings)
    builder = StateGraph(TaxonomyGraphState)

    builder.add_node("resolve_input_node", resolve_input_node)
    builder.add_node("load_version_context_node", load_version_context_node)
    builder.add_node("load_verification_context_node", load_verification_context_node)
    builder.add_node("create_analysis_run_node", create_analysis_run_node)
    builder.add_node("parse_excel_node", parse_excel_node)
    builder.add_node("build_tree_node", build_tree_node)
    builder.add_node("save_initial_version_node", save_initial_version_node)
    builder.add_node("index_vector_node", index_vector_node)
    builder.add_node("index_result_version_node", index_result_version_node)
    builder.add_node(
        "index_verification_versions_node", index_verification_versions_node
    )
    builder.add_node("structure_diagnosis_node", structure_diagnosis_node)
    builder.add_node(
        "baseline_quality_evaluation_node", baseline_quality_evaluation_node
    )
    builder.add_node("result_quality_evaluation_node", result_quality_evaluation_node)
    builder.add_node(
        "verify_base_quality_evaluation_node", verify_base_quality_evaluation_node
    )
    builder.add_node(
        "verify_result_quality_evaluation_node", verify_result_quality_evaluation_node
    )
    builder.add_node("verification_node", verification_node)
    builder.add_node("wait_continue_node", wait_continue_node)
    builder.add_node(
        "wait_manual_intervention_node", wait_manual_intervention_node
    )
    builder.add_node("diagnosis_planning_node", diagnosis_planning_node)
    builder.add_node("content_diagnosis_node", content_diagnosis_node)
    builder.add_node("generate_suggestion_node", generate_suggestion_node)
    builder.add_node("wait_human_review_node", wait_human_review_node)
    builder.add_node("validate_action_node", validate_action_node)
    builder.add_node("execute_action_node", execute_action_node)
    builder.add_node("save_new_version_node", save_new_version_node)
    builder.add_node("generate_report_node", generate_report_node)
    builder.add_node("generate_failed_report_node", generate_failed_report_node)
    builder.add_node("generate_degraded_report_node", generate_degraded_report_node)

    builder.add_edge(START, "resolve_input_node")
    builder.add_conditional_edges(
        "resolve_input_node",
        route_after_resolve,
        {
            "parse_excel_node": "parse_excel_node",
            "load_version_context_node": "load_version_context_node",
            "load_verification_context_node": "load_verification_context_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "parse_excel_node",
        lambda state: route_after_required_node(state, "build_tree_node"),
        {
            "build_tree_node": "build_tree_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "build_tree_node",
        lambda state: route_after_required_node(state, "save_initial_version_node"),
        {
            "save_initial_version_node": "save_initial_version_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "save_initial_version_node",
        lambda state: route_after_required_node(state, "create_analysis_run_node"),
        {
            "create_analysis_run_node": "create_analysis_run_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "load_version_context_node",
        lambda state: route_after_required_node(state, "create_analysis_run_node"),
        {
            "create_analysis_run_node": "create_analysis_run_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "load_verification_context_node",
        lambda state: route_after_required_node(state, "create_analysis_run_node"),
        {
            "create_analysis_run_node": "create_analysis_run_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "create_analysis_run_node",
        route_after_analysis_run,
        {
            "index_vector_node": "index_vector_node",
            "index_verification_versions_node": "index_verification_versions_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "index_verification_versions_node",
        lambda state: route_after_required_node(
            state, "verify_base_quality_evaluation_node"
        ),
        {
            "verify_base_quality_evaluation_node": "verify_base_quality_evaluation_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "index_vector_node",
        route_after_index,
        {
            "structure_diagnosis_node": "structure_diagnosis_node",
            "verify_base_quality_evaluation_node": "verify_base_quality_evaluation_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "structure_diagnosis_node",
        lambda state: route_after_required_node(
            state, "baseline_quality_evaluation_node"
        ),
        {
            "baseline_quality_evaluation_node": "baseline_quality_evaluation_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "baseline_quality_evaluation_node",
        lambda state: route_after_required_node(state, "diagnosis_planning_node"),
        {
            "diagnosis_planning_node": "diagnosis_planning_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "verify_base_quality_evaluation_node",
        lambda state: route_after_required_node(
            state, "verify_result_quality_evaluation_node"
        ),
        {
            "verify_result_quality_evaluation_node": "verify_result_quality_evaluation_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "verify_result_quality_evaluation_node",
        lambda state: route_after_required_node(state, "verification_node"),
        {
            "verification_node": "verification_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "diagnosis_planning_node",
        lambda state: route_after_required_node(state, "content_diagnosis_node"),
        {
            "content_diagnosis_node": "content_diagnosis_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "content_diagnosis_node",
        lambda state: route_after_required_node(state, "generate_suggestion_node"),
        {
            "generate_suggestion_node": "generate_suggestion_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "generate_suggestion_node",
        lambda state: route_after_suggestion(
            state,
            enable_suggestion_review=enable_suggestion_review,
        ),
        {
            "wait_human_review_node": "wait_human_review_node",
            "generate_report_node": "generate_report_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "wait_human_review_node",
        route_after_review,
        {
            "validate_action_node": "validate_action_node",
            "generate_report_node": "generate_report_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "validate_action_node",
        route_after_validate,
        {
            "execute_action_node": "execute_action_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "execute_action_node",
        lambda state: route_after_required_node(state, "save_new_version_node"),
        {
            "save_new_version_node": "save_new_version_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "save_new_version_node",
        lambda state: route_after_required_node(state, "index_result_version_node"),
        {
            "index_result_version_node": "index_result_version_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "index_result_version_node",
        lambda state: route_after_required_node(
            state, "result_quality_evaluation_node"
        ),
        {
            "result_quality_evaluation_node": "result_quality_evaluation_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "result_quality_evaluation_node",
        lambda state: route_after_required_node(state, "verification_node"),
        {
            "verification_node": "verification_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "verification_node",
        route_after_verification,
        {
            "generate_report_node": "generate_report_node",
            "generate_degraded_report_node": "generate_degraded_report_node",
            "wait_continue_node": "wait_continue_node",
            "wait_manual_intervention_node": "wait_manual_intervention_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_conditional_edges(
        "wait_continue_node",
        route_after_continue,
        {
            "create_analysis_run_node": "create_analysis_run_node",
            "generate_report_node": "generate_report_node",
            "generate_failed_report_node": "generate_failed_report_node",
        },
    )
    builder.add_edge("generate_report_node", END)
    builder.add_edge("generate_degraded_report_node", END)
    builder.add_edge("generate_failed_report_node", END)
    builder.add_edge("wait_manual_intervention_node", END)

    return builder.compile(checkpointer=checkpointer)
