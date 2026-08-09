from fastapi import FastAPI

from story_generator.api.routers.health import router as health_router
from story_generator.api.routers.vocabulary import router as vocabulary_router
from story_generator.api.routers.sync_status import router as sync_status_router
from story_generator.api.routers.stories import router as stories_router
from story_generator.api.routers.generation import router as generation_router

from story_generator.api.routers import health, stories, sync_status, vocabulary



def create_app() -> FastAPI:
    app = FastAPI(
        title="Chinese Story Generator API",
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(vocabulary_router)
    app.include_router(sync_status_router)
    app.include_router(stories_router)
    app.include_router(generation_router)
    

    return app