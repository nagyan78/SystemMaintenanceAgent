from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app.services.review_service import ReviewService
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.services.action_simulation_service import ActionSimulationService

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewDecisionRequest(BaseModel):
    decision: str
    approved_suggestion_ids: list[int] = Field(default_factory=list)
    rejected_suggestion_ids: list[int] = Field(default_factory=list)
    edits: list[dict[str, Any]] = Field(default_factory=list)
    operator: str = "local_user"
    reject_reason: str | None = None


class ExecuteReviewRequest(BaseModel):
    operator: str = "local_user"


class PreviewReviewRequest(BaseModel):
    suggestion_ids: list[int] = Field(default_factory=list)


@router.get("/{review_batch_id}")
def get_review_batch(review_batch_id: str, request: Request) -> dict[str, Any]:
    suggestions = ReviewService(request.app.state.settings).list_review_batch(review_batch_id)
    if not suggestions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review batch not found.")
    return {
        "review_batch_id": review_batch_id,
        "suggestion_count": len(suggestions),
        "suggestions": [item.model_dump() for item in suggestions],
    }


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
    return {
        "review_batch_id": review_batch_id,
        "approved_count": approved_count,
        "status": "ok",
    }


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
