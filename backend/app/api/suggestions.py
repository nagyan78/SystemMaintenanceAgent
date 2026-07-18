from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.services.suggestion_service import SuggestionAgent

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


class GenerateSuggestionsRequest(BaseModel):
    version_id: int
    issue_ids: list[int] | None = None


@router.post("/generate")
def generate_suggestions(payload: GenerateSuggestionsRequest, request: Request) -> dict[str, Any]:
    result = SuggestionAgent(request.app.state.settings).run(payload.version_id)
    return result.model_dump()


@router.get("")
def list_suggestions(
    request: Request,
    version_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    suggestions = SuggestionRepository(request.app.state.settings).list_suggestions(
        version_id=version_id,
        status=status,
    )
    return [item.model_dump() for item in suggestions]


@router.get("/{suggestion_id}")
def get_suggestion(suggestion_id: int, request: Request) -> dict[str, Any]:
    suggestion = SuggestionRepository(request.app.state.settings).get_suggestion(suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found.")
    return suggestion.model_dump()
