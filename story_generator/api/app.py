from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from story_generator.api.routers.auth import router as auth_router
from story_generator.api.routers.health import router as health_router
from story_generator.api.routers.stories import router as stories_router
from story_generator.api.routers.story_generations import (
    router as story_generations_router,
)
from story_generator.api.routers.sync_status import router as sync_status_router
from story_generator.api.routers.vocabulary import router as vocabulary_router
from story_generator.api.security import require_auth
from story_generator.config import get_api_access_key, get_cors_allowed_origins


def create_app() -> FastAPI:
    # Fail fast at startup if the access key is missing.
    get_api_access_key()

    # Interactive docs and the OpenAPI schema are app-level routes that the
    # auth dependency doesn't cover, so they're disabled rather than left
    # public.
    app = FastAPI(
        title="Chinese Story Generator API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_allowed_origins(),
        # Lets the browser send the login cookie cross-origin (huaben.app →
        # api.huaben.app). Safe only because allow_origins is an explicit list.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    app.include_router(health_router)
    # Login/logout must be reachable without being logged in; /auth/me checks
    # the session itself.
    app.include_router(auth_router)
    # Router-level dependencies run before route-level ones, so the auth check
    # comes before the generation rate limiter: an unauthenticated caller must
    # never be able to use up the owner's rate-limit budget. Keep it that way.
    protected = [Depends(require_auth)]
    app.include_router(vocabulary_router, dependencies=protected)
    app.include_router(sync_status_router, dependencies=protected)
    app.include_router(stories_router, dependencies=protected)
    app.include_router(story_generations_router, dependencies=protected)

    return app
