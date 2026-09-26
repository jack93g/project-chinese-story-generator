from datetime import UTC, datetime, timedelta

import pytest

from story_generator.auth.persistence.models import AuthEvent
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import AUTH_EVENT_RETENTION, AuthService
from story_generator.cli.logins import build_parser, run

PASSWORD = "correct horse battery"


@pytest.fixture
def jack(db_session):
    return AuthService(AuthRepository(db_session)).create_user("jack", PASSWORD)


def _event(db_session, event_type, occurred_at, user_id=None, **fields):
    event = AuthEvent(
        event_type=event_type, occurred_at=occurred_at, user_id=user_id, **fields
    )
    db_session.add(event)
    db_session.flush()
    return event


@pytest.mark.db
def test_recent_lists_events_newest_first(db_session, jack):
    now = datetime.now(UTC)
    _event(
        db_session,
        "login_wrong_password",
        now - timedelta(minutes=5),
        jack.id,
        client_ip="203.0.113.9",
        user_agent="x" * 100,
    )
    _event(db_session, "login_unknown_user", now, client_ip="198.51.100.7")

    lines = run(["recent"], db_session).splitlines()

    assert lines[0].startswith("OCCURRED (UTC)")
    assert "login_unknown_user" in lines[1] and "198.51.100.7" in lines[1]
    assert "login_wrong_password" in lines[2] and "jack" in lines[2]
    assert lines[2].endswith("x" * 59 + "…")


@pytest.mark.db
def test_recent_failed_and_limit(db_session, jack):
    now = datetime.now(UTC)
    _event(db_session, "login_wrong_password", now - timedelta(minutes=2), jack.id)
    _event(db_session, "login_unknown_user", now - timedelta(minutes=1))
    _event(db_session, "logout", now, jack.id)

    failed = run(["recent", "--failed"], db_session).splitlines()[1:]
    limited = run(["recent", "--limit", "1"], db_session).splitlines()[1:]

    assert [line.split()[2] for line in failed] == [
        "login_unknown_user",
        "login_wrong_password",
    ]
    assert len(limited) == 1 and "logout" in limited[0]


@pytest.mark.db
def test_recent_with_nothing_recorded(db_session):
    assert run(["recent"], db_session) == "No auth events."
    assert run(["recent", "--failed"], db_session) == "No failed login attempts."


@pytest.mark.db
def test_purge_deletes_only_events_past_retention(db_session):
    now = datetime.now(UTC)
    _event(
        db_session,
        "login_unknown_user",
        now - AUTH_EVENT_RETENTION - timedelta(hours=1),
    )
    kept = _event(db_session, "login_unknown_user", now - timedelta(days=1))

    message = run(["purge"], db_session)

    assert message == "Deleted 1 auth events older than 90 days."
    assert [event.id for event in db_session.query(AuthEvent).all()] == [kept.id]


def test_limit_must_be_positive():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["recent", "--limit", "0"])
