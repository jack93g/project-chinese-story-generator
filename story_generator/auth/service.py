import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from story_generator.auth.persistence.models import AuthEvent, AuthSession, User
from story_generator.auth.persistence.repository import AuthRepository

SESSION_LIFETIME = timedelta(days=30)
MIN_PASSWORD_LENGTH = 12
MAX_USERNAME_LENGTH = 150
# Auth events hold client IPs, which are personal data: keep them for a fixed
# period only. `manage-logins purge`, run daily by cron, deletes older rows.
AUTH_EVENT_RETENTION = timedelta(days=90)
MAX_USER_AGENT_LENGTH = 512

_hasher = PasswordHasher()


@cache
def _dummy_hash() -> str:
    # Verified against when the username doesn't exist, so a login attempt
    # takes about as long whether or not the account is real.
    return _hasher.hash("not-a-real-password")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthEventType(StrEnum):
    # Mirrored by auth_events_event_type_check (AuthEvent's model and its
    # migration): a new member needs a migration widening that constraint.
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_WRONG_PASSWORD = "login_wrong_password"
    LOGIN_UNKNOWN_USER = "login_unknown_user"
    LOGOUT = "logout"


FAILED_LOGIN_EVENTS = (
    AuthEventType.LOGIN_WRONG_PASSWORD,
    AuthEventType.LOGIN_UNKNOWN_USER,
)


class InvalidCredentialsError(Exception):
    """Raised for an unknown username and a wrong password alike, so callers
    can't tell them apart. The failed attempt has already been recorded as an
    auth event: commit the session to keep it."""

    def __init__(self):
        super().__init__("Invalid username or password")


class InvalidUsernameError(Exception):
    def __init__(self):
        super().__init__(
            f"Username must be 1 to {MAX_USERNAME_LENGTH} characters, "
            "not counting surrounding spaces"
        )


class PasswordTooShortError(Exception):
    def __init__(self):
        super().__init__(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )


class UsernameTakenError(Exception):
    def __init__(self, username: str):
        self.username = username
        super().__init__(f"User {username!r} already exists")


class UserNotFoundError(Exception):
    def __init__(self, username: str):
        self.username = username
        super().__init__(f"User {username!r} not found")


@dataclass(frozen=True)
class IssuedSession:
    """A new login. `token` is the only copy of the raw token: it goes in the
    browser's cookie and is never stored server-side."""

    token: str
    username: str
    expires_at: datetime


@dataclass(frozen=True)
class ClientInfo:
    """Where a login or logout came from, as recorded on its auth event."""

    ip: str | None = None
    user_agent: str | None = None


NO_CLIENT = ClientInfo()


@dataclass(frozen=True)
class AuthEventSummary:
    occurred_at: datetime
    event_type: str
    # None for an unknown username (which is never stored) or a deleted user.
    username: str | None
    session_id: int | None
    client_ip: str | None
    user_agent: str | None


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    username: str


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        clock: Callable[[], datetime] = _utcnow,
    ):
        self.repository = repository
        self.clock = clock

    def create_user(self, username: str, password: str) -> AuthenticatedUser:
        username = self._validated_username(username)
        self._check_password(password)
        if self.repository.get_user_by_username(username) is not None:
            raise UsernameTakenError(username)

        user = User(username=username, password_hash=_hasher.hash(password))
        self.repository.add_user(user)
        return AuthenticatedUser(id=user.id, username=user.username)

    def set_password(self, username: str, password: str) -> None:
        """Change a password and log out every existing session for the user."""
        self._check_password(password)
        user = self.repository.get_user_by_username(normalize_username(username))
        if user is None:
            raise UserNotFoundError(normalize_username(username))

        now = self.clock()
        user.password_hash = _hasher.hash(password)
        user.updated_at = now
        self.repository.revoke_all_sessions(user.id, now)

    def login(
        self, username: str, password: str, client: ClientInfo = NO_CLIENT
    ) -> IssuedSession:
        """Start a session, recording the attempt as an auth event whether or
        not it succeeds. The attempted username is never recorded."""
        user = self.repository.get_user_by_username(normalize_username(username))
        if user is None:
            self._verify(_dummy_hash(), password)
            self._record(AuthEventType.LOGIN_UNKNOWN_USER, client, self.clock())
            raise InvalidCredentialsError()
        if not self._verify(user.password_hash, password):
            self._record(
                AuthEventType.LOGIN_WRONG_PASSWORD, client, self.clock(), user.id
            )
            raise InvalidCredentialsError()

        now = self.clock()
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
            user.updated_at = now

        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_LIFETIME
        auth_session = AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=expires_at,
        )
        self.repository.add_session(auth_session)
        self._record(
            AuthEventType.LOGIN_SUCCEEDED, client, now, user.id, auth_session.id
        )
        return IssuedSession(token=token, username=user.username, expires_at=expires_at)

    def authenticate(self, token: str) -> AuthenticatedUser | None:
        """Return the session's user, or None if the token is unknown,
        expired, or logged out."""
        auth_session = self.repository.get_active_session(
            hash_session_token(token), self.clock()
        )
        if auth_session is None:
            return None
        return AuthenticatedUser(
            id=auth_session.user.id, username=auth_session.user.username
        )

    def logout(self, token: str, client: ClientInfo = NO_CLIENT) -> None:
        """Revoke the session and record the logout. A no-op (nothing
        recorded) for unknown or already-revoked tokens."""
        now = self.clock()
        revoked = self.repository.revoke_session(hash_session_token(token), now)
        if revoked is not None:
            session_id, user_id = revoked
            self._record(AuthEventType.LOGOUT, client, now, user_id, session_id)

    def recent_events(
        self, limit: int, failed_only: bool = False
    ) -> list[AuthEventSummary]:
        """The latest auth events, newest first."""
        events = self.repository.recent_events(
            limit, FAILED_LOGIN_EVENTS if failed_only else None
        )
        return [
            AuthEventSummary(
                occurred_at=event.occurred_at,
                event_type=event.event_type,
                username=event.user.username if event.user else None,
                session_id=event.session_id,
                client_ip=event.client_ip,
                user_agent=event.user_agent,
            )
            for event in events
        ]

    def delete_expired_events(self) -> int:
        """Delete auth events older than the retention period. Returns how
        many were deleted."""
        return self.repository.delete_events_before(self.clock() - AUTH_EVENT_RETENTION)

    def _record(
        self,
        event_type: AuthEventType,
        client: ClientInfo,
        occurred_at: datetime,
        user_id: int | None = None,
        session_id: int | None = None,
    ) -> None:
        self.repository.add_event(
            AuthEvent(
                occurred_at=occurred_at,
                event_type=event_type,
                user_id=user_id,
                session_id=session_id,
                client_ip=client.ip,
                user_agent=(client.user_agent or "")[:MAX_USER_AGENT_LENGTH] or None,
            )
        )

    @staticmethod
    def _verify(password_hash: str, password: str) -> bool:
        try:
            return _hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    @staticmethod
    def _validated_username(username: str) -> str:
        username = normalize_username(username)
        if not 1 <= len(username) <= MAX_USERNAME_LENGTH:
            raise InvalidUsernameError()
        return username

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError()
