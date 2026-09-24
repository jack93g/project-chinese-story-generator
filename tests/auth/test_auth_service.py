from datetime import UTC, datetime

import pytest

from story_generator.auth.persistence.models import AuthSession, User
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import (
    SESSION_LIFETIME,
    AuthService,
    InvalidCredentialsError,
    InvalidUsernameError,
    PasswordTooShortError,
    UsernameTakenError,
    UserNotFoundError,
    hash_session_token,
)

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery"


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def service(db_session, clock):
    return AuthService(AuthRepository(db_session), clock=clock)


def test_create_user_normalises_username_and_hashes_password(service, db_session):
    created = service.create_user("  Jack ", PASSWORD)

    user = db_session.get(User, created.id)
    assert user.username == "jack"
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")


def test_create_user_rejects_duplicate_usernames_case_insensitively(service):
    service.create_user("jack", PASSWORD)

    with pytest.raises(UsernameTakenError):
        service.create_user("JACK", PASSWORD)


def test_create_user_rejects_short_password(service):
    with pytest.raises(PasswordTooShortError):
        service.create_user("jack", "short")


def test_create_user_rejects_blank_username(service):
    with pytest.raises(InvalidUsernameError):
        service.create_user("   ", PASSWORD)


def test_login_issues_a_token_and_stores_only_its_hash(service, db_session, clock):
    service.create_user("jack", PASSWORD)

    issued = service.login("Jack", PASSWORD)

    stored = db_session.query(AuthSession).one()
    assert issued.username == "jack"
    assert stored.token_hash == hash_session_token(issued.token)
    assert stored.token_hash != issued.token
    assert stored.expires_at == clock.now + SESSION_LIFETIME


@pytest.mark.parametrize(
    ("username", "password"),
    [("jack", "wrong password here"), ("nobody", PASSWORD)],
)
def test_login_rejects_bad_credentials(service, db_session, username, password):
    service.create_user("jack", PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        service.login(username, password)
    assert db_session.query(AuthSession).count() == 0


def test_authenticate_returns_the_sessions_user(service):
    service.create_user("jack", PASSWORD)
    issued = service.login("jack", PASSWORD)

    user = service.authenticate(issued.token)

    assert user is not None
    assert user.username == "jack"


def test_authenticate_rejects_unknown_token(service):
    assert service.authenticate("not-a-token") is None


def test_authenticate_rejects_expired_session(service, clock):
    service.create_user("jack", PASSWORD)
    issued = service.login("jack", PASSWORD)

    clock.now += SESSION_LIFETIME

    assert service.authenticate(issued.token) is None


def test_logout_revokes_only_that_session(service):
    service.create_user("jack", PASSWORD)
    first = service.login("jack", PASSWORD)
    second = service.login("jack", PASSWORD)

    service.logout(first.token)

    assert service.authenticate(first.token) is None
    assert service.authenticate(second.token) is not None


def test_logout_of_unknown_token_is_a_no_op(service):
    service.logout("not-a-token")


def test_set_password_changes_password_and_revokes_all_sessions(service):
    service.create_user("jack", PASSWORD)
    issued = service.login("jack", PASSWORD)

    service.set_password("JACK", "a brand new password")

    assert service.authenticate(issued.token) is None
    with pytest.raises(InvalidCredentialsError):
        service.login("jack", PASSWORD)
    assert service.login("jack", "a brand new password").username == "jack"


def test_set_password_for_unknown_user_raises(service):
    with pytest.raises(UserNotFoundError):
        service.set_password("nobody", PASSWORD)
