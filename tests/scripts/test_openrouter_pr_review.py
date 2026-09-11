import io
import json
import urllib.error

import pytest

import scripts.openrouter_pr_review as pr_review
from scripts.openrouter_pr_review import (
    call_openrouter,
    env,
    extract_json_object,
    fetch_diff_since,
    fetch_last_reviewed_sha,
    fetch_pr_diff,
    load_claude_md,
    main,
    parse_review,
    post_comment,
    render_comment,
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


def _review_json(**overrides) -> bytes:
    payload = {
        "verdict": "green",
        "pr_summary": "Adds a thing.",
        "findings_markdown": "No issues found.",
        "changes_since_last_review_markdown": None,
    }
    payload.update(overrides)
    return json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]}).encode()


def test_call_openrouter_retries_on_503_then_succeeds(monkeypatch):
    responses = [
        _http_error(503, b'{"error": "overloaded"}'),
        _FakeResponse(_review_json()),
    ]

    def fake_urlopen(request, timeout=None):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result = call_openrouter("fake-key", "diff", "claude.md contents")
    assert json.loads(result)["verdict"] == "green"


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
    responses = [
        urllib.error.URLError("connection reset"),
        _FakeResponse(_review_json()),
    ]

    def fake_urlopen(request, timeout=None):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    assert json.loads(call_openrouter("fake-key", "diff", "claude.md contents"))["verdict"] == "green"


def test_call_openrouter_omits_since_block_when_not_given(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data)
        return _FakeResponse(_review_json())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    call_openrouter("fake-key", "diff", "claude.md contents", since_diff=None)

    user_message = captured["body"]["messages"][1]["content"]
    assert "changes_since_last_review" not in user_message


def test_call_openrouter_includes_since_block_when_given(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data)
        return _FakeResponse(_review_json())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    call_openrouter("fake-key", "diff", "claude.md contents", since_diff="+ new line")

    user_message = captured["body"]["messages"][1]["content"]
    assert "<changes_since_last_review>" in user_message
    assert "+ new line" in user_message


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


def test_fetch_diff_since_builds_compare_url(monkeypatch):
    captured = {}

    def fake_github_request(url, token, accept):
        captured["url"] = url
        captured["accept"] = accept
        return b"diff --git a/foo b/foo\n+world\n"

    monkeypatch.setattr(pr_review, "github_request", fake_github_request)

    result = fetch_diff_since("owner/repo", "abc123", "def456", "token")

    assert captured["url"] == "https://api.github.com/repos/owner/repo/compare/abc123...def456"
    assert captured["accept"] == "application/vnd.github.v3.diff"
    assert "world" in result


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


def test_fetch_last_reviewed_sha_returns_none_with_no_comments(monkeypatch):
    monkeypatch.setattr(pr_review, "github_request", lambda *a, **k: b"[]")
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") is None


def test_fetch_last_reviewed_sha_returns_none_without_marker(monkeypatch):
    comments = [{"body": "just a regular human comment"}]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") is None


def test_fetch_last_reviewed_sha_returns_most_recent_marker(monkeypatch):
    comments = [
        {"body": f"### 🟡 DeepSeek review\n...\n{pr_review.REVIEW_MARKER_PREFIX}sha-one -->"},
        {"body": "a human reply in between"},
        {"body": f"### 🟢 DeepSeek review\n...\n{pr_review.REVIEW_MARKER_PREFIX}sha-two -->"},
    ]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") == "sha-two"


def test_extract_json_object_parses_plain_json():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_strips_code_fence():
    text = '```json\n{"a": 1}\n```'
    assert extract_json_object(text) == {"a": 1}


def test_parse_review_valid_payload():
    content = json.dumps(
        {
            "verdict": "RED",
            "pr_summary": "Does a thing.",
            "findings_markdown": "- bug in foo.py",
            "changes_since_last_review_markdown": None,
        }
    )
    result = parse_review(content)
    assert result["verdict"] == "red"
    assert result["findings_markdown"] == "- bug in foo.py"
    assert result["changes_since_last_review_markdown"] is None


def test_parse_review_rejects_unknown_verdict():
    content = json.dumps(
        {"verdict": "orange", "pr_summary": "x", "findings_markdown": "x"}
    )
    with pytest.raises(RuntimeError, match="Unexpected review JSON shape"):
        parse_review(content)


def test_parse_review_rejects_missing_key():
    content = json.dumps({"verdict": "green", "pr_summary": "x"})
    with pytest.raises(RuntimeError, match="Unexpected review JSON shape"):
        parse_review(content)


def test_parse_review_rejects_non_json():
    with pytest.raises(RuntimeError, match="Unexpected review JSON shape"):
        parse_review("not json at all")


def test_render_comment_shows_correct_emoji_per_verdict():
    for verdict, emoji in [("green", "🟢"), ("yellow", "🟡"), ("red", "🔴")]:
        review = {
            "verdict": verdict,
            "pr_summary": "summary",
            "findings_markdown": "findings",
            "changes_since_last_review_markdown": None,
        }
        comment = render_comment(review, "some/model", "abc123")
        assert comment.startswith(f"### {emoji} DeepSeek review")


def test_render_comment_omits_since_section_when_absent():
    review = {
        "verdict": "green",
        "pr_summary": "summary",
        "findings_markdown": "findings",
        "changes_since_last_review_markdown": None,
    }
    comment = render_comment(review, "some/model", "abc123")
    assert "What changed since the last review" not in comment


def test_render_comment_includes_since_section_when_present():
    review = {
        "verdict": "yellow",
        "pr_summary": "summary",
        "findings_markdown": "findings",
        "changes_since_last_review_markdown": "- addressed the null check",
    }
    comment = render_comment(review, "some/model", "abc123")
    assert "What changed since the last review" in comment
    assert "addressed the null check" in comment


def test_render_comment_includes_model_and_sha_marker():
    review = {
        "verdict": "green",
        "pr_summary": "summary",
        "findings_markdown": "findings",
        "changes_since_last_review_markdown": None,
    }
    comment = render_comment(review, "deepseek/deepseek-v4.1-flash", "abc123")
    assert "`deepseek/deepseek-v4.1-flash`" in comment
    assert f"{pr_review.REVIEW_MARKER_PREFIX}abc123 -->" in comment


def test_post_comment_sends_expected_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data)
        return _FakeResponse(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    post_comment("owner/repo", "43", "token", "a fully rendered comment")

    assert captured["url"] == "https://api.github.com/repos/owner/repo/issues/43/comments"
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["body"]["body"] == "a fully rendered comment"


def test_env_exits_when_missing(monkeypatch):
    monkeypatch.delenv("SOME_UNSET_VAR", raising=False)
    with pytest.raises(SystemExit):
        env("SOME_UNSET_VAR")


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "43")
    monkeypatch.setenv("PR_HEAD_SHA", "head-sha")


def test_main_returns_early_on_empty_diff(monkeypatch):
    _set_required_env(monkeypatch)

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: "   ")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not be called for an empty diff")

    monkeypatch.setattr(pr_review, "load_claude_md", fail_if_called)
    monkeypatch.setattr(pr_review, "fetch_last_reviewed_sha", fail_if_called)
    monkeypatch.setattr(pr_review, "call_openrouter", fail_if_called)
    monkeypatch.setattr(pr_review, "post_comment", fail_if_called)

    main()  # should return quietly instead of calling the fakes above


def test_main_first_review_posts_rendered_comment_without_since_section(monkeypatch):
    _set_required_env(monkeypatch)

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: "some diff")
    monkeypatch.setattr(pr_review, "load_claude_md", lambda *a, **k: "claude.md")
    monkeypatch.setattr(pr_review, "fetch_last_reviewed_sha", lambda *a, **k: None)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not fetch a since-diff on the first review")

    monkeypatch.setattr(pr_review, "fetch_diff_since", fail_if_called)
    monkeypatch.setattr(
        pr_review,
        "call_openrouter",
        lambda api_key, diff, claude_md, since_diff=None: json.dumps(
            {
                "verdict": "green",
                "pr_summary": "does a thing",
                "findings_markdown": "none",
                "changes_since_last_review_markdown": None,
            }
        ),
    )

    posted = {}
    monkeypatch.setattr(
        pr_review,
        "post_comment",
        lambda repo, pr_number, token, body: posted.update(body=body),
    )

    main()

    assert "does a thing" in posted["body"]
    assert "What changed since the last review" not in posted["body"]


def test_main_second_review_fetches_since_diff_and_includes_section(monkeypatch):
    _set_required_env(monkeypatch)

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: "some diff")
    monkeypatch.setattr(pr_review, "load_claude_md", lambda *a, **k: "claude.md")
    monkeypatch.setattr(pr_review, "fetch_last_reviewed_sha", lambda *a, **k: "old-sha")

    since_calls = []

    def fake_fetch_diff_since(repo, prev_sha, head_sha, token):
        since_calls.append((prev_sha, head_sha))
        return "+ fixed the bug"

    monkeypatch.setattr(pr_review, "fetch_diff_since", fake_fetch_diff_since)
    monkeypatch.setattr(
        pr_review,
        "call_openrouter",
        lambda api_key, diff, claude_md, since_diff=None: json.dumps(
            {
                "verdict": "green",
                "pr_summary": "does a thing",
                "findings_markdown": "none",
                "changes_since_last_review_markdown": "fixed the earlier bug" if since_diff else None,
            }
        ),
    )

    posted = {}
    monkeypatch.setattr(
        pr_review,
        "post_comment",
        lambda repo, pr_number, token, body: posted.update(body=body),
    )

    main()

    assert since_calls == [("old-sha", "head-sha")]
    assert "fixed the earlier bug" in posted["body"]
