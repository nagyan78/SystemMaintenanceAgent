"""Thin LangGraph workflow nodes for the taxonomy maintenance MVP."""

from collections.abc import Callable
from typing import Any

from langgraph.types import interrupt

from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings, get_settings
from backend.app.repositories.task_repo import TaskRepository
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.content_diagnosis_service import (
    ContentDiagnosisAgent,
    DiagnosisPlanningAgent,
)
from backend.app.services.diagnosis_service import DiagnosisService
from backend.app.services.excel_service import ExcelService
from backend.app.services.report_service import ReportService
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.vector_index_service import VectorIndexService
from backend.app.services.version_service import VersionService


StateUpdate = dict[str, Any]
_runtime_settings: Settings = get_settings()


class WorkflowNodeError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def configure_workflow_runtime(settings: Settings) -> None:
    global _runtime_settings
    _runtime_settings = settings


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
    update = {
        "status": status,
        "current_step": current_step,
        "progress": progress,
        "completed_steps": completed_steps,
        **updates,
    }
    _record_progress(state, node_name, update)
    return update


def node_guard(
    node_name: str,
    fn: Callable[[TaxonomyGraphState], StateUpdate],
) -> Callable[[TaxonomyGraphState], StateUpdate]:
    def wrapped(state: TaxonomyGraphState) -> StateUpdate:
        try:
            return fn(state)
        except WorkflowNodeError as exc:
            _record_failure(state, node_name, exc.error_code, str(exc))
            return {
                "status": "failed",
                "current_step": node_name,
                "error_code": exc.error_code,
                "error_message": str(exc),
            }
        except Exception as exc:
            _record_failure(state, node_name, "WORKFLOW_NODE_ERROR", str(exc))
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
    result = ExcelService(_runtime_settings).parse_uploaded_file(file_id)
    return _complete_step(
        state,
        "parse_excel_node",
        current_step="parse_excel",
        progress=10,
        file_path=str(result.file_path),
        file_name=result.file_name,
        row_count=result.row_count,
        column_count=result.column_count,
        columns=result.columns,
    )


def build_tree_node(state: TaxonomyGraphState) -> StateUpdate:
    result = TaxonomyService(_runtime_settings).build_tree(_require_file_id(state))
    return _complete_step(
        state,
        "build_tree_node",
        current_step="build_tree",
        progress=20,
        node_count=result.node_count,
        max_depth=result.max_depth,
        max_children_count=result.max_children_count,
    )


def save_initial_version_node(state: TaxonomyGraphState) -> StateUpdate:
    result = VersionService(_runtime_settings).create_initial_version(_require_file_id(state))
    return _complete_step(
        state,
        "save_initial_version_node",
        current_step="save_initial_version",
        progress=30,
        base_version_id=result.version_id,
        current_version_id=result.version_id,
        version_no=result.version_no,
        node_count=result.node_count,
        max_depth=result.max_depth,
        max_children_count=result.max_children_count,
    )


def index_vector_node(state: TaxonomyGraphState) -> StateUpdate:
    result = VectorIndexService(_runtime_settings).index_version(
        _require_current_version_id(state)
    )
    return _complete_step(
        state,
        "index_vector_node",
        current_step="index_vector",
        progress=40,
        vector_index_status=result.status,
        vector_index_count=result.indexed_count,
    )


def structure_diagnosis_node(state: TaxonomyGraphState) -> StateUpdate:
    result = DiagnosisService(_runtime_settings).run_structure_diagnosis(
        _require_current_version_id(state)
    )
    return _complete_step(
        state,
        "structure_diagnosis_node",
        current_step="structure_diagnosis",
        progress=55,
        structure_issue_count=result.issue_count,
        structure_issue_summary=result.summary,
    )


def diagnosis_planning_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    plan = DiagnosisPlanningAgent(_runtime_settings).run(
        structure_stats=state.structure_issue_summary,
        tree_overview=TaxonomyService(_runtime_settings).get_planning_overview(version_id),
    )
    return _complete_step(
        state,
        "diagnosis_planning_node",
        current_step="diagnosis_planning",
        progress=62,
        diagnosis_plan=plan.model_dump(),
    )


def content_diagnosis_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    plan = DiagnosisPlan.model_validate(state.diagnosis_plan or {})
    issues = ContentDiagnosisAgent(_runtime_settings).run(version_id, plan)
    return _complete_step(
        state,
        "content_diagnosis_node",
        current_step="content_diagnosis",
        progress=68,
        content_issue_count=len(issues),
    )


def generate_suggestion_node(state: TaxonomyGraphState) -> StateUpdate:
    _require_current_version_id(state)
    return _complete_step(
        state,
        "generate_suggestion_node",
        current_step="generate_suggestion",
        progress=78,
        suggestion_count=0,
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
    version_id = state.current_version_id or state.base_version_id
    if version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Workflow requires version_id.")
    result = ReportService(_runtime_settings).generate_diagnosis_report(version_id)
    return _complete_step(
        state,
        "generate_report_node",
        current_step="completed",
        progress=100,
        status="completed",
        report_id=version_id,
        report_path=str(result.report_path),
    )


def _record_progress(
    state: TaxonomyGraphState,
    node_name: str,
    update: StateUpdate,
) -> None:
    if not state.task_id:
        return
    version_id = update.get("current_version_id") or state.current_version_id
    task_repo = TaskRepository(_runtime_settings)
    task_repo.update_task(
        task_id=state.task_id,
        status=update["status"],
        current_step=update["current_step"],
        progress=update["progress"],
        version_id=version_id,
        result_payload=update,
    )
    task_repo.record_event(
        workflow_id=state.workflow_id,
        thread_id=state.thread_id,
        task_id=state.task_id,
        node_name=node_name,
        event_type="node_completed",
        status=update["status"],
        progress=update["progress"],
        payload=update,
    )


def _record_failure(
    state: TaxonomyGraphState,
    node_name: str,
    error_code: str,
    message: str,
) -> None:
    if not state.task_id:
        return
    TaskRepository(_runtime_settings).record_event(
        workflow_id=state.workflow_id,
        thread_id=state.thread_id,
        task_id=state.task_id,
        node_name=node_name,
        event_type="node_failed",
        status="failed",
        message=message,
        payload={"error_code": error_code},
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
diagnosis_planning_node = node_guard(
    "diagnosis_planning_node",
    diagnosis_planning_node,
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
