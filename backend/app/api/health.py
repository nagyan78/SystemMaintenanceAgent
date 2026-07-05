from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "app": request.app.state.settings.app_name,
    }

