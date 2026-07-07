from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from backend.app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


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
