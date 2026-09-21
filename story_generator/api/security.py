import secrets

from fastapi import Header, HTTPException

from story_generator.config import get_api_access_key


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject requests that don't present the shared access key (single-user gate)."""
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), get_api_access_key().encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
