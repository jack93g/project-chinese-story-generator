import secrets

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import AuthenticatedUser, AuthService
from story_generator.config import get_api_access_key, get_cors_allowed_origins

SESSION_COOKIE_NAME = "session"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Not logged in")


def _session_token_or_valid_api_key(
    x_api_key: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str | None:
    """
    First half of `require_auth`, deliberately free of any database access so
    a request with no credentials is rejected before a session is opened.
    Returns None for a valid API key, or the session token still to be checked.
    """
    if x_api_key is not None:
        if secrets.compare_digest(x_api_key.encode(), get_api_access_key().encode()):
            return None
        raise _unauthorized()
    if session_token:
        return session_token
    raise _unauthorized()


def _require_session_token(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    if not session_token:
        raise _unauthorized()
    return session_token


def _require_allowed_origin(request: Request) -> None:
    """
    Cross-site request forgery guard for cookie-authenticated writes. The
    SameSite=Lax cookie already stops other sites' requests carrying it;
    this also refuses writes from any origin not in CORS_ALLOWED_ORIGINS
    (e.g. another subdomain), in case the cookie rules ever loosen.
    """
    if request.method in _SAFE_METHODS:
        return
    if request.headers.get("origin") not in get_cors_allowed_origins():
        raise HTTPException(status_code=403, detail="Request origin not allowed")


def require_auth(
    request: Request,
    session_token: str | None = Depends(_session_token_or_valid_api_key),
    db: Session = Depends(get_db),
) -> None:
    """
    Gate for every protected route: accept either the shared X-API-Key
    (scripts, curl, operations) or a logged-in browser's session cookie.
    """
    if session_token is None:
        return
    _require_allowed_origin(request)
    if AuthService(AuthRepository(db)).authenticate(session_token) is None:
        raise _unauthorized()


def require_session_user(
    session_token: str = Depends(_require_session_token),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """The logged-in user. Session cookie only: an API key has no user."""
    user = AuthService(AuthRepository(db)).authenticate(session_token)
    if user is None:
        raise _unauthorized()
    return user
