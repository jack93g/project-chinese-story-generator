from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.api.rate_limit import login_rate_limit
from story_generator.api.security import SESSION_COOKIE_NAME, require_session_user
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.schemas import CurrentUserResponse, LoginRequest
from story_generator.auth.service import (
    AuthenticatedUser,
    AuthService,
    InvalidCredentialsError,
)
from story_generator.config import get_session_cookie_secure

router = APIRouter(tags=["auth"])

# HttpOnly: page scripts can't read the token. SameSite=Lax: other sites'
# requests don't carry it; huaben.app and api.huaben.app count as the same
# site, so the frontend's requests do.
_COOKIE_FLAGS = {"httponly": True, "samesite": "lax", "path": "/"}


@router.post(
    "/auth/login",
    response_model=CurrentUserResponse,
    dependencies=[Depends(login_rate_limit)],
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    service = AuthService(AuthRepository(db))

    try:
        issued = service.login(payload.username, payload.password)
    except InvalidCredentialsError as exc:
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
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> None:
    if session_token:
        AuthService(AuthRepository(db)).logout(session_token)
        db.commit()

    response.delete_cookie(
        SESSION_COOKIE_NAME, secure=get_session_cookie_secure(), **_COOKIE_FLAGS
    )


@router.get("/auth/me", response_model=CurrentUserResponse)
def current_user(
    user: AuthenticatedUser = Depends(require_session_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(username=user.username)
