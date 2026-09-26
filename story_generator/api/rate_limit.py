import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request

# One shared budget for POST /story-generations and its retry endpoint.
# In-memory, so it is per API process — fine for the single-process,
# single-user deployment; move to shared storage if that ever changes.
GENERATION_RATE_LIMIT = 10
GENERATION_RATE_WINDOW_SECONDS = 60.0

# Login attempts, successful or not: slows password guessing. Counted per
# client address, so one guesser can't hold the login form shut for everyone
# else, plus a looser cap across all clients against guessing spread over
# many addresses. The client address is the real caller's only because
# production sets FORWARDED_ALLOW_IPS (docker-compose.prod.yml); without it,
# every request behind Caddy shares Caddy's address and the per-client limit
# acts like a global one.
LOGIN_RATE_LIMIT_PER_CLIENT = 10
LOGIN_RATE_LIMIT = 60
LOGIN_RATE_WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """Allows `limit` hits per `window_seconds`, counted separately per key."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, key: str = "") -> float | None:
        """Record a hit for `key`. Returns None if allowed, else seconds until retry."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                self._forget_idle_keys(now)
                hits = self._hits[key] = deque()
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window_seconds - (now - hits[0])
            hits.append(now)
            return None

    def _forget_idle_keys(self, now: float) -> None:
        # Run whenever a new key arrives, so memory is bounded by the keys
        # seen within one window rather than growing with every address ever.
        idle = [
            key
            for key, hits in self._hits.items()
            if not hits or now - hits[-1] >= self.window_seconds
        ]
        for key in idle:
            del self._hits[key]


_generation_limiter = SlidingWindowRateLimiter(
    GENERATION_RATE_LIMIT, GENERATION_RATE_WINDOW_SECONDS
)


_login_client_limiter = SlidingWindowRateLimiter(
    LOGIN_RATE_LIMIT_PER_CLIENT, LOGIN_RATE_WINDOW_SECONDS
)
_login_limiter = SlidingWindowRateLimiter(LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS)


def _enforce(limiter: SlidingWindowRateLimiter, detail: str, key: str = "") -> None:
    retry_after = limiter.check(key)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def generation_rate_limit() -> None:
    _enforce(_generation_limiter, "Too many generation requests; slow down")


def login_rate_limit(request: Request) -> None:
    detail = "Too many login attempts; try again in a minute"
    client = request.client.host if request.client else ""
    # Per client first: a client that is already blocked doesn't also use up
    # the shared budget.
    _enforce(_login_client_limiter, detail, key=client)
    _enforce(_login_limiter, detail)
