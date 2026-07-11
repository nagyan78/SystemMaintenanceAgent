from backend.app.agents.graph import (
    build_taxonomy_graph,
    create_initial_state,
    route_after_validate,
)
from backend.app.agents.states import TaxonomyGraphState


def test_legacy_initial_state_is_import_file_driven() -> None:
    state = create_initial_state(file_id=7, task_id="task-7", workflow_id="wf-7")

    assert state.file_id == 7
    assert state.base_version_id is None
    assert state.current_version_id is None
    assert state.status == "pending"


def test_legacy_graph_starts_with_excel_and_saves_new_version_before_report() -> None:
    graph = build_taxonomy_graph(enable_suggestion_review=True).get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert ("__start__", "parse_excel_node") in edges
    assert ("execute_action_node", "save_new_version_node") in edges
    assert ("save_new_version_node", "generate_report_node") in edges


def test_legacy_validation_failure_routes_to_normal_report() -> None:
    state = TaxonomyGraphState(
        workflow_id="wf",
        thread_id="thread",
        status="failed",
        current_step="validate_action_node",
        error_code="ACTION_VALIDATION_FAILED",
    )

    assert route_after_validate(state) == "generate_report_node"


def test_legacy_review_state_requires_review_batch() -> None:
    state = TaxonomyGraphState(
        workflow_id="wf",
        thread_id="thread",
        status="waiting_review",
        review_batch_id="review-1",
    )

    assert state.review_batch_id == "review-1"
