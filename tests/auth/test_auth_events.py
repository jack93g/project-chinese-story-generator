"""Auth event recording, without a database: the repository is a fake."""

import pytest

from story_generator.auth.service import (
    MAX_USER_AGENT_LENGTH,
    AuthService,
    ClientInfo,
    InvalidCredentialsError,
)


class FakeRepository:
    def __init__(self):
        self.events = []

    def get_user_by_username(self, username):
        return None

    def add_event(self, event):
        self.events.append(event)


def test_unknown_user_is_recorded_without_a_username():
    repository = FakeRepository()

    with pytest.raises(InvalidCredentialsError):
        AuthService(repository).login(
            "typed-my-password-here", "x", ClientInfo(ip="203.0.113.9")
        )

    (event,) = repository.events
    assert event.event_type == "login_unknown_user"
    assert event.user_id is None
    assert event.client_ip == "203.0.113.9"
    assert "typed-my-password-here" not in repr(vars(event))


@pytest.mark.parametrize(
    ("user_agent", "stored"),
    [
        ("a" * (MAX_USER_AGENT_LENGTH + 100), "a" * MAX_USER_AGENT_LENGTH),
        ("", None),
        (None, None),
    ],
)
def test_user_agent_is_truncated_and_blank_is_null(user_agent, stored):
    repository = FakeRepository()

    with pytest.raises(InvalidCredentialsError):
        AuthService(repository).login("nobody", "x", ClientInfo(user_agent=user_agent))

    assert repository.events[0].user_agent == stored
