import pytest

from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import AuthService, UsernameTakenError
from story_generator.cli.users import run

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery"


def test_create_then_log_in(db_session):
    message = run(["create", "Jack"], db_session, read_password=lambda: PASSWORD)

    assert message == "Created user 'jack'."
    service = AuthService(AuthRepository(db_session))
    assert service.login("jack", PASSWORD).username == "jack"


def test_create_existing_user_fails(db_session):
    run(["create", "jack"], db_session, read_password=lambda: PASSWORD)

    with pytest.raises(UsernameTakenError):
        run(["create", "jack"], db_session, read_password=lambda: PASSWORD)


def test_set_password_logs_out_existing_sessions(db_session):
    run(["create", "jack"], db_session, read_password=lambda: PASSWORD)
    service = AuthService(AuthRepository(db_session))
    issued = service.login("jack", PASSWORD)

    message = run(
        ["set-password", "jack"],
        db_session,
        read_password=lambda: "a brand new password",
    )

    assert "logged out" in message
    assert service.authenticate(issued.token) is None
