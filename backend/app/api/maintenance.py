from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.services.maintenance_cleanup_service import MaintenanceCleanupService

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CleanupPreviewRequest(BaseModel):
    workflow_ids: list[str] = Field(default_factory=list)
    review_batch_ids: list[str] = Field(default_factory=list)
    file_ids: list[int] = Field(default_factory=list)
    failed_workflows: bool = False
    incomplete_workflows: bool = False
    all_business_data: bool = False
    force_cancel_running: bool = False


class CleanupExecuteRequest(BaseModel):
    cleanup_preview_id: str
    confirmation: str


@router.post("/cleanup/preview")
def preview_cleanup(payload: CleanupPreviewRequest, request: Request) -> dict[str, Any]:
    if not any((payload.workflow_ids, payload.review_batch_ids, payload.file_ids,
                payload.failed_workflows, payload.incomplete_workflows, payload.all_business_data)):
        raise HTTPException(status_code=400, detail="至少选择一种清理范围。")
    return MaintenanceCleanupService(request.app.state.settings).preview(payload.model_dump())


@router.post("/cleanup/execute")
def execute_cleanup(payload: CleanupExecuteRequest, request: Request) -> dict[str, Any]:
    try:
        return MaintenanceCleanupService(request.app.state.settings).execute(payload.cleanup_preview_id, payload.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
