from fastapi import APIRouter

from backend.app.api._placeholder import not_implemented

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.post("/generate")
def generate_suggestions() -> None:
    not_implemented("suggestions", "generate")


@router.get("")
def list_suggestions() -> None:
    not_implemented("suggestions", "list")


@router.post("/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: int) -> None:
    not_implemented("suggestions", f"approve:{suggestion_id}")


@router.post("/{suggestion_id}/reject")
def reject_suggestion(suggestion_id: int) -> None:
    not_implemented("suggestions", f"reject:{suggestion_id}")


@router.post("/execute")
def execute_suggestions() -> None:
    not_implemented("suggestions", "execute")

