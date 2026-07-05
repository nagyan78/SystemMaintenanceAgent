from fastapi import APIRouter

from backend.app.api._placeholder import not_implemented

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
def chat_with_taxonomy() -> None:
    not_implemented("chat", "chat")


@router.get("/history")
def get_chat_history() -> None:
    not_implemented("chat", "history")

