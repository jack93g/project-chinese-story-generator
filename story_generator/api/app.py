from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from story_generator.api.routers.health import router as health_router
from story_generator.api.routers.stories import router as stories_router
from story_generator.api.routers.story_generations import (
    router as story_generations_router,
)
from story_generator.api.routers.sync_status import router as sync_status_router
from story_generator.api.routers.vocabulary import router as vocabulary_router
from story_generator.config import get_cors_allowed_origins


def create_app() -> FastAPI:
    app = FastAPI(
        title="Chinese Story Generator API",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_allowed_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(vocabulary_router)
    app.include_router(sync_status_router)
    app.include_router(stories_router)
    app.include_router(story_generations_router)

    return app
