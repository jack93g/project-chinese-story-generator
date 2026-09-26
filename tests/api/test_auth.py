import pytest
from fastapi.testclient import TestClient

from story_generator.api import rate_limit
from story_generator.api.app import create_app
from story_generator.api.dependencies import get_db
from story_generator.api.rate_limit import SlidingWindowRateLimiter
from story_generator.auth.persistence.models import AuthEvent, AuthSession
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import AuthService

PASSWORD = "correct horse battery"
ALLOWED_ORIGIN = "https://huaben.app"
CLIENT_IP = "203.0.113.9"
USER_AGENT = "Mozilla/5.0 (test browser)"


@pytest.fixture
def browser(db_session, monkeypatch):
    """A client with no API key, like the frontend: it relies on the cookie.
    https, because the session cookie is Secure and httpx honours that."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(
        app,
        base_url="https://testserver",
        client=(CLIENT_IP, 50000),
        headers={"User-Agent": USER_AGENT},
    ) as client:
        yield client


@pytest.fixture
def user(db_session):
    return AuthService(AuthRepository(db_session)).create_user("jack", PASSWORD)


def log_in(client, username="jack", password=PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


@pytest.mark.db
def test_login_sets_a_locked_down_session_cookie(browser, user):
    response = log_in(browser, username="Jack")

    assert response.status_code == 200
    assert response.json() == {"username": "jack"}
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("session=")
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie


@pytest.mark.db
def test_session_cookie_grants_access_and_identifies_the_user(browser, user):
    assert browser.get("/stories").status_code == 401
    assert browser.get("/auth/me").status_code == 401

    log_in(browser)

    assert browser.get("/stories").status_code == 200
    assert browser.get("/auth/me").json() == {"username": "jack"}


@pytest.mark.db
def test_wrong_password_returns_401_without_a_cookie(browser, user):
    response = log_in(browser, password="not the password")

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert browser.get("/stories").status_code == 401


@pytest.mark.db
def test_logout_revokes_the_session_and_clears_the_cookie(browser, user):
    log_in(browser)
    token = browser.cookies["session"]

    response = browser.post("/auth/logout")

    assert response.status_code == 204
    assert 'session=""' in response.headers["set-cookie"]
    # Even a copy of the old token no longer works.
    browser.cookies.set("session", token)
    assert browser.get("/stories").status_code == 401


@pytest.mark.db
def test_logout_without_a_session_still_succeeds(browser):
    assert browser.post("/auth/logout").status_code == 204


@pytest.mark.db
def test_made_up_session_cookie_is_rejected(browser):
    browser.cookies.set("session", "made-up")

    assert browser.get("/stories").status_code == 401


@pytest.mark.db
def test_cookie_authenticated_writes_need_an_allowed_origin(browser, user):
    log_in(browser)

    assert browser.delete("/stories/999999").status_code == 403
    assert (
        browser.delete(
            "/stories/999999", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    # Past the auth gate: the story just doesn't exist.
    assert (
        browser.delete(
            "/stories/999999", headers={"Origin": ALLOWED_ORIGIN}
        ).status_code
        == 404
    )


@pytest.mark.db
def test_api_key_writes_need_no_origin(client):
    assert client.delete("/stories/999999").status_code == 404


@pytest.mark.db
def test_api_key_has_no_user(client):
    assert client.get("/auth/me").status_code == 401


def test_login_is_rate_limited(monkeypatch):
    monkeypatch.setattr(rate_limit, "_login_limiter", SlidingWindowRateLimiter(1, 60))
    app = create_app()
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)

    # Invalid body: fails validation (422) but still uses up the budget.
    assert client.post("/auth/login", json={}).status_code == 422
    limited = client.post("/auth/login", json={})

    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_login_is_limited_per_client_address(monkeypatch):
    monkeypatch.setattr(
        rate_limit, "_login_client_limiter", SlidingWindowRateLimiter(1, 60)
    )
    shared = SlidingWindowRateLimiter(10, 60)
    monkeypatch.setattr(rate_limit, "_login_limiter", shared)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: None
    guesser = TestClient(app, client=("203.0.113.1", 50000))
    owner = TestClient(app, client=("198.51.100.7", 50000))

    assert guesser.post("/auth/login", json={}).status_code == 422
    for _ in range(3):
        assert guesser.post("/auth/login", json={}).status_code == 429

    # Another address still gets through, and the guesser's blocked attempts
    # didn't use up the shared budget.
    assert owner.post("/auth/login", json={}).status_code == 422
    assert len(shared._hits[""]) == 2


def test_cors_allows_credentials_for_listed_origins(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    client = TestClient(create_app())

    response = client.options(
        "/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_insecure_cookie_setting_is_opt_in(monkeypatch):
    from story_generator.config import get_session_cookie_secure

    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    assert get_session_cookie_secure() is True
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert get_session_cookie_secure() is False


@pytest.mark.db
def test_quiz_attempt_records_the_logged_in_user(browser, user, db_session):
    from story_generator.stories.persistence.models import QuizAttempt, Story

    story = Story(
        title="点菜",
        content="我们去饭馆。",
        comprehension_questions=[
            {"question": "去哪里？", "options": ["学校", "饭馆"], "answer": 1}
        ],
    )
    db_session.add(story)
    db_session.flush()
    log_in(browser)

    response = browser.post(
        f"/stories/{story.id}/quiz-attempts",
        json={"answers": [1]},
        headers={"Origin": ALLOWED_ORIGIN},
    )

    assert response.status_code == 201
    assert db_session.get(QuizAttempt, response.json()["id"]).user_id == user.id


@pytest.mark.db
def test_question_flag_records_the_logged_in_user(browser, user, db_session):
    from story_generator.stories.persistence.models import QuestionFlag, Story

    story = Story(
        title="点菜",
        content="我们去饭馆。",
        comprehension_questions=[
            {"question": "去哪里？", "options": ["学校", "饭馆"], "answer": 1}
        ],
    )
    db_session.add(story)
    db_session.flush()
    log_in(browser)

    response = browser.post(
        f"/stories/{story.id}/question-flags",
        json={"question_index": 0},
        headers={"Origin": ALLOWED_ORIGIN},
    )

    assert response.status_code == 201
    assert db_session.get(QuestionFlag, response.json()["id"]).user_id == user.id


def auth_events(db_session):
    return db_session.query(AuthEvent).order_by(AuthEvent.id).all()


@pytest.mark.db
def test_successful_login_records_the_session_and_client(browser, user, db_session):
    log_in(browser)

    (event,) = auth_events(db_session)
    assert event.event_type == "login_succeeded"
    assert event.user_id == user.id
    assert event.session_id == db_session.query(AuthSession).one().id
    assert event.client_ip == CLIENT_IP
    assert event.user_agent == USER_AGENT


@pytest.mark.db
def test_wrong_password_is_recorded_and_committed(browser, user, db_session):
    log_in(browser, password="not the password")
    # Undo anything the request left uncommitted: the event must survive.
    db_session.rollback()

    (event,) = auth_events(db_session)
    assert event.event_type == "login_wrong_password"
    assert event.user_id == user.id
    assert event.session_id is None
    assert event.client_ip == CLIENT_IP


@pytest.mark.db
def test_unknown_user_is_recorded_without_the_attempted_username(
    browser, user, db_session
):
    # What someone who typed their password into the username box would send.
    attempted = "hunter2-my-secret"
    log_in(browser, username=attempted)
    db_session.rollback()

    (event,) = auth_events(db_session)
    assert event.event_type == "login_unknown_user"
    assert event.user_id is None
    assert event.session_id is None
    stored = [getattr(event, column.key) for column in AuthEvent.__table__.columns]
    assert not any(attempted in str(value) for value in stored)


@pytest.mark.db
def test_both_kinds_of_failed_login_look_the_same(browser, user):
    wrong_password = log_in(browser, password="not the password")
    unknown_user = log_in(browser, username="nobody")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json() == {"detail": "Incorrect username or password"}


@pytest.mark.db
def test_rate_limited_login_attempts_are_not_recorded(
    browser, user, db_session, monkeypatch
):
    monkeypatch.setattr(
        rate_limit, "_login_client_limiter", SlidingWindowRateLimiter(1, 60)
    )

    assert log_in(browser, password="not the password").status_code == 401
    assert log_in(browser, password="not the password").status_code == 429

    assert len(auth_events(db_session)) == 1


@pytest.mark.db
def test_logout_is_recorded_with_its_session(browser, user, db_session):
    log_in(browser)
    login_event = auth_events(db_session)[0]

    browser.post("/auth/logout")

    logout_event = auth_events(db_session)[1]
    assert logout_event.event_type == "logout"
    assert logout_event.user_id == user.id
    assert logout_event.session_id == login_event.session_id
    assert logout_event.client_ip == CLIENT_IP


@pytest.mark.db
def test_logout_without_a_live_session_is_not_recorded(browser, user, db_session):
    browser.post("/auth/logout")
    browser.cookies.set("session", "made-up")
    browser.post("/auth/logout")

    assert auth_events(db_session) == []
