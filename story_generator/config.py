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
            "OPENAI_API_KEY environment variable is not set. "
            "Add it to your .env file."
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