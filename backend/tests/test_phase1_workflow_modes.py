from backend.app.agents.graph import (
    build_taxonomy_graph,
    route_after_resolve,
    route_after_required_node,
)
from backend.app.agents.states import TaxonomyGraphState


def _state(mode: str, **updates) -> TaxonomyGraphState:
    values = {
        "workflow_id": "wf",
        "thread_id": "thread",
        "workflow_mode": mode,
        "file_id": 1,
    }
    values.update(updates)
    return TaxonomyGraphState(**values)


def test_resolve_routes_import_maintain_and_verify_to_distinct_load_paths() -> None:
    assert route_after_resolve(_state("import")) == "parse_excel_node"
    assert (
        route_after_resolve(_state("maintain", base_version_id=1))
        == "load_version_context_node"
    )
    assert (
        route_after_resolve(
            _state("verify", base_version_id=1, result_version_id=2)
        )
        == "load_verification_context_node"
    )


def test_graph_contains_explicit_mode_nodes_and_verify_has_no_forbidden_edge() -> None:
    graph = build_taxonomy_graph(enable_suggestion_review=True).get_graph()
    node_ids = set(graph.nodes)
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert {
        "resolve_input_node",
        "load_version_context_node",
        "load_verification_context_node",
        "create_analysis_run_node",
        "generate_failed_report_node",
    }.issubset(node_ids)
    assert ("__start__", "resolve_input_node") in edges
    assert ("load_verification_context_node", "create_analysis_run_node") in edges
    assert ("create_analysis_run_node", "index_verification_versions_node") in edges
    assert (
        "index_verification_versions_node",
        "verify_base_quality_evaluation_node",
    ) in edges
    assert (
        "verify_base_quality_evaluation_node",
        "verify_result_quality_evaluation_node",
    ) in edges


def test_required_node_failure_routes_to_failed_report() -> None:
    state = _state(
        "maintain",
        base_version_id=1,
        current_version_id=1,
        status="failed",
        error_code="MODEL_OUTPUT_INVALID",
    )

    assert route_after_required_node(state, "content_diagnosis_node") == (
        "generate_failed_report_node"
    )
    assert (
        route_after_required_node(
            state.model_copy(update={"status": "running"}),
            "content_diagnosis_node",
        )
        == "content_diagnosis_node"
    )
