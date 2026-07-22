"""Thin LangGraph workflow nodes for the taxonomy maintenance MVP."""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings, get_settings
from backend.app.repositories.task_repo import TaskRepository
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.action_service import ActionService
from backend.app.services.content_diagnosis_service import (
    ContentDiagnosisAgent,
    DiagnosisPlanningAgent,
)
from backend.app.services.diagnosis_service import DiagnosisService
from backend.app.services.excel_service import ExcelService
from backend.app.services.report_service import ReportService
from backend.app.services.review_service import ReviewService
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.vector_index_service import VectorIndexService
from backend.app.services.version_service import VersionService
from backend.app.services.version_verification_service import VersionVerificationService
from backend.app.services.quality_score_service import calculate_composite_quality_score
from backend.app.services.ai_review_service import AIReviewService
from backend.app.services.adaptive_planning_service import AdaptivePlanningService
from backend.app.schemas.planning import DiagnosisBatchFeedback, MaintenancePlan
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.repositories.version_repo import VersionRepository


StateUpdate = dict[str, Any]
_workflow_settings: ContextVar[Settings | None] = ContextVar("workflow_settings", default=None)


class WorkflowNodeError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def bind_workflow_node(fn: Callable[[TaxonomyGraphState], StateUpdate], settings: Settings):
    """Bind settings to one node invocation without cross-workflow globals."""
    def bound(state: TaxonomyGraphState) -> StateUpdate:
        token = _workflow_settings.set(settings)
        try:
            return fn(state)
        finally:
            _workflow_settings.reset(token)
    return bound


def _current_settings() -> Settings:
    return _workflow_settings.get() or get_settings()


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
        if state.task_id:
            task = TaskRepository(_current_settings()).get_task(state.task_id)
            if task and task.get("status") == "cancelled":
                return {"status": "cancelled", "current_step": "cancelled"}
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
    result = ExcelService(_current_settings()).parse_uploaded_file(file_id)
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
    result = TaxonomyService(_current_settings()).build_tree(_require_file_id(state))
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
    result = VersionService(_current_settings()).create_initial_version(_require_file_id(state))
    VersionRepository(_current_settings()).update_model_metadata(
        result.version_id,
        diagnosis_mode="ai_enhanced" if state.enable_ai_analysis else "deterministic_rules",
        diagnosis_model=state.model_name if state.enable_ai_analysis else None,
    )
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
    if not state.enable_ai_analysis:
        return _complete_step(
            state,
            "index_vector_node",
            current_step="index_vector_skipped",
            progress=40,
            vector_index_status="skipped",
            vector_index_count=0,
        )
    result = VectorIndexService(_current_settings()).index_version(
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
    result = DiagnosisService(_current_settings()).run_structure_diagnosis(
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
    if state.enable_ai_analysis:
        maintenance = AdaptivePlanningService().create(workflow_id=state.workflow_id, version_id=version_id, candidate_budget=20)
        plan = DiagnosisPlan(
            priority_subtree_ids=state.priority_subtree_ids,
            sample_strategy=state.sample_strategy,
            focus_issues=state.focus_issues,
            estimated_candidates=state.ai_candidate_limit or sum(item.candidate_budget for item in maintenance.targets),
        )
        maintenance = maintenance.model_copy(update={
            "strategy": "full_screening" if state.sample_strategy == "full_scan" else state.sample_strategy,
            "max_model_calls": state.ai_max_model_calls or maintenance.max_model_calls,
            "max_tokens": state.ai_token_budget or maintenance.max_tokens,
            "max_wall_seconds": state.ai_wall_seconds or maintenance.max_wall_seconds,
        })
    else:
        maintenance = None
        plan = DiagnosisPlan(sample_strategy="focused", estimated_candidates=0)
    return _complete_step(
        state,
        "diagnosis_planning_node",
        current_step="diagnosis_planning",
        progress=62,
        diagnosis_plan=plan.model_dump(),
        maintenance_plan=maintenance.model_dump() if maintenance else None,
        plan_revision=maintenance.revision if maintenance else 1,
    )


def content_diagnosis_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    plan = DiagnosisPlan.model_validate(state.diagnosis_plan or {})
    plan.estimated_candidates = min(plan.estimated_candidates, 50)  # hard cap to prevent excessive API calls
    rule_issue_count = DiagnosisService(_current_settings()).run_content_rule_diagnosis(version_id)
    if state.enable_ai_analysis:
        from backend.app.agents.content_diagnosis_subgraph import build_content_diagnosis_subgraph
        subgraph_result = build_content_diagnosis_subgraph(settings=_current_settings()).invoke(
            {"workflow_id": state.workflow_id, "version_id": version_id, "plan": plan.model_dump(),
             "rule_scanned_nodes": state.node_count, "rule_issue_count": state.structure_issue_count + rule_issue_count,
             "budget": {
                 "max_model_calls": state.ai_max_model_calls or _current_settings().llm_max_calls,
                 "max_tokens": state.ai_token_budget or _current_settings().llm_max_tokens,
                 "max_wall_seconds": state.ai_wall_seconds or _current_settings().diagnosis_ai_wall_seconds,
             }},
            config={"max_concurrency": _current_settings().agent_llm_max_concurrency},
        )
        issues_count = rule_issue_count + int(subgraph_result.get("issue_count", 0))
        analysis_run_id = subgraph_result.get("run_id")
        work_item_counts = subgraph_result.get("work_item_counts", {})
        coverage = subgraph_result.get("coverage", {})
        if analysis_run_id:
            DiagnosisRepository(_current_settings()).link_run_issues(
                run_id=str(analysis_run_id), version_id=version_id,
            )
    else:
        issues_count, analysis_run_id, work_item_counts = rule_issue_count, None, {}
        coverage = {
            "total_nodes": state.node_count, "rule_scanned_nodes": state.node_count,
            "rule_issue_count": state.structure_issue_count + rule_issue_count,
            "candidate_count": 0, "deep_diagnosed_count": 0, "ai_issue_count": 0,
            "skipped_count": 0, "failed_count": 0, "unexamined_reasons": {},
            "model_calls": 0, "tokens_used": 0, "wall_seconds": 0,
            "plan_revision": state.plan_revision, "stop_reason": "规则模式未生成 AI 修改方案",
            "rules_complete": True, "ai_complete": False, "coverage_complete": False,
            "completion_status": "partial", "run_id": None,
            "workflow_id": state.workflow_id, "plan": plan.model_dump(),
        }
    triage_count = 0
    all_issues = DiagnosisRepository(_current_settings()).list_issues(version_id)
    composite = calculate_composite_quality_score(
        state.node_count,
        all_issues,
        ai_content_sample_score=coverage.get("ai_content_sample_score") if coverage.get("ai_complete") else None,
    )
    VersionRepository(_current_settings()).update_quality_score(version_id, composite.overall_quality_score)
    plan_update = {}
    if state.maintenance_plan:
        maintenance = MaintenancePlan.model_validate(state.maintenance_plan)
        processed = sum(int(work_item_counts.get(key, 0)) for key in ("succeeded", "clean", "inconclusive", "permanent_failed"))
        feedback = DiagnosisBatchFeedback(batch_id=analysis_run_id or "rules", plan_revision=maintenance.revision, processed=processed, issues=issues_count, clean=int(work_item_counts.get("clean",0)), inconclusive=int(work_item_counts.get("inconclusive",0)), failed=int(work_item_counts.get("permanent_failed",0)), model_calls=int(coverage.get("model_calls", processed)), tokens=int(coverage.get("tokens_used", 0)), wall_seconds=float(coverage.get("wall_seconds", 0)))
        revised = AdaptivePlanningService().revise(maintenance, feedback)
        plan_update = {"maintenance_plan": revised.model_dump(), "plan_revision": revised.revision, "plan_decision": revised.decision, "stop_reason": revised.stop_reason, "model_calls_used": feedback.model_calls, "tokens_used": feedback.tokens, "wall_seconds_used": feedback.wall_seconds}
    return _complete_step(
        state,
        "content_diagnosis_node",
        current_step="content_diagnosis",
        progress=68,
        content_issue_count=issues_count,
        analysis_run_id=analysis_run_id,
        work_item_counts=work_item_counts,
        coverage=coverage,
        diagnosis_completion_status=str(coverage.get("completion_status") or "completed"),
        triage_count=triage_count,
        **plan_update,
    )


def generate_suggestion_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    from backend.app.agents.suggestion_subgraph import build_suggestion_subgraph
    # Keep delivery predictable and cheap: AI diagnoses content, while the
    # mutation path accepts deterministic low-risk repairs only.
    result = build_suggestion_subgraph(settings=_current_settings(), llm=None).invoke(
        {"workflow_id": state.workflow_id, "version_id": version_id, "analysis_run_id": state.analysis_run_id},
        config={"max_concurrency": _current_settings().agent_llm_max_concurrency},
    )
    generated_count = int(result.get("suggestion_count", 0))
    review_batch_id = result.get("review_batch_id")
    suggestion_work_counts = result.get("work_item_counts", {})
    if generated_count == 0:
        return _complete_step(
            state,
            "generate_suggestion_node",
            current_step="generate_suggestion",
            progress=78,
            suggestion_count=0,
            suggestion_work_item_counts=suggestion_work_counts,
        )
    version = VersionRepository(_current_settings()).get_version(version_id)
    if review_batch_id and version:
        batch_repo = ReviewBatchRepository(_current_settings())
        batch_repo.create(
            batch_id=str(review_batch_id), file_id=int(version["file_id"]),
            version_id=version_id, task_id=state.task_id, workflow_id=state.workflow_id,
        )
        batch_repo.refresh_status(str(review_batch_id))
    approval = ReviewService(_current_settings()).auto_complete_review(
        str(review_batch_id),
        operator="deterministic_auto_apply",
        complete_if_empty=False,
    )
    approved_ids = [int(item) for item in approval.get("approved_ids", [])]
    return _complete_step(
        state,
        "generate_suggestion_node",
        current_step="generate_suggestion",
        progress=78,
        suggestion_count=generated_count,
        review_batch_id=review_batch_id,
        suggestion_work_item_counts=suggestion_work_counts,
        review_decision="approve" if approved_ids else "uncertain",
        review_payload={
            "mode": "deterministic_low_risk",
            "approved_suggestion_ids": approved_ids,
            "ignored_suggestion_ids": approval.get("ignored_ids", []),
        },
        approved_action_count=len(approved_ids),
    )


def ai_review_action_node(state: TaxonomyGraphState) -> StateUpdate:
    """Run an independent AI judgment, then the deterministic execution gate."""
    review_batch_id = _require_review_batch_id(state)
    review_service = ReviewService(_current_settings())
    suggestions = review_service.list_review_batch(review_batch_id)
    from backend.app.services.model_service import ModelService
    ai_review = AIReviewService(ModelService(_current_settings()).get_chat_model()).review(suggestions)
    ai_approved_ids = {
        int(item["suggestion_id"])
        for item in ai_review.decisions
        if ai_review.completed and item.get("verdict") == "approve"
    }
    result = review_service.auto_complete_review(
        review_batch_id,
        operator="ai_reviewer",
        complete_if_empty=False,
        approved_suggestion_ids=ai_approved_ids,
    )
    approved_ids = [int(item) for item in result.get("approved_ids", [])]
    ignored_ids = [int(item) for item in result.get("ignored_ids", [])]
    return _complete_step(
        state,
        "ai_review_action_node",
        current_step="ai_review",
        progress=82,
        status="running",
        review_decision="approve" if approved_ids else "uncertain",
        review_payload={
            "mode": "ai_auto_review",
            "ai_review_completed": ai_review.completed,
            "ai_review_decisions": ai_review.decisions,
            "ai_review_warning": ai_review.warning,
            "approved_suggestion_ids": approved_ids,
            "ignored_suggestion_ids": ignored_ids,
        },
        approved_action_count=len(approved_ids),
        # Suggestion rejection means "diagnosis completed, no safe action"; it
        # must not downgrade completed diagnostic coverage to a partial report.
        diagnosis_completion_status=state.diagnosis_completion_status,
    )


def validate_action_node(state: TaxonomyGraphState) -> StateUpdate:
    review_batch_id = _require_review_batch_id(state)
    results = ActionService(_current_settings()).validate_approved_actions(review_batch_id)
    failed = [item for item in results if not item.valid]
    if failed:
        message = "; ".join(item.reason for item in failed)
        raise WorkflowNodeError("ACTION_VALIDATION_FAILED", message)
    return _complete_step(
        state,
        "validate_action_node",
        current_step="validate_action",
        progress=86,
    )


def execute_action_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = _require_current_version_id(state)
    review_batch_id = _require_review_batch_id(state)
    result = ActionService(_current_settings()).execute_actions(version_id, review_batch_id)
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
    review_batch_id = _require_review_batch_id(state)
    nodes = None
    if state.executed_nodes:
        from backend.app.schemas.taxonomy import TaxonomyNodeRecord

        nodes = [TaxonomyNodeRecord.model_validate(item) for item in state.executed_nodes]
    result = VersionService(_current_settings()).save_new_version(
        base_version_id=current_version_id,
        review_batch_id=review_batch_id,
        nodes=nodes,
        action_batch_id=state.action_batch_id,
        source_workflow_id=state.workflow_id,
    )
    return _complete_step(
        state,
        "save_new_version_node",
        current_step="save_new_version",
        progress=96,
        new_version_id=result.new_version_id,
        current_version_id=result.new_version_id,
        version_no=result.new_version_no,
        node_count=result.node_count,
        executed_action_count=result.executed_count,
        failed_action_count=result.failed_count,
    )


def deterministic_optimize_node(state: TaxonomyGraphState) -> StateUpdate:
    base_version_id = state.base_version_id or _require_current_version_id(state)
    result = VersionService(_current_settings()).create_deterministic_optimized_version(
        base_version_id=base_version_id,
        source_workflow_id=state.workflow_id,
    )
    return _complete_step(
        state,
        "deterministic_optimize_node",
        current_step="save_new_version",
        progress=96,
        new_version_id=result.new_version_id,
        current_version_id=result.new_version_id,
        version_no=result.new_version_no,
        node_count=result.node_count,
        executed_action_count=result.executed_count,
        failed_action_count=result.failed_count,
        action_batch_id=result.action_batch_id,
        review_payload={
            **(state.review_payload or {}),
            "delivery_fallback": "deterministic_synonym_cleanup",
            "changed_node_count": result.executed_count,
        },
    )


def verify_new_version_node(state: TaxonomyGraphState) -> StateUpdate:
    if state.base_version_id is None or state.new_version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Version verification requires old and new versions.")
    result = VersionVerificationService(_current_settings()).verify(
        base_version_id=state.base_version_id,
        new_version_id=state.new_version_id,
        build_vector_index=state.enable_ai_analysis,
    )
    if state.analysis_run_id:
        DiagnosisRepository(_current_settings()).link_run_issues(
            run_id=state.analysis_run_id,
            version_id=state.new_version_id,
        )
    return _complete_step(
        state,
        "verify_new_version_node",
        current_step="verify_new_version",
        progress=98,
        verification_status=result.status,
        quality_before=result.quality_before,
        quality_after=result.quality_after,
        quality_delta=result.quality_delta,
        remaining_issue_count=result.remaining_issue_count,
        vector_index_status=result.vector_index_status,
        export_path=result.export_path,
    )


def generate_report_node(state: TaxonomyGraphState) -> StateUpdate:
    version_id = state.current_version_id or state.base_version_id
    if version_id is None:
        raise WorkflowNodeError("MISSING_VERSION_ID", "Workflow requires version_id.")
    is_draft = (
        state.review_batch_id is not None
        and state.new_version_id is None
        and state.review_decision is None
    )
    report_type = "final"
    reports = ReportService(_current_settings())
    baseline_id = state.base_version_id or version_id
    baseline = reports.generate_diagnosis_report(
        baseline_id,
        report_type=report_type,
        workflow_id=state.workflow_id,
        run_id=state.analysis_run_id,
    )
    result = baseline
    if state.new_version_id is not None and state.new_version_id != baseline_id:
        result = reports.generate_optimization_report(
            base_version_id=baseline_id,
            new_version_id=state.new_version_id,
            workflow_id=state.workflow_id,
            run_id=state.analysis_run_id,
            review_batch_id=state.review_batch_id,
        )
    return _complete_step(
        state,
        "generate_report_node",
        current_step="review_pending" if is_draft else "completed",
        progress=80 if is_draft else 100,
        status="waiting_review" if is_draft else ("partial" if report_type == "partial" else "completed"),
        report_id=version_id,
        report_path=str(result.report_path),
        report_type=report_type,
    )


def _record_progress(
    state: TaxonomyGraphState,
    node_name: str,
    update: StateUpdate,
) -> None:
    if not state.task_id:
        return
    version_id = update.get("current_version_id") or state.current_version_id
    task_repo = TaskRepository(_current_settings())
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
    TaskRepository(_current_settings()).record_event(
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
deterministic_optimize_node = node_guard("deterministic_optimize_node", deterministic_optimize_node)
validate_action_node = node_guard("validate_action_node", validate_action_node)
execute_action_node = node_guard("execute_action_node", execute_action_node)
save_new_version_node = node_guard("save_new_version_node", save_new_version_node)
verify_new_version_node = node_guard("verify_new_version_node", verify_new_version_node)
generate_report_node = node_guard("generate_report_node", generate_report_node)
