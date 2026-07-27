from fastapi import FastAPI

from story_generator.api.routers.health import router as health_router
from story_generator.api.routers.vocabulary import router as vocabulary_router
from story_generator.api.routers.sync_status import router as sync_status_router



def create_app() -> FastAPI:
    app = FastAPI(
        title="Chinese Story Generator API",
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(vocabulary_router)
    app.include_router(sync_status_router)

    return app