import pytest
from fastapi.testclient import TestClient

from story_generator.api import rate_limit
from story_generator.api.app import create_app
from story_generator.api.dependencies import get_db
from story_generator.api.rate_limit import SlidingWindowRateLimiter
from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import AuthService

PASSWORD = "correct horse battery"
ALLOWED_ORIGIN = "https://huaben.app"


@pytest.fixture
def browser(db_session, monkeypatch):
    """A client with no API key, like the frontend: it relies on the cookie.
    https, because the session cookie is Secure and httpx honours that."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url="https://testserver") as client:
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
