"""
Redaction for provider request/response bodies persisted to
raw_generation_payloads.

Two layers of defense:
  1. Callers must never pass HTTP headers into this module or the
     persistence path — only parsed request/response *bodies* are
     accepted anywhere in this module's surface. There is no
     parameter here that accepts headers, by design, so headers
     structurally cannot reach the database through this path.
  2. As a second safeguard, `redact` recursively walks a body and
     masks any value whose key matches the denylist below, in case a
     secret is echoed back inside a body (e.g. a provider error
     response that includes the request payload it received).
"""

from typing import Any

_DENYLIST_SUBSTRINGS = (
    "authorization",
    "api_key",
    "x-api-key",
    "token",
    "secret",
    "password",
)

_REDACTED = "[REDACTED]"


def _is_denylisted(key: str) -> bool:
    lowered = key.lower()
    return any(term in lowered for term in _DENYLIST_SUBSTRINGS)


def redact(value: Any) -> Any:
    """Recursively redact denylisted keys from a JSON-like structure."""
    if isinstance(value, dict):
        return {
            key: (_REDACTED if _is_denylisted(key) else redact(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
