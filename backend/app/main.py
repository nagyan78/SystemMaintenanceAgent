from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import (
    chat,
    diagnosis,
    files,
    health,
    reviews,
    suggestions,
    taxonomy,
    versions,
    workflows,
)
from backend.app.config import Settings, get_settings
from backend.app.db import init_db


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.ensure_directories()
    init_db(app_settings)

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description="Local backend gateway for the taxonomy maintenance agent.",
    )
    app.state.settings = app_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(taxonomy.router, prefix="/api")
    app.include_router(diagnosis.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")
    app.include_router(reviews.router, prefix="/api")
    app.include_router(versions.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
