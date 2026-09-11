import io
import json
import urllib.error

import pytest

from scripts.openrouter_pr_review import call_openrouter, truncate


def test_truncate_leaves_short_text_untouched():
    assert truncate("short diff", 100) == "short diff"


def test_truncate_cuts_on_line_boundary():
    text = "line one\nline two\nline three"
    result = truncate(text, max_chars=14)
    assert result.startswith("line one\n")
    assert "line two" not in result
    assert result.endswith("[truncated, too large to review in full]")


def test_truncate_falls_back_to_hard_cutoff_with_no_newline():
    result = truncate("a" * 20, max_chars=5)
    assert result.startswith("aaaaa")


def _http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_call_openrouter_retries_on_503_then_succeeds(monkeypatch):
    success_body = json.dumps({"choices": [{"message": {"content": "looks good"}}]}).encode()
    responses = [
        _http_error(503, b'{"error": "overloaded"}'),
        _FakeResponse(success_body),
    ]

    def fake_urlopen(request, timeout=None):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result = call_openrouter("fake-key", "diff", "claude.md contents")
    assert result == "looks good"


def test_call_openrouter_raises_after_exhausting_retries(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise _http_error(503, b'{"error": "still overloaded"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    with pytest.raises(urllib.error.HTTPError):
        call_openrouter("fake-key", "diff", "claude.md contents")


def test_call_openrouter_does_not_retry_on_non_retryable_status(monkeypatch):
    calls = {"count": 0}

    def fake_urlopen(request, timeout=None):
        calls["count"] += 1
        raise _http_error(401, b'{"error": "invalid key"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError):
        call_openrouter("fake-key", "diff", "claude.md contents")
    assert calls["count"] == 1


def test_call_openrouter_raises_clear_error_on_unexpected_response_shape(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(json.dumps({"unexpected": "shape"}).encode()),
    )

    with pytest.raises(RuntimeError, match="Unexpected OpenRouter response shape"):
        call_openrouter("fake-key", "diff", "claude.md contents")
