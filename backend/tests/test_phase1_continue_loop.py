from backend.app.agents.events import interrupt_event
from backend.app.agents.graph import (
    build_taxonomy_graph,
    route_after_continue,
    route_after_verification,
)
from backend.app.agents.nodes import apply_continue_decision
from backend.app.agents.states import TaxonomyGraphState


def _state(**updates) -> TaxonomyGraphState:
    values = {
        "workflow_id": "wf",
        "thread_id": "thread",
        "workflow_mode": "maintain",
        "base_version_id": 1,
        "current_version_id": 2,
        "result_version_id": 2,
        "analysis_run_id": "run-1",
        "round": 1,
        "max_rounds": 2,
        "action_batch_id": "action",
        "diagnosis_plan": {"sample_strategy": "focused"},
        "executed_nodes": [{"category_id": 1}],
        "evaluation_before_id": 10,
        "evaluation_after_id": 11,
    }
    values.update(updates)
    return TaxonomyGraphState(**values)


def test_verification_routes_to_continue_degraded_manual_or_success() -> None:
    assert route_after_verification(
        _state(verification_payload={"next_decision": "ask_continue", "status": "partially_passed"})
    ) == "wait_continue_node"
    assert route_after_verification(
        _state(verification_payload={"next_decision": "finish", "status": "degraded"})
    ) == "generate_degraded_report_node"
    assert route_after_verification(
        _state(verification_payload={"next_decision": "manual_intervention", "status": "failed"})
    ) == "wait_manual_intervention_node"
    assert route_after_verification(
        _state(verification_payload={"next_decision": "finish", "status": "passed"})
    ) == "generate_report_node"
    assert route_after_verification(
        _state(
            vector_index_status="skipped",
            verification_payload={"next_decision": "finish", "status": "passed"},
        )
    ) == "generate_degraded_report_node"


def test_continue_promotes_result_and_clears_round_scoped_state() -> None:
    update = apply_continue_decision(_state(), decision="continue")

    assert update["base_version_id"] == 2
    assert update["current_version_id"] == 2
    assert update["result_version_id"] is None
    assert update["round"] == 2
    assert update["analysis_run_id"] is None
    assert update["action_batch_id"] is None
    assert update["diagnosis_plan"] is None
    assert update["executed_nodes"] == []
    assert update["evaluation_before_id"] is None
    assert update["evaluation_after_id"] is None


def test_continue_is_rejected_at_round_limit() -> None:
    try:
        apply_continue_decision(_state(round=2), decision="continue")
    except ValueError as exc:
        assert "max_rounds" in str(exc)
    else:
        raise AssertionError("continue was accepted at max_rounds")


def test_continue_interrupt_has_distinct_sse_contract() -> None:
    event = interrupt_event(
        '{"interrupt_type":"continue_optimization","interrupt_id":"int-1",'
        '"round":1}'
    )

    assert event["event"] == "workflow_waiting_continue"
    assert event["data"]["interrupt_id"] == "int-1"
    assert event["data"]["round"] == 1


def test_graph_continue_returns_through_new_analysis_run() -> None:
    edges = {
        (edge.source, edge.target)
        for edge in build_taxonomy_graph().get_graph().edges
    }

    assert ("verification_node", "wait_continue_node") in edges
    assert ("wait_continue_node", "create_analysis_run_node") in edges
    assert ("wait_continue_node", "generate_report_node") in edges
    assert route_after_continue(_state(continuation_payload={"decision": "finish"})) == (
        "generate_report_node"
    )
