import time
from collections import deque
from threading import Lock

from fastapi import HTTPException

# One shared budget for POST /story-generations and its retry endpoint.
# In-memory, so it is per API process — fine for the single-process,
# single-user deployment; move to shared storage if that ever changes.
GENERATION_RATE_LIMIT = 10
GENERATION_RATE_WINDOW_SECONDS = 60.0

# Login attempts, successful or not, across all callers: slows password
# guessing. Global rather than per client, because behind Caddy every request
# comes from the same address. A guesser can hold the login form shut for a
# minute at a time; the X-API-Key still works then.
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: deque[float] = deque()
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until retry."""
        now = time.monotonic()
        with self._lock:
            while self._hits and now - self._hits[0] >= self.window_seconds:
                self._hits.popleft()
            if len(self._hits) >= self.limit:
                return self.window_seconds - (now - self._hits[0])
            self._hits.append(now)
            return None


_generation_limiter = SlidingWindowRateLimiter(
    GENERATION_RATE_LIMIT, GENERATION_RATE_WINDOW_SECONDS
)


_login_limiter = SlidingWindowRateLimiter(LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS)


def _enforce(limiter: SlidingWindowRateLimiter, detail: str) -> None:
    retry_after = limiter.check()
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def generation_rate_limit() -> None:
    _enforce(_generation_limiter, "Too many generation requests; slow down")


def login_rate_limit() -> None:
    _enforce(_login_limiter, "Too many login attempts; try again in a minute")
