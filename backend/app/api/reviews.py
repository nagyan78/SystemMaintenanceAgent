from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app.services.review_service import ReviewService
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.services.action_simulation_service import ActionSimulationService
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.services.execution_preview_service import ExecutionPreviewService
from backend.app.services.suggestion_consistency_service import SuggestionConsistencyService
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.tools.validation_tools import validate_suggestion_action
from backend.app.repositories.version_repo import VersionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.services.remediation_planning_service import RemediationPlanningService
from backend.app.repositories.operation_log_repo import OperationLogRepository
import json

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("")
def list_review_batches(
    request: Request,
    review_status: str | None = None,
    file_id: int | None = None,
) -> list[dict[str, Any]]:
    return ReviewBatchRepository(request.app.state.settings).list(
        status=review_status, file_id=file_id
    )


class ReviewDecisionRequest(BaseModel):
    decision: str
    approved_suggestion_ids: list[int] = Field(default_factory=list)
    rejected_suggestion_ids: list[int] = Field(default_factory=list)
    confirmed_without_action_suggestion_ids: list[int] = Field(default_factory=list)
    uncertain_suggestion_ids: list[int] = Field(default_factory=list)
    edits: list[dict[str, Any]] = Field(default_factory=list)
    operator: str = "local_user"
    reject_reason: str | None = None


class ExecuteReviewRequest(BaseModel):
    operator: str = "local_user"


class PreviewReviewRequest(BaseModel):
    suggestion_ids: list[int] = Field(default_factory=list)


class ManualSuggestionItem(BaseModel):
    issue_id: int | None = None
    action_type: str
    target_node_id: int | None = None
    target_node_name: str | None = None
    old_parent_id: int | None = None
    new_parent_id: int | None = None
    old_name: str | None = None
    new_name: str | None = None
    action_payload: dict[str, Any] = Field(default_factory=dict)
    reason: str
    suggestion: str
    risk_level: str = "medium"
    confidence: float = 1.0


class ManualSuggestionsRequest(BaseModel):
    suggestions: list[ManualSuggestionItem] = Field(min_length=1)


@router.get("/{review_batch_id}")
def get_review_batch(review_batch_id: str, request: Request) -> dict[str, Any]:
    batch = ReviewBatchRepository(request.app.state.settings).get(review_batch_id)
    suggestions = ReviewService(request.app.state.settings).list_review_batch(review_batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review batch not found.")
    diagnosis = DiagnosisRepository(request.app.state.settings)
    consistency = SuggestionConsistencyService(request.app.state.settings)
    consistency_results = [(item, consistency.check(item)) for item in suggestions]
    rendered = []
    type_stats: dict[str, dict[str, Any]] = {}
    incomplete_ids: list[int] = []
    for item, result in consistency_results:
        issue = diagnosis.get_issue_detail(item.issue_id)
        preview = item.change_preview or result.change_preview
        code = str((issue or {}).get("issue_type_code") or "unknown")
        incomplete = not _complete_preview(preview, issue_type_code=code, action_payload=item.action_payload)
        if incomplete:
            incomplete_ids.append(item.id)
        stats = type_stats.setdefault(code, {"issue_type_code": code,
            "issue_type_label": str((issue or {}).get("issue_type_label") or "其他"),
            "total": 0, "pending": 0, "approved": 0, "rejected": 0, "deferred": 0})
        stats["total"] += 1
        key = "pending" if item.status in {"pending", "edited"} else item.status
        if key in stats:
            stats[key] += 1
        rendered.append({**item.model_dump(), "issue": issue, "change_preview": preview,
                         "is_executable": bool(result.valid and result.executable),
                         "needs_manual_edit": bool(item.action_payload.get("needs_manual_edit")
                                                   or preview.get("details", {}).get("needs_manual_edit")),
                         "is_complete": not incomplete,
                         "before": preview.get("before") or {}, "after": preview.get("after") or {},
                         "action": preview.get("action") or {"type": item.action_type},
                         "impact_scope": preview.get("impact_scope") or preview.get("impact") or {}})
    invalid_suggestion_ids = [item.id for item, result in consistency_results
                              if not result.valid or item.consistency_status == "invalid"]
    legacy_warning = batch.get("batch_kind") in {"historical", "superseded"} or bool(incomplete_ids)
    batch_view = dict(batch)
    executable_approved_count = sum(
        1
        for item in rendered
        if item.get("status") == "approved" and item.get("is_executable")
    )
    if batch_view.get("status") != "executed" and int(batch_view.get("pending_count") or 0) == 0 and executable_approved_count == 0:
        batch_view["can_generate_preview"] = False
        batch_view["can_execute"] = False
        batch_view["blocked_reason"] = "当前没有可执行修改"
    stored_preview = None
    raw_preview = batch.get("preview_payload")
    if isinstance(raw_preview, str) and raw_preview.strip():
        try:
            stored_preview = json.loads(raw_preview)
        except json.JSONDecodeError:
            stored_preview = None
    return {
        "batch": batch_view,
        "review_batch_id": review_batch_id,
        "suggestion_count": len(suggestions),
        "suggestions": rendered,
        "type_stats": list(type_stats.values()),
        "incomplete_suggestion_ids": incomplete_ids,
        "invalid_suggestion_ids": invalid_suggestion_ids,
        "execution_preview": stored_preview,
        "legacy_warning": legacy_warning,
    }


@router.post("/{review_batch_id}/regenerate")
def regenerate_review_batch(review_batch_id: str, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    batches = ReviewBatchRepository(settings)
    source = batches.get(review_batch_id)
    if not source:
        raise HTTPException(status_code=404, detail="审核批次不存在。")
    old_suggestions = SuggestionRepository(settings).list_suggestions(review_batch_id=review_batch_id)
    planner = RemediationPlanningService(settings)
    consistency = SuggestionConsistencyService(settings)
    repo = SuggestionRepository(settings)
    audit = OperationLogRepository(settings)
    regenerated, reset_to_pending, unchanged = 0, 0, 0
    for current in old_suggestions:
        issue = DiagnosisRepository(settings).get_issue_detail(current.issue_id)
        if not issue:
            continue
        if _complete_preview(current.change_preview,
                             issue_type_code=str(issue.get("issue_type_code") or "unknown"),
                             action_payload=current.action_payload):
            continue
        suggestion = planner.plan(int(source["version_id"]), issue)
        if not suggestion:
            continue
        checked = consistency.check(suggestion, normalize_new=True)
        same_action = _action_fingerprint(current.action_type, current.action_payload) == _action_fingerprint(
            checked.suggestion.action_type, checked.suggestion.action_payload)
        preserve_status = current.status != "approved" or same_action
        repo.regenerate(current.id, suggestion=checked.suggestion, change_preview=checked.change_preview,
                        consistency_status="invalid" if checked.downgraded else "valid",
                        consistency_reason=checked.reason, preserve_status=preserve_status,
                        generator_version=RemediationPlanningService.GENERATOR_VERSION)
        audit.create_log(version_id=int(source["version_id"]), operator="local_user",
                         operation_type="regenerate_incomplete_suggestion",
                         operation_detail={"review_batch_id": review_batch_id, "suggestion_id": current.id,
                                           "issue_id": current.issue_id, "old": current.model_dump(mode="json"),
                                           "new": checked.suggestion.model_dump(mode="json"),
                                           "preserved_status": preserve_status})
        regenerated += 1
        if current.status == "approved" and not preserve_status:
            reset_to_pending += 1
        elif same_action:
            unchanged += 1
    batch = batches.refresh_status(review_batch_id)
    return {"source_review_batch_id": source.get("source_review_batch_id"), "review_batch_id": review_batch_id,
            "regenerated_count": regenerated, "reset_to_pending_count": reset_to_pending,
            "unchanged_action_count": unchanged, "batch": batch}


def _complete_preview(preview: dict[str, Any] | None, *, issue_type_code: str = "unknown",
                      action_payload: dict[str, Any] | None = None) -> bool:
    value = preview or {}
    if not all(key in value for key in ("before", "after", "action", "impact_scope")):
        return False
    payload = action_payload or {}
    if issue_type_code == "missing_parent" and value.get("action", {}).get("type") in {"review_only", "needs_manual_edit"}:
        return bool(payload.get("needs_manual_edit") and payload.get("missing_parent_id"))
    return True


def _action_fingerprint(action_type: str, payload: dict[str, Any]) -> str:
    keys = {
        "add_node": ("category_id", "parent_id", "new_name"),
        "rename_node": ("new_name",), "move_node": ("new_parent_id", "new_path"),
        "update_synonyms": ("synonyms_to_remove", "synonyms_to_add", "final_syn_list"),
        "split_subtree": ("groups",), "merge_node": ("source_node_id", "target_node_id"),
    }.get(action_type, tuple(sorted(payload)))
    return json.dumps({"action_type": action_type, **{key: payload.get(key) for key in keys}},
                      ensure_ascii=False, sort_keys=True)


@router.post("/{review_batch_id}/decision")
def apply_review_decision(
    review_batch_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        approved_count = ReviewService(request.app.state.settings).apply_workflow_decision(
            review_batch_id,
            payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    batch = ReviewBatchRepository(request.app.state.settings).refresh_status(review_batch_id)
    completion = None
    if batch.get("pending_count", 0) == 0 and batch.get("approved_count", 0) == 0:
        completion = ReviewService(request.app.state.settings).complete_without_execution(
            review_batch_id, operator=payload.operator,
        )
    return {
        "review_batch_id": review_batch_id,
        "approved_count": approved_count,
        "status": "ok",
        "batch": batch,
        "completion": completion,
    }


@router.post("/{review_batch_id}/auto-complete")
def auto_complete_review(
    review_batch_id: str,
    payload: ExecuteReviewRequest,
    request: Request,
) -> dict[str, Any]:
    """Complete review without manual editing: executable items pass, all others are ignored."""
    try:
        return ReviewService(request.app.state.settings).auto_complete_review(
            review_batch_id, payload.operator
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{review_batch_id}/execute")
def execute_review_batch(
    review_batch_id: str,
    payload: ExecuteReviewRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return ReviewService(request.app.state.settings).execute_approved_actions(
            review_batch_id,
            operator=payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{review_batch_id}/preview")
def preview_review_batch(review_batch_id: str, payload: PreviewReviewRequest, request: Request) -> dict[str, Any]:
    repo = SuggestionRepository(request.app.state.settings)
    batch = repo.list_suggestions(review_batch_id=review_batch_id)
    selected = [item for item in batch if not payload.suggestion_ids or item.id in payload.suggestion_ids]
    if not selected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No suggestions selected.")
    version_ids = {item.version_id for item in selected}
    if len(version_ids) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preview requires one base version.")
    preview = ActionSimulationService(request.app.state.settings).simulate(version_ids.pop(), selected)
    return preview.model_dump(exclude={"nodes"})


@router.post("/{review_batch_id}/execution-preview")
def create_execution_preview(review_batch_id: str, request: Request) -> dict[str, Any]:
    try:
        return ExecutionPreviewService(request.app.state.settings).create(review_batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{review_batch_id}/manual-suggestions")
def create_manual_suggestions(review_batch_id: str, payload: ManualSuggestionsRequest, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    batch = ReviewBatchRepository(settings).get(review_batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="审核批次不存在。")
    repo = SuggestionRepository(settings)
    consistency = SuggestionConsistencyService(settings)
    ids: list[int] = []
    for item in payload.suggestions:
        issue_id = item.issue_id
        if issue_id is None:
            node = TaxonomyRepository(settings).get_node_detail(int(batch["version_id"]), item.target_node_id) if item.target_node_id else None
            issue_type = {"rename_node": "naming_nonstandard", "update_synonyms": "synonym_format",
                          "move_node": "semantic_misplacement", "merge_node": "semantic_duplicate"}.get(item.action_type, "unknown")
            issue_id = DiagnosisRepository(settings).create_issue(
                version_id=int(batch["version_id"]),
                issue=DiagnosisIssueRecord(
                    issue_type=issue_type, node_id=item.target_node_id,
                    node_name=(node or {}).get("category_name") or item.target_node_name,
                    description=item.reason, reason=item.reason, risk_level=item.risk_level,
                    confidence=item.confidence, status="pending", path=(node or {}).get("path_names"),
                    evidence="人工创建修改", source="manual",
                ),
            )
        issue = DiagnosisRepository(settings).get_issue_detail(int(issue_id))
        if not issue or int(issue.get("version_id") or batch["version_id"]) != int(batch["version_id"]):
            raise HTTPException(status_code=400, detail="人工建议的问题不属于当前审核基线版本。")
        try:
            suggestion = AdjustmentSuggestion.model_validate({**item.model_dump(), "issue_id": issue_id, "version_id": int(batch["version_id"]),
                                                               "need_confirm": True, "status": "pending"})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"人工建议格式错误：{exc}") from exc
        checked = consistency.check(suggestion, normalize_new=True)
        validation = validate_suggestion_action(checked.suggestion, settings)
        if not validation.valid and checked.suggestion.action_type != "review_only":
            downgraded = checked.suggestion.model_copy(update={
                "action_type": "review_only",
                "action_payload": {"no_change_reason": validation.reason, "confirmation_required": checked.suggestion.suggestion},
                "suggestion": f"暂不执行修改：{validation.reason}",
            })
            checked = consistency.check(downgraded, normalize_new=True)
        suggestion_id = repo.create_suggestion(review_batch_id=review_batch_id, suggestion=checked.suggestion)
        repo.mark_manual(suggestion_id)
        repo.update_consistency(suggestion_id, suggestion=checked.suggestion, change_preview=checked.change_preview,
                                status="invalid" if checked.downgraded else "valid", reason=checked.reason)
        ids.append(suggestion_id)
    batch_repo = ReviewBatchRepository(settings)
    batch_repo.invalidate_preview(review_batch_id)
    batch = batch_repo.refresh_status(review_batch_id)
    return {"review_batch_id": review_batch_id, "created_count": len(ids), "suggestion_ids": ids, "batch": batch}
