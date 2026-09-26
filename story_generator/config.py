import os

from dotenv import load_dotenv

load_dotenv()


def get_skritter_access_token() -> str:
    token = os.getenv("SKRITTER_ACCESS_TOKEN")
    if token is None:
        raise RuntimeError(
            "SKRITTER_ACCESS_TOKEN environment variable is not set. "
            "Add it to your .env file."
        )
    return token


def get_openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if key is None:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set. Add it to your .env file."
        )
    return key


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o")


def get_openai_base_url() -> str:
    """
    Chat-completions endpoint. Defaults to OpenAI's real API, but can
    be pointed at any OpenAI-compatible endpoint (e.g. OpenRouter,
    Groq) for local development without touching provider code —
    they all implement the same request/response shape.
    """
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")


def get_openai_provider_label() -> str:
    """
    Human-readable label for which backend OPENAI_BASE_URL actually
    points at (e.g. "openai", "openrouter"). Purely descriptive —
    doesn't affect request behavior, only what gets recorded in
    StoryGenerationRequest.provider for accurate provenance.
    """
    return os.getenv("OPENAI_PROVIDER_LABEL", "openai")


def get_cors_allowed_origins() -> list[str]:
    """
    Comma-separated browser origins allowed to call this API
    (e.g. "http://localhost:3000,https://app.example.com"). Defaults
    to the local Next.js dev server.
    """
    raw = os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_api_access_key() -> str:
    """
    Shared secret every API request (except /health) must present in the
    X-API-Key header. Required: the API refuses to start without it so a
    production box can never silently run unauthenticated.
    """
    key = os.getenv("API_ACCESS_KEY")
    if not key:
        raise RuntimeError(
            "API_ACCESS_KEY environment variable is not set. Add it to your .env file."
        )
    return key


def get_api_docs_enabled() -> bool:
    """
    Whether to serve the interactive docs (/docs, /redoc) and the OpenAPI
    schema. Off unless ENABLE_API_DOCS=true: they are app-level routes the
    auth dependency doesn't cover, so turning them on shows every endpoint to
    anyone who can reach the API. For local development only; never set it
    in production.
    """
    return os.getenv("ENABLE_API_DOCS", "false").strip().lower() == "true"


def get_session_cookie_secure() -> bool:
    """
    Whether the login cookie is marked Secure (sent over HTTPS only). On by
    default; set SESSION_COOKIE_SECURE=false only for local development over
    plain http, if your browser won't keep a Secure cookie from localhost.
    """
    return os.getenv("SESSION_COOKIE_SECURE", "true").strip().lower() != "false"
