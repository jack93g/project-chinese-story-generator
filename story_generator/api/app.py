from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the HTTP application without performing external work."""
    app = FastAPI(
        title="Chinese Story Generator API",
        version="0.1.0",
    )

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app
