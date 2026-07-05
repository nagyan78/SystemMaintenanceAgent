"""Thin LangGraph workflow nodes for the taxonomy maintenance MVP."""

from collections.abc import Callable
from typing import Any

from langgraph.types import interrupt

from backend.app.agents.states import TaxonomyGraphState


StateUpdate = dict[str, Any]


class WorkflowNodeError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _complete_step(
    state: TaxonomyGraphState,
    node_name: str,
    *,
    progress: int,
    current_step: str,
    status: str = "running",
    **updates: Any,
) -> StateUpdate:
    completed_steps = [*state.completed_steps]
    if node_name not in completed_steps:
        completed_steps.append(node_name)
    return {
        "status": status,
        "current_step": current_step,
        "progress": progress,
        "completed_steps": completed_steps,
        **updates,
    }


def node_guard(
    node_name: str,
    fn: Callable[[TaxonomyGraphState], StateUpdate],
) -> Callable[[TaxonomyGraphState], StateUpdate]:
    def wrapped(state: TaxonomyGraphState) -> StateUpdate:
        try:
            return fn(state)
        except WorkflowNodeError as exc:
            return {
                "status": "failed",
                "current_step": node_name,
                "error_code": exc.error_code,
                "error_message": str(exc),
            }
        except Exception as exc:
            return {
                "status": "failed",
                "current_step": node_name,
                "error_code": "WORKFLOW_NODE_ERROR",
                "error_message": str(exc),
            }

    return wrapped


def _require_file_id(state: TaxonomyGraphState) -> int:
    if state.file_id is None:
        raise WorkflowNodeError("MISSING_FILE_ID", "Workflow requires file_id.")
    return state.file_id


def _require_current_version_id(state: TaxonomyGraphState) -> int:
    if state.current_version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Workflow requires current_version_id.")
    return state.current_version_id


def _require_review_batch_id(state: TaxonomyGraphState) -> str:
    if state.review_batch_id is None:
        raise WorkflowNodeError("MISSING_REVIEW_BATCH_ID", "Workflow requires review_batch_id.")
    return state.review_batch_id


def parse_excel_node(state: TaxonomyGraphState) -> StateUpdate:
    file_id = _require_file_id(state)
    return _complete_step(
        state,
        "parse_excel_node",
        current_step="parse_excel",
        progress=10,
        file_path=f"data/uploads/demo_file_{file_id}.xlsx",
        file_name=f"demo_file_{file_id}.xlsx",
        row_count=21090,
        column_count=6,
    )


def build_tree_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_file_id(state)
    return _complete_step(
        state,
        "build_tree_node",
        current_step="build_tree",
        progress=20,
        node_count=21090,
        max_depth=10,
        max_children_count=3125,
    )


def save_initial_version_node(state: TaxonomyGraphState) -> StateUpdate:
    file_id = _require_file_id(state)
    version_id = file_id
    return _complete_step(
        state,
        "save_initial_version_node",
        current_step="save_initial_version",
        progress=30,
        base_version_id=version_id,
        current_version_id=version_id,
        version_no="v1.0",
    )


def index_vector_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_current_version_id(state)
    return _complete_step(
        state,
        "index_vector_node",
        current_step="index_vector",
        progress=40,
    )


def structure_diagnosis_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_current_version_id(state)
    return _complete_step(
        state,
        "structure_diagnosis_node",
        current_step="structure_diagnosis",
        progress=55,
        structure_issue_count=44,
    )


def content_diagnosis_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_current_version_id(state)
    return _complete_step(
        state,
        "content_diagnosis_node",
        current_step="content_diagnosis",
        progress=68,
        content_issue_count=2,
    )


def generate_suggestion_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_current_version_id(state)
    review_batch_id = f"review_{state.workflow_id}"
    return _complete_step(
        state,
        "generate_suggestion_node",
        current_step="wait_human_review",
        progress=78,
        status="waiting_review",
        suggestion_count=3,
        review_batch_id=review_batch_id,
    )


def wait_human_review_node(state: TaxonomyGraphState) -> StateUpdate:
    review_batch_id = _require_review_batch_id(state)
    decision = interrupt(
        {
            "type": "human_review",
            "review_batch_id": review_batch_id,
            "suggestion_count": state.suggestion_count,
            "required_actions": ["approve", "reject", "edit"],
        }
    )
    approved_ids = decision.get("approved_suggestion_ids", [])
    review_decision = decision.get("decision")
    if review_decision not in {"approve", "reject", "edit"}:
        raise WorkflowNodeError("INVALID_REVIEW_DECISION", "Review decision is invalid.")
    return _complete_step(
        state,
        "wait_human_review_node",
        current_step="human_review_completed",
        progress=82,
        status="running",
        review_decision=review_decision,
        review_payload=decision,
        approved_action_count=len(approved_ids),
    )


def validate_action_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_review_batch_id(state)
    return _complete_step(
        state,
        "validate_action_node",
        current_step="validate_action",
        progress=86,
    )


def execute_action_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_current_version_id(state)
    _require_review_batch_id(state)
    return _complete_step(
        state,
        "execute_action_node",
        current_step="execute_action",
        progress=91,
        executed_action_count=state.approved_action_count,
    )


def save_new_version_node(state: TaxonomyGraphState) -> StateUpdate:
    current_version_id = _require_current_version_id(state)
    return _complete_step(
        state,
        "save_new_version_node",
        current_step="save_new_version",
        progress=96,
        new_version_id=current_version_id + 1,
        current_version_id=current_version_id + 1,
        version_no="v1.1",
    )


def generate_report_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = state.current_version_id or state.base_version_id or 0
    return _complete_step(
        state,
        "generate_report_node",
        current_step="completed",
        progress=100,
        status="completed",
        report_id=version_id,
        report_path=f"data/reports/{state.workflow_id}.md",
    )


parse_excel_node = node_guard("parse_excel_node", parse_excel_node)
build_tree_node = node_guard("build_tree_node", build_tree_node)
save_initial_version_node = node_guard(
    "save_initial_version_node",
    save_initial_version_node,
)
index_vector_node = node_guard("index_vector_node", index_vector_node)
structure_diagnosis_node = node_guard(
    "structure_diagnosis_node",
    structure_diagnosis_node,
)
content_diagnosis_node = node_guard("content_diagnosis_node", content_diagnosis_node)
generate_suggestion_node = node_guard(
    "generate_suggestion_node",
    generate_suggestion_node,
)
validate_action_node = node_guard("validate_action_node", validate_action_node)
execute_action_node = node_guard("execute_action_node", execute_action_node)
save_new_version_node = node_guard("save_new_version_node", save_new_version_node)
generate_report_node = node_guard("generate_report_node", generate_report_node)
