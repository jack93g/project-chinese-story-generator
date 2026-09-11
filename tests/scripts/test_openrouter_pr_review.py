import io
import json
import urllib.error

import pytest

import scripts.openrouter_pr_review as pr_review
from scripts.openrouter_pr_review import (
    call_openrouter,
    env,
    fetch_pr_diff,
    load_claude_md,
    main,
    post_comment,
    truncate,
)


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
    assert result == "aaaaa\n\n... [truncated, too large to review in full]"


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


def test_call_openrouter_raises_clear_error_on_non_string_content(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": None}}]}).encode()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout=None: _FakeResponse(body)
    )

    with pytest.raises(RuntimeError, match="Unexpected OpenRouter response shape"):
        call_openrouter("fake-key", "diff", "claude.md contents")


def test_call_openrouter_retries_on_network_error_then_succeeds(monkeypatch):
    success_body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
    responses = [
        urllib.error.URLError("connection reset"),
        _FakeResponse(success_body),
    ]

    def fake_urlopen(request, timeout=None):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    assert call_openrouter("fake-key", "diff", "claude.md contents") == "ok"


def test_fetch_pr_diff_rejects_non_numeric_pr_number():
    with pytest.raises(ValueError, match="PR_NUMBER"):
        fetch_pr_diff("owner/repo", "43; rm -rf /", "token")


def test_fetch_pr_diff_builds_url_and_truncates(monkeypatch):
    captured = {}

    def fake_github_request(url, token, accept):
        captured["url"] = url
        captured["accept"] = accept
        return b"diff --git a/foo b/foo\n+hello\n"

    monkeypatch.setattr(pr_review, "github_request", fake_github_request)
    monkeypatch.setattr(pr_review, "MAX_DIFF_CHARS", 10)

    result = fetch_pr_diff("owner/repo", "43", "token")

    assert captured["url"] == "https://api.github.com/repos/owner/repo/pulls/43"
    assert captured["accept"] == "application/vnd.github.v3.diff"
    assert result.endswith("[truncated, too large to review in full]")


def test_load_claude_md_falls_back_on_404(monkeypatch):
    def fake_github_request(url, token, accept):
        raise urllib.error.HTTPError(url, 404, "not found", None, io.BytesIO(b""))

    monkeypatch.setattr(pr_review, "github_request", fake_github_request)

    result = load_claude_md("owner/repo", "token", "main")

    assert result == "(no CLAUDE.md found in this repo)"


def test_load_claude_md_reraises_on_other_errors(monkeypatch):
    def fake_github_request(url, token, accept):
        raise urllib.error.HTTPError(url, 500, "server error", None, io.BytesIO(b""))

    monkeypatch.setattr(pr_review, "github_request", fake_github_request)

    with pytest.raises(urllib.error.HTTPError):
        load_claude_md("owner/repo", "token", "main")


def test_load_claude_md_encodes_base_ref(monkeypatch):
    captured = {}

    def fake_github_request(url, token, accept):
        captured["url"] = url
        return b"# CLAUDE.md"

    monkeypatch.setattr(pr_review, "github_request", fake_github_request)

    load_claude_md("owner/repo", "token", "feature/weird ref")

    assert "feature%2Fweird%20ref" in captured["url"]


def test_post_comment_sends_expected_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data)
        return _FakeResponse(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    post_comment("owner/repo", "43", "token", "the review text")

    assert captured["url"] == "https://api.github.com/repos/owner/repo/issues/43/comments"
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert "the review text" in captured["body"]["body"]
    assert "Automated, unverified output" in captured["body"]["body"]


def test_env_exits_when_missing(monkeypatch):
    monkeypatch.delenv("SOME_UNSET_VAR", raising=False)
    with pytest.raises(SystemExit):
        env("SOME_UNSET_VAR")


def test_main_returns_early_on_empty_diff(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "43")

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: "   ")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not be called for an empty diff")

    monkeypatch.setattr(pr_review, "load_claude_md", fail_if_called)
    monkeypatch.setattr(pr_review, "call_openrouter", fail_if_called)
    monkeypatch.setattr(pr_review, "post_comment", fail_if_called)

    main()  # should return quietly instead of calling the fakes above
