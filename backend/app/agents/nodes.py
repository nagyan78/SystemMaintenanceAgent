"""Thin LangGraph workflow nodes for the taxonomy maintenance MVP."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from langgraph.types import interrupt

from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings, get_settings
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.analysis_run_repo import AnalysisRunRepository
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.action_service import ActionService
from backend.app.services.content_diagnosis_service import (
    ContentDiagnosisAgent,
    DiagnosisPlanningAgent,
)
from backend.app.services.diagnosis_service import DiagnosisService
from backend.app.services.excel_service import ExcelService
from backend.app.services.report_service import ReportService
from backend.app.services.quality_evaluation_service import QualityEvaluationService
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.vector_index_service import VectorIndexService
from backend.app.services.verification_service import VerificationService
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


def _require_action_batch_id(state: TaxonomyGraphState) -> str:
    if state.action_batch_id is None:
        raise WorkflowNodeError("MISSING_ACTION_BATCH_ID", "Workflow requires action_batch_id.")
    return state.action_batch_id


def resolve_input_node(state: TaxonomyGraphState) -> StateUpdate:
    if state.workflow_mode == "import":
        _require_file_id(state)
    elif state.workflow_mode == "maintain" and state.base_version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Maintain requires base_version_id.")
    elif state.workflow_mode == "verify" and (
        state.base_version_id is None or state.result_version_id is None
    ):
        raise WorkflowNodeError(
            "MISSING_VERSION_ID",
            "Verify requires base_version_id and result_version_id.",
        )
    return _complete_step(
        state,
        "resolve_input_node",
        current_step="resolve_input",
        progress=2,
    )


def load_version_context_node(state: TaxonomyGraphState) -> StateUpdate:
    version = VersionService(_runtime_settings).get_version(int(state.base_version_id))
    if version is None:
        raise WorkflowNodeError("VERSION_NOT_FOUND", "Base version was not found.")
    return _complete_step(
        state,
        "load_version_context_node",
        current_step="load_version_context",
        progress=5,
        file_id=int(version["file_id"]),
        current_version_id=int(version["id"]),
        version_no=str(version["version_no"]),
    )


def load_verification_context_node(state: TaxonomyGraphState) -> StateUpdate:
    version = VersionService(_runtime_settings).get_version(int(state.result_version_id))
    if version is None:
        raise WorkflowNodeError("VERSION_NOT_FOUND", "Result version was not found.")
    return _complete_step(
        state,
        "load_verification_context_node",
        current_step="load_verification_context",
        progress=5,
        file_id=int(version["file_id"]),
        current_version_id=int(version["id"]),
        version_no=str(version["version_no"]),
    )


def create_analysis_run_node(state: TaxonomyGraphState) -> StateUpdate:
    run_id = AnalysisRunRepository(_runtime_settings).create_or_get(
        workflow_id=state.workflow_id,
        round_no=state.round,
        analyzed_version_id=_require_current_version_id(state),
    )
    return _complete_step(
        state,
        "create_analysis_run_node",
        current_step="create_analysis_run",
        progress=max(state.progress, 8),
        analysis_run_id=run_id,
    )


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
    if result.status == "failed":
        raise WorkflowNodeError(
            "VECTOR_INDEX_FAILED",
            result.error_message or "Vector index failed.",
        )
    return _complete_step(
        state,
        "index_vector_node",
        current_step="index_vector",
        progress=40,
        vector_index_status=result.status,
        vector_index_count=result.indexed_count,
    )


def index_result_version_node(state: TaxonomyGraphState) -> StateUpdate:
    result = VectorIndexService(_runtime_settings).index_version(
        _require_current_version_id(state),
        changed_category_ids=state.affected_node_ids or None,
    )
    if result.status == "failed":
        raise WorkflowNodeError(
            "RESULT_VECTOR_INDEX_FAILED",
            result.error_message or "Result version index failed.",
        )
    return _complete_step(
        state,
        "index_result_version_node",
        current_step="index_result_version",
        progress=96,
        vector_index_status=result.status,
        vector_index_count=result.indexed_count,
    )


def index_verification_versions_node(state: TaxonomyGraphState) -> StateUpdate:
    if state.base_version_id is None or state.result_version_id is None:
        raise WorkflowNodeError(
            "MISSING_VERIFICATION_VERSION",
            "Verify indexing requires base and result versions.",
        )
    results = [
        VectorIndexService(_runtime_settings).index_version(state.base_version_id),
        VectorIndexService(_runtime_settings).index_version(state.result_version_id),
    ]
    failed = next((item for item in results if item.status == "failed"), None)
    if failed is not None:
        raise WorkflowNodeError(
            "VERIFY_VECTOR_INDEX_FAILED",
            failed.error_message or "Verification vector index failed.",
        )
    combined_status = (
        "skipped" if any(item.status == "skipped" for item in results) else "ready"
    )
    return _complete_step(
        state,
        "index_verification_versions_node",
        current_step="index_verification_versions",
        progress=35,
        vector_index_status=combined_status,
        vector_index_count=sum(item.indexed_count for item in results),
    )


def structure_diagnosis_node(state: TaxonomyGraphState) -> StateUpdate:
    result = DiagnosisService(_runtime_settings).run_structure_diagnosis(
        _require_current_version_id(state),
        workflow_id=state.workflow_id,
        analysis_run_id=state.analysis_run_id,
    )
    return _complete_step(
        state,
        "structure_diagnosis_node",
        current_step="structure_diagnosis",
        progress=55,
        structure_issue_count=result.issue_count,
        structure_issue_summary=result.summary,
    )


def _quality_evaluation_update(
    state: TaxonomyGraphState,
    *,
    node_name: str,
    version_id: int,
    role: str,
    result_field: str,
    progress: int,
) -> StateUpdate:
    if state.analysis_run_id is None:
        raise WorkflowNodeError(
            "MISSING_ANALYSIS_RUN",
            "Quality evaluation requires analysis_run_id.",
        )
    result = QualityEvaluationService(_runtime_settings).evaluate(
        workflow_id=state.workflow_id,
        analysis_run_id=state.analysis_run_id,
        version_id=version_id,
        evaluation_role=role,
    )
    return _complete_step(
        state,
        node_name,
        current_step=node_name.removesuffix("_node"),
        progress=progress,
        **{result_field: result.id},
    )


def baseline_quality_evaluation_node(state: TaxonomyGraphState) -> StateUpdate:
    return _quality_evaluation_update(
        state,
        node_name="baseline_quality_evaluation_node",
        version_id=_require_current_version_id(state),
        role="baseline",
        result_field="evaluation_before_id",
        progress=58,
    )


def result_quality_evaluation_node(state: TaxonomyGraphState) -> StateUpdate:
    return _quality_evaluation_update(
        state,
        node_name="result_quality_evaluation_node",
        version_id=_require_current_version_id(state),
        role="result",
        result_field="evaluation_after_id",
        progress=97,
    )


def verify_base_quality_evaluation_node(state: TaxonomyGraphState) -> StateUpdate:
    return _quality_evaluation_update(
        state,
        node_name="verify_base_quality_evaluation_node",
        version_id=int(state.base_version_id),
        role="verify_base",
        result_field="evaluation_before_id",
        progress=45,
    )


def verify_result_quality_evaluation_node(state: TaxonomyGraphState) -> StateUpdate:
    return _quality_evaluation_update(
        state,
        node_name="verify_result_quality_evaluation_node",
        version_id=int(state.result_version_id),
        role="verify_result",
        result_field="evaluation_after_id",
        progress=65,
    )


def verification_node(state: TaxonomyGraphState) -> StateUpdate:
    if state.base_version_id is None or state.current_version_id is None:
        raise WorkflowNodeError(
            "MISSING_VERIFICATION_VERSION",
            "Verification requires base and result versions.",
        )
    if state.evaluation_before_id is None or state.evaluation_after_id is None:
        raise WorkflowNodeError(
            "MISSING_VERIFICATION_EVALUATION",
            "Verification requires before and after evaluations.",
        )
    result = VerificationService(_runtime_settings).verify(
        base_version_id=state.base_version_id,
        result_version_id=state.current_version_id,
        affected_node_ids=state.affected_node_ids,
        evaluation_before_id=state.evaluation_before_id,
        evaluation_after_id=state.evaluation_after_id,
        current_round=state.round,
        max_rounds=state.max_rounds,
    )
    return _complete_step(
        state,
        "verification_node",
        current_step="verification",
        progress=98,
        verification_payload=result.model_dump(),
    )


def apply_continue_decision(
    state: TaxonomyGraphState,
    *,
    decision: str,
) -> StateUpdate:
    if decision == "finish":
        return {
            "continuation_payload": {"decision": "finish"},
            "interrupt_type": None,
            "interrupt_id": None,
        }
    if decision != "continue":
        raise ValueError("Continue decision must be continue or finish.")
    if state.round >= state.max_rounds:
        raise ValueError("Cannot continue because max_rounds has been reached.")
    result_version_id = state.result_version_id or state.current_version_id
    if result_version_id is None:
        raise ValueError("Continue requires a result version.")
    return {
        "base_version_id": result_version_id,
        "current_version_id": result_version_id,
        "result_version_id": None,
        "round": state.round + 1,
        "analysis_run_id": None,
        "diagnosis_plan": None,
        "continuation_payload": {"decision": "continue"},
        "action_batch_id": None,
        "executed_nodes": [],
        "validated_action_count": 0,
        "executed_action_count": 0,
        "failed_action_count": 0,
        "suggestion_count": 0,
        "content_issue_count": 0,
        "structure_issue_count": 0,
        "structure_issue_summary": {},
        "evaluation_before_id": None,
        "evaluation_after_id": None,
        "verification_payload": None,
        "interrupt_type": None,
        "interrupt_id": None,
    }


def wait_continue_node(state: TaxonomyGraphState) -> StateUpdate:
    interrupt_id = f"continue:{state.workflow_id}:{state.round}"
    interrupt_payload = {
        "type": "continue_optimization",
        "interrupt_type": "continue_optimization",
        "interrupt_id": interrupt_id,
        "round": state.round,
        "max_rounds": state.max_rounds,
        "required_actions": ["continue", "finish"],
        "verification": state.verification_payload or {},
    }
    if state.task_id:
        TaskRepository(_runtime_settings).update_task(
            task_id=state.task_id,
            status="waiting_continue",
            current_step="continue_optimization",
            progress=99,
            interrupt_payload=interrupt_payload,
            interrupt_id=interrupt_id,
        )
    decision_payload = interrupt(interrupt_payload)
    updates = apply_continue_decision(
        state,
        decision=str(decision_payload.get("decision")),
    )
    return _complete_step(
        state,
        "wait_continue_node",
        current_step="continue_decided",
        progress=99,
        status="running",
        **updates,
    )


def wait_manual_intervention_node(state: TaxonomyGraphState) -> StateUpdate:
    update = {
        "status": "waiting_manual_intervention",
        "current_step": "manual_intervention",
        "progress": 99,
    }
    _record_progress(state, "wait_manual_intervention_node", update)
    return update


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
    plan.estimated_candidates = min(plan.estimated_candidates, 50)  # hard cap to prevent excessive API calls
    issues = ContentDiagnosisAgent(_runtime_settings).run(
        version_id,
        plan,
        workflow_id=state.workflow_id,
        analysis_run_id=state.analysis_run_id,
    )
    return _complete_step(
        state,
        "content_diagnosis_node",
        current_step="content_diagnosis",
        progress=68,
        content_issue_count=len(issues),
    )


def generate_suggestion_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    result = SuggestionAgent(_runtime_settings).run(
        version_id,
        workflow_id=state.workflow_id,
        analysis_run_id=state.analysis_run_id,
    )
    if result.generated_count == 0:
        return _complete_step(
            state,
            "generate_suggestion_node",
            current_step="generate_suggestion",
            progress=78,
            suggestion_count=0,
        )
    return _complete_step(
        state,
        "generate_suggestion_node",
        current_step="generate_suggestion",
        progress=78,
        suggestion_count=result.generated_count,
    )


def validate_action_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    results = ActionService(_runtime_settings).validate_automatic_actions(
        version_id,
        analysis_run_id=state.analysis_run_id,
        workflow_id=state.workflow_id,
    )
    failed = [item for item in results if not item.valid]
    if failed:
        message = "; ".join(item.reason for item in failed)
        raise WorkflowNodeError("ACTION_VALIDATION_FAILED", message)
    return _complete_step(
        state,
        "validate_action_node",
        current_step="validate_action",
        progress=86,
        validated_action_count=sum(1 for item in results if item.valid),
    )


def execute_action_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    result = ActionService(_runtime_settings).execute_validated_actions(
        version_id,
        operator="agent",
        workflow_id=state.workflow_id,
        analysis_run_id=state.analysis_run_id,
    )
    return _complete_step(
        state,
        "execute_action_node",
        current_step="execute_action",
        progress=91,
        executed_action_count=result.executed_count,
        failed_action_count=result.failed_count,
        action_batch_id=result.action_batch_id,
        executed_nodes=[node.model_dump() for node in result.nodes],
    )


def save_new_version_node(state: TaxonomyGraphState) -> StateUpdate:
    current_version_id = _require_current_version_id(state)
    nodes = None
    if state.executed_nodes:
        from backend.app.schemas.taxonomy import TaxonomyNodeRecord

        nodes = [TaxonomyNodeRecord.model_validate(item) for item in state.executed_nodes]
    result = VersionService(_runtime_settings).save_new_version(
        base_version_id=current_version_id,
        action_batch_id=_require_action_batch_id(state),
        workflow_id=state.workflow_id,
        analysis_run_id=state.analysis_run_id,
        nodes=nodes,
    )
    return _complete_step(
        state,
        "save_new_version_node",
        current_step="save_new_version",
        progress=96,
        new_version_id=result.new_version_id,
        result_version_id=result.new_version_id,
        current_version_id=result.new_version_id,
        version_no=result.new_version_no,
        node_count=result.node_count,
        executed_action_count=result.executed_count,
        failed_action_count=result.failed_count,
    )


def generate_report_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = state.current_version_id or state.base_version_id
    if version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Workflow requires version_id.")
    result = ReportService(_runtime_settings).generate_diagnosis_report(
        version_id,
        workflow_id=state.workflow_id if state.analysis_run_id else None,
        analysis_run_id=state.analysis_run_id,
        analyzed_version_id=state.base_version_id or version_id,
        result_version_id=state.result_version_id,
        verification=state.verification_payload,
    )
    return _complete_step(
        state,
        "generate_report_node",
        current_step="completed",
        progress=100,
        status="completed",
        report_id=version_id,
        report_path=str(result.report_path),
    )


def generate_degraded_report_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = state.current_version_id or state.base_version_id
    if version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Workflow requires version_id.")
    result = ReportService(_runtime_settings).generate_diagnosis_report(
        version_id,
        workflow_id=state.workflow_id if state.analysis_run_id else None,
        analysis_run_id=state.analysis_run_id,
        analyzed_version_id=state.base_version_id or version_id,
        result_version_id=state.result_version_id,
        verification=state.verification_payload,
    )
    return _complete_step(
        state,
        "generate_degraded_report_node",
        current_step="completed_degraded",
        progress=100,
        status="completed_degraded",
        report_id=version_id,
        report_path=str(result.report_path),
    )


def generate_failed_report_node(state: TaxonomyGraphState) -> StateUpdate:
    report_path = state.report_path
    version_id = state.current_version_id or state.base_version_id
    if version_id is not None:
        try:
            report_path = str(
                ReportService(_runtime_settings)
                .generate_diagnosis_report(
                    version_id,
                    workflow_id=state.workflow_id if state.analysis_run_id else None,
                    analysis_run_id=state.analysis_run_id,
                    analyzed_version_id=state.base_version_id or version_id,
                    result_version_id=state.result_version_id,
                    verification=state.verification_payload,
                )
                .report_path
            )
        except Exception:
            report_path = state.report_path
    update = {
        "status": "failed",
        "current_step": "failed",
        "report_path": report_path,
        "error_code": state.error_code or "WORKFLOW_FAILED",
        "error_message": state.error_message or "Workflow failed.",
    }
    _record_progress(state, "generate_failed_report_node", {**update, "progress": state.progress})
    return update


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
resolve_input_node = node_guard("resolve_input_node", resolve_input_node)
load_version_context_node = node_guard(
    "load_version_context_node", load_version_context_node
)
load_verification_context_node = node_guard(
    "load_verification_context_node", load_verification_context_node
)
create_analysis_run_node = node_guard(
    "create_analysis_run_node", create_analysis_run_node
)
build_tree_node = node_guard("build_tree_node", build_tree_node)
save_initial_version_node = node_guard(
    "save_initial_version_node",
    save_initial_version_node,
)
index_vector_node = node_guard("index_vector_node", index_vector_node)
index_result_version_node = node_guard(
    "index_result_version_node", index_result_version_node
)
index_verification_versions_node = node_guard(
    "index_verification_versions_node", index_verification_versions_node
)
structure_diagnosis_node = node_guard(
    "structure_diagnosis_node",
    structure_diagnosis_node,
)
baseline_quality_evaluation_node = node_guard(
    "baseline_quality_evaluation_node", baseline_quality_evaluation_node
)
result_quality_evaluation_node = node_guard(
    "result_quality_evaluation_node", result_quality_evaluation_node
)
verify_base_quality_evaluation_node = node_guard(
    "verify_base_quality_evaluation_node", verify_base_quality_evaluation_node
)
verify_result_quality_evaluation_node = node_guard(
    "verify_result_quality_evaluation_node", verify_result_quality_evaluation_node
)
verification_node = node_guard("verification_node", verification_node)
wait_continue_node = node_guard("wait_continue_node", wait_continue_node)
wait_manual_intervention_node = node_guard(
    "wait_manual_intervention_node", wait_manual_intervention_node
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
generate_degraded_report_node = node_guard(
    "generate_degraded_report_node", generate_degraded_report_node
)
generate_failed_report_node = node_guard(
    "generate_failed_report_node", generate_failed_report_node
)
