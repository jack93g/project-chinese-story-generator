import pytest
from fastapi.testclient import TestClient

from story_generator.api import rate_limit
from story_generator.api.app import create_app
from story_generator.api.dependencies import get_db
from story_generator.api.rate_limit import SlidingWindowRateLimiter
from tests.conftest import TEST_API_KEY

PROTECTED_PATHS = ["/stories", "/vocabulary-lists", "/story-generations/1"]


@pytest.fixture
def anonymous_client():
    return TestClient(create_app())


def test_app_refuses_to_start_without_access_key(monkeypatch):
    monkeypatch.delenv("API_ACCESS_KEY", raising=False)

    with pytest.raises(RuntimeError, match="API_ACCESS_KEY"):
        create_app()


def test_health_needs_no_key(anonymous_client):
    assert anonymous_client.get("/health").status_code == 200


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_missing_key_returns_401(anonymous_client, path):
    assert anonymous_client.get(path).status_code == 401


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_wrong_key_returns_401(anonymous_client, path):
    response = anonymous_client.get(path, headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_missing_key_on_write_endpoints_returns_401(anonymous_client):
    assert anonymous_client.post("/story-generations", json={}).status_code == 401
    assert anonymous_client.post("/story-generations/1/retry").status_code == 401
    assert anonymous_client.delete("/stories/1").status_code == 401


def test_docs_and_openapi_are_not_exposed(anonymous_client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anonymous_client.get(path).status_code == 404


def test_cors_preflight_allows_the_key_header_without_needing_it(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://huaben.app")
    client = TestClient(create_app())

    response = client.options(
        "/stories",
        headers={
            "Origin": "https://huaben.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )

    assert response.status_code == 200
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


def test_sliding_window_limiter_blocks_then_recovers(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.check() is None
    assert limiter.check() is None
    assert limiter.check() == pytest.approx(60)

    now[0] += 61
    assert limiter.check() is None


def test_sliding_window_limiter_counts_each_key_separately():
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)

    assert limiter.check("203.0.113.1") is None
    assert limiter.check("203.0.113.1") is not None
    assert limiter.check("203.0.113.2") is None


def test_sliding_window_limiter_forgets_idle_keys(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    limiter.check("203.0.113.1")

    now[0] += 61
    limiter.check("203.0.113.2")

    assert list(limiter._hits) == ["203.0.113.2"]


def test_generation_endpoints_return_429_when_rate_limited(monkeypatch):
    monkeypatch.setattr(
        rate_limit, "_generation_limiter", SlidingWindowRateLimiter(1, 60)
    )
    app = create_app()
    # FastAPI resolves every dependency (including get_db) before it reports a
    # body-validation error, so stub the session: this test needs no database.
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})

    # Invalid body: fails validation (422) but still consumes rate-limit budget.
    assert client.post("/story-generations", json={}).status_code == 422
    limited = client.post("/story-generations", json={})

    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_unauthenticated_requests_do_not_consume_rate_limit_budget(monkeypatch):
    limiter = SlidingWindowRateLimiter(1, 60)
    monkeypatch.setattr(rate_limit, "_generation_limiter", limiter)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: None

    anonymous = TestClient(app)
    for _ in range(3):
        assert anonymous.post("/story-generations", json={}).status_code == 401

    keyed = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    assert keyed.post("/story-generations", json={}).status_code == 422


def test_limiter_reset_clears_recorded_hits():
    limiter = SlidingWindowRateLimiter(1, 60)
    assert limiter.check() is None
    assert limiter.check() is not None

    limiter.reset()

    assert limiter.check() is None
