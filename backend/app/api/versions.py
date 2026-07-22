from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from uuid import uuid4

from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.version import ExportResult
from backend.app.services.version_service import VersionService
from backend.app.tools.export_tools import export_excel
from backend.app.repositories.version_repo import VersionRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.db import connect
from backend.app.services.report_service import ReportService
from backend.app.services.review_service import ReviewService
from backend.app.services.execution_preview_service import ExecutionPreviewService

router = APIRouter(prefix="/versions", tags=["versions"])


class CreateVersionReviewBatchRequest(BaseModel):
    issue_ids: list[int] = Field(default_factory=list)


class RestoreVersionRequest(BaseModel):
    supersedes_version_id: int | None = None
    operator: str = "local_user"


@router.get("")
def list_versions(
    request: Request,
    file_id: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    return VersionService(request.app.state.settings).list_versions(file_id=file_id)


@router.get("/{version_id}")
def get_version(version_id: int, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    version = VersionService(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    node_count = TaxonomyRepository(settings).count_nodes(version_id)
    return {**version, "node_count": node_count}


@router.get("/{version_id}/quality")
def get_version_quality(version_id: int, request: Request) -> dict[str, Any]:
    versions = VersionRepository(request.app.state.settings)
    current = versions.get_version(version_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    issues = DiagnosisRepository(request.app.state.settings)
    current_issues = issues.list_issues(version_id)
    parent_id = current.get("parent_version_id")
    parent = versions.get_version(int(parent_id)) if parent_id else None
    parent_issues = issues.list_issues(int(parent_id)) if parent_id else []
    identity = lambda item: (item.get("issue_type_code"), item.get("node_id"))
    parent_keys = {identity(item) for item in parent_issues}
    current_keys = {identity(item) for item in current_issues}
    resolved = [item for item in parent_issues if identity(item) not in current_keys or item.get("status") == "resolved"]
    unresolved = [item for item in current_issues if identity(item) in parent_keys and item.get("status") not in {"false_positive", "resolved"}]
    added = [item for item in current_issues if identity(item) not in parent_keys]
    deferred = [item for item in current_issues if item.get("status") == "deferred"]
    false_positive = [item for item in current_issues if item.get("status") == "false_positive"]
    before_count = len(parent_issues) if parent else len(current_issues)
    after_count = len(current_issues)
    improvement_rate = round((before_count - after_count) * 100 / before_count, 1) if before_count else 0.0
    return {"version_id": version_id, "version_no": current["version_no"],
        "parent_version_id": parent_id, "before_issue_count": before_count,
        "after_issue_count": after_count, "quality_before": parent.get("quality_score") if parent else current.get("quality_score"),
        "quality_after": current.get("quality_score"), "improvement_rate": improvement_rate,
        "remaining_issues": current_issues, "resolved_issues": resolved, "unresolved_issues": unresolved,
        "new_issues": added, "deferred_issues": deferred, "false_positive_issues": false_positive,
        "verification_status": current.get("verification_status"), "lifecycle_status": current.get("lifecycle_status"),
        "release_allowed": current.get("lifecycle_status") == "passed"}


@router.get("/{version_id}/diff")
def get_version_diff(
    version_id: int,
    request: Request,
    target_version_id: int = Query(...),
) -> dict[str, Any]:
    service = VersionService(request.app.state.settings)
    if service.get_version(version_id) is None or service.get_version(target_version_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return service.get_version_diff(version_id, target_version_id).model_dump()


@router.post("/{version_id}/rollback")
def rollback_version(version_id: int, request: Request) -> dict[str, Any]:
    try:
        return VersionService(request.app.state.settings).rollback_version(version_id).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{version_id}/restore")
def restore_version(version_id: int, payload: RestoreVersionRequest, request: Request) -> dict[str, Any]:
    try:
        return VersionService(request.app.state.settings).rollback_version(
            version_id, operator=payload.operator, supersedes_version_id=payload.supersedes_version_id
        ).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{version_id}/review-batches")
def create_version_review_batch(version_id: int, payload: CreateVersionReviewBatchRequest, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    version = VersionRepository(settings).get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found.")
    available = {int(item["id"]) for item in DiagnosisRepository(settings).list_issues(version_id)}
    if not set(payload.issue_ids).issubset(available):
        raise HTTPException(status_code=400, detail="选择的问题不属于当前版本。")
    batch_id = f"review_{uuid4().hex[:12]}"
    ReviewBatchRepository(settings).create(batch_id=batch_id, file_id=int(version["file_id"]), version_id=version_id)
    result = SuggestionAgent(settings, enable_ai=False, review_batch_id=batch_id).run(version_id, issue_ids=payload.issue_ids)
    batch = ReviewBatchRepository(settings).refresh_status(batch_id)
    return {"review_batch_id": batch_id, "suggestion_count": result.generated_count, "batch": batch}


@router.post("/{version_id}/apply-fixes")
def apply_version_fixes(version_id: int, request: Request) -> dict[str, Any]:
    """Apply generated fixes immediately and create the next version."""
    settings = request.app.state.settings
    version = VersionRepository(settings).get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found.")

    pending = DiagnosisRepository(settings).list_pending_issues(version_id)
    if not pending:
        raise HTTPException(status_code=400, detail="当前版本没有可修改的问题。")
    pending.sort(key=lambda item: (
        0 if str(item.get("issue_type_code") or item.get("issue_type")) in {
            "synonym_format", "synonym_format_issue", "missing_parent"
        } else 1,
        int(item["id"]),
    ))
    issue_ids = [int(item["id"]) for item in pending[:50]]
    batch_id = f"quick_apply_{uuid4().hex[:12]}"
    ReviewBatchRepository(settings).create(
        batch_id=batch_id,
        file_id=int(version["file_id"]),
        version_id=version_id,
    )
    generated = SuggestionAgent(
        settings,
        enable_ai=False,
        review_batch_id=batch_id,
    ).run(version_id, issue_ids=issue_ids)
    if generated.generated_count == 0:
        raise HTTPException(status_code=400, detail="没有生成可执行修改。")

    review = ReviewService(settings)
    approved = review.auto_complete_review(
        batch_id,
        operator="quick_apply",
        complete_if_empty=False,
    )
    if not approved.get("approved_ids"):
        raise HTTPException(status_code=400, detail="生成的修改无法执行。")
    ExecutionPreviewService(settings).create(batch_id)
    result = review.execute_approved_actions(batch_id, operator="quick_apply")
    new_version_id = int(result["new_version_id"])
    export_path = export_excel(new_version_id, settings)
    new_version = VersionRepository(settings).get_version(new_version_id) or {}
    VersionRepository(settings).update_verification(
        new_version_id,
        status=str(new_version.get("verification_status") or "passed"),
        export_path=str(export_path),
    )
    return {
        **result,
        "file_name": export_path.name,
        "export_path": str(export_path),
        "download_url": f"/api/downloads/exports/{export_path.name}",
    }


@router.post("/{version_id}/release")
def release_version(version_id: int, request: Request) -> dict[str, Any]:
    try:
        settings = request.app.state.settings
        VersionRepository(settings).release(version_id)
        with connect(settings) as connection:
            batch = connection.execute("SELECT id FROM review_batch WHERE new_version_id=? ORDER BY created_time DESC LIMIT 1", (version_id,)).fetchone()
            artifact = connection.execute("SELECT id FROM report_artifact WHERE version_id=? AND report_type='final'", (version_id,)).fetchone()
        if artifact:
            ReportService(settings).generate_diagnosis_report(version_id, report_type="final", review_batch_id=str(batch["id"]) if batch else None)
        return VersionRepository(settings).get_version(version_id) or {}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{version_id}/execution-records")
def list_execution_records(version_id: int, request: Request) -> list[dict[str, Any]]:
    with connect(request.app.state.settings) as connection:
        rows = connection.execute(
            """SELECT * FROM version_execution_record WHERE source_version_id=? OR target_version_id=? ORDER BY id DESC""",
            (version_id, version_id),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/{version_id}/export")
def export_version(version_id: int, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    version = VersionService(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    try:
        export_path = export_excel(version_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    VersionRepository(settings).update_verification(
        version_id,
        status=str(version.get("verification_status") or "not_verified"),
        export_path=str(export_path),
    )
    return ExportResult(
        version_id=version_id,
        version_no=str(version["version_no"]),
        file_name=export_path.name,
        export_path=str(export_path),
        download_url=f"/api/downloads/exports/{export_path.name}",
    ).model_dump()
