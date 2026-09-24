import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from story_generator.auth.persistence.models import AuthSession, User
from story_generator.auth.persistence.repository import AuthRepository

SESSION_LIFETIME = timedelta(days=30)
MIN_PASSWORD_LENGTH = 12
MAX_USERNAME_LENGTH = 150

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


class InvalidCredentialsError(Exception):
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

    def login(self, username: str, password: str) -> IssuedSession:
        user = self.repository.get_user_by_username(normalize_username(username))
        if user is None:
            self._verify(_dummy_hash(), password)
            raise InvalidCredentialsError()
        if not self._verify(user.password_hash, password):
            raise InvalidCredentialsError()

        now = self.clock()
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
            user.updated_at = now

        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_LIFETIME
        self.repository.add_session(
            AuthSession(
                user_id=user.id,
                token_hash=hash_session_token(token),
                created_at=now,
                expires_at=expires_at,
            )
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

    def logout(self, token: str) -> None:
        """Revoke the session. A no-op for unknown or already-revoked tokens."""
        self.repository.revoke_session(hash_session_token(token), self.clock())

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
