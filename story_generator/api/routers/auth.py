from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.api.rate_limit import login_rate_limit
from story_generator.api.security import SESSION_COOKIE_NAME, require_session_user
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.schemas import CurrentUserResponse, LoginRequest
from story_generator.auth.service import (
    AuthenticatedUser,
    AuthService,
    ClientInfo,
    InvalidCredentialsError,
)
from story_generator.config import get_session_cookie_secure

router = APIRouter(tags=["auth"])

# HttpOnly: page scripts can't read the token. SameSite=Lax: other sites'
# requests don't carry it; huaben.app and api.huaben.app count as the same
# site, so the frontend's requests do.
_COOKIE_FLAGS = {"httponly": True, "samesite": "lax", "path": "/"}


def _client_info(request: Request) -> ClientInfo:
    # The real caller's address in production, where FORWARDED_ALLOW_IPS
    # makes uvicorn trust Caddy's X-Forwarded-For (docker-compose.prod.yml).
    return ClientInfo(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post(
    "/auth/login",
    response_model=CurrentUserResponse,
    dependencies=[Depends(login_rate_limit)],
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    service = AuthService(AuthRepository(db))

    try:
        issued = service.login(
            payload.username, payload.password, _client_info(request)
        )
    except InvalidCredentialsError as exc:
        # Keep the record of the failed attempt: a failed login writes
        # nothing else, so this commits only that event.
        db.commit()
        raise HTTPException(
            status_code=401, detail="Incorrect username or password"
        ) from exc

    db.commit()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        issued.token,
        expires=issued.expires_at,
        secure=get_session_cookie_secure(),
        **_COOKIE_FLAGS,
    )
    return CurrentUserResponse(username=issued.username)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> None:
    if session_token:
        AuthService(AuthRepository(db)).logout(session_token, _client_info(request))
        db.commit()

    response.delete_cookie(
        SESSION_COOKIE_NAME, secure=get_session_cookie_secure(), **_COOKIE_FLAGS
    )


@router.get("/auth/me", response_model=CurrentUserResponse)
def current_user(
    user: AuthenticatedUser = Depends(require_session_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(username=user.username)
