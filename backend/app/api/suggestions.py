from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.services.review_service import ReviewService
from backend.app.services.suggestion_service import SuggestionAgent

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


class GenerateSuggestionsRequest(BaseModel):
    version_id: int
    issue_ids: list[int] | None = None


class OperatorRequest(BaseModel):
    operator: str = "local_user"


class RejectSuggestionRequest(OperatorRequest):
    reject_reason: str | None = None


class EditSuggestionRequest(AdjustmentSuggestion):
    operator: str = "local_user"


class BatchApproveRequest(OperatorRequest):
    version_id: int
    suggestion_ids: list[int]


@router.post("/generate")
def generate_suggestions(payload: GenerateSuggestionsRequest, request: Request) -> dict[str, Any]:
    result = SuggestionAgent(request.app.state.settings).run(payload.version_id)
    return result.model_dump()


@router.get("")
def list_suggestions(
    request: Request,
    version_id: int | None = None,
    status: str | None = None,
    review_batch_id: str | None = None,
) -> list[dict[str, Any]]:
    suggestions = SuggestionRepository(request.app.state.settings).list_suggestions(
        version_id=version_id,
        status=status,
        review_batch_id=review_batch_id,
    )
    return [item.model_dump() for item in suggestions]


@router.get("/{suggestion_id}")
def get_suggestion(suggestion_id: int, request: Request) -> dict[str, Any]:
    suggestion = SuggestionRepository(request.app.state.settings).get_suggestion(suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found.")
    return suggestion.model_dump()


@router.post("/{suggestion_id}/approve")
def approve_suggestion(
    suggestion_id: int,
    payload: OperatorRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        suggestion = ReviewService(request.app.state.settings).approve_suggestion(
            suggestion_id,
            payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"suggestion_id": suggestion.id, "status": suggestion.status}


@router.post("/{suggestion_id}/reject")
def reject_suggestion(
    suggestion_id: int,
    payload: RejectSuggestionRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        suggestion = ReviewService(request.app.state.settings).reject_suggestion(
            suggestion_id,
            payload.operator,
            payload.reject_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"suggestion_id": suggestion.id, "status": suggestion.status}


@router.put("/{suggestion_id}")
def edit_suggestion(
    suggestion_id: int,
    payload: EditSuggestionRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        suggestion_data = payload.model_dump(exclude={"operator"})
        suggestion = ReviewService(request.app.state.settings).edit_suggestion(
            suggestion_id,
            AdjustmentSuggestion.model_validate(suggestion_data),
            payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return suggestion.model_dump()


@router.post("/batch-approve")
def batch_approve(payload: BatchApproveRequest, request: Request) -> dict[str, Any]:
    try:
        suggestions = ReviewService(request.app.state.settings).batch_approve(
            payload.suggestion_ids,
            payload.operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"approved_count": len(suggestions), "suggestion_ids": [item.id for item in suggestions]}
