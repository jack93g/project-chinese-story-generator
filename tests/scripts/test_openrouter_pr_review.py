import io
import json
import urllib.error

import pytest

import scripts.openrouter_pr_review as pr_review
from scripts.openrouter_pr_review import (
    call_openrouter,
    diff_file_path,
    env,
    extract_json_object,
    fetch_diff_since,
    fetch_last_reviewed_sha,
    fetch_pr_diff,
    file_priority,
    fit_diff_to_budget,
    load_claude_md,
    main,
    parse_review,
    post_comment,
    render_comment,
    split_diff_by_file,
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


def _file_diff(path: str, body_chars: int) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1 @@\n"
        f"+{'x' * body_chars}\n"
    )


def test_split_diff_by_file_splits_on_git_headers():
    first = _file_diff("a.py", 5)
    second = _file_diff("b.py", 5)
    assert split_diff_by_file(first + second) == [first, second]


def test_split_diff_by_file_ignores_diff_git_text_mid_line():
    section = _file_diff("a.py", 0).replace("+\n", "+see diff --git usage\n")
    assert split_diff_by_file(section) == [section]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (
            "diff --git a/story_generator/x.py b/story_generator/x.py",
            "story_generator/x.py",
        ),
        ("diff --git a/old.py b/new.py", "new.py"),
        ("diff --git a/dir b/file.py b/dir b/file.py", "dir b/file.py"),
        ('diff --git "a/docs/some file.md" "b/docs/some file.md"', "docs/some file.md"),
    ],
)
def test_diff_file_path_reads_post_change_path(header, expected):
    assert diff_file_path(header + "\nindex 1..2\n") == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("main.py", 0),
        ("story_generator/api/routers/auth.py", 0),
        ("alembic/versions/0007_add_users.py", 0),
        ("scripts/openrouter_pr_review.py", 0),
        ("frontend/app/login/page.tsx", 0),
        ("frontend/lib/api.ts", 0),
        ("pyproject.toml", 1),
        ("Dockerfile", 1),
        (".github/workflows/deploy-backend.yml", 1),
        ("tests/api/test_auth.py", 2),
        ("tests/conftest.py", 2),
        ("frontend/app/page.test.tsx", 2),
        ("frontend/lib/api.test.ts", 2),
        ("CLAUDE.md", 3),
        ("frontend/README.md", 3),
        ("docs/runbook.md", 3),
        ("docs/diagram.png", 3),
        ("frontend/package-lock.json", 3),
    ],
)
def test_file_priority_ranks_source_then_other_then_tests_then_docs(path, expected):
    assert file_priority(path) == expected


def test_fit_diff_to_budget_leaves_diff_under_cap_untouched():
    diff = _file_diff("README.md", 10) + _file_diff("story_generator/x.py", 10)
    assert fit_diff_to_budget(diff, len(diff)) == (diff, [])


def test_fit_diff_to_budget_keeps_source_over_alphabetically_earlier_docs():
    docs = _file_diff("CLAUDE.md", 100) + _file_diff("docs/runbook.md", 100)
    source = _file_diff("story_generator/api/routers/auth.py", 100)
    test = _file_diff("tests/api/test_auth.py", 100)
    diff = docs + source + test

    result, omitted = fit_diff_to_budget(diff, len(source) + len(test))

    assert result.startswith(source + test)
    assert omitted == ["CLAUDE.md", "docs/runbook.md"]
    assert "2 file(s) omitted" in result
    assert "- CLAUDE.md\n- docs/runbook.md\n]" in result
    assert "x" * 100 not in result.split(test, 1)[1]


def test_fit_diff_to_budget_drops_tests_before_config():
    config = _file_diff("Dockerfile", 100)
    test = _file_diff("tests/test_x.py", 100)

    result, omitted = fit_diff_to_budget(config + test, len(config) + 10)

    assert result.startswith(config)
    assert omitted == ["tests/test_x.py"]


def test_fit_diff_to_budget_drops_tests_before_source():
    source = _file_diff("story_generator/x.py", 100)
    test = _file_diff("tests/test_x.py", 100)

    result, omitted = fit_diff_to_budget(test + source, len(source) + 10)

    assert result.startswith(source)
    assert omitted == ["tests/test_x.py"]


def test_fit_diff_to_budget_skips_file_that_does_not_fit_but_keeps_smaller_later_ones():
    big = _file_diff("story_generator/big.py", 500)
    small = _file_diff("story_generator/small.py", 10)
    readme = _file_diff("README.md", 10)
    budget = len(small) + len(readme) + 50

    result, omitted = fit_diff_to_budget(big + small + readme, budget)

    assert result.startswith(small + readme)
    assert omitted == ["story_generator/big.py"]


def test_fit_diff_to_budget_kept_files_stay_within_budget():
    sections = [_file_diff(f"story_generator/m{i}.py", 100) for i in range(10)]
    budget = len(sections[0]) * 3 + 5

    result, omitted = fit_diff_to_budget("".join(sections), budget)

    kept = result.split("\n... [", 1)[0]
    assert len(kept) <= budget
    assert len(omitted) == 7
    assert omitted == [f"story_generator/m{i}.py" for i in range(3, 10)]


def test_fit_diff_to_budget_falls_back_to_line_cut_for_a_single_file():
    diff = _file_diff("story_generator/huge.py", 500)

    result, omitted = fit_diff_to_budget(diff, 100)

    assert result.endswith("[truncated, too large to review in full]")
    assert omitted == []


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
    return json.dumps(
        {"choices": [{"message": {"content": json.dumps(payload)}}]}
    ).encode()


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
        lambda request, timeout=None: _FakeResponse(
            json.dumps({"unexpected": "shape"}).encode()
        ),
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

    assert (
        json.loads(call_openrouter("fake-key", "diff", "claude.md contents"))["verdict"]
        == "green"
    )


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

    result, omitted = fetch_pr_diff("owner/repo", "43", "token")

    assert captured["url"] == "https://api.github.com/repos/owner/repo/pulls/43"
    assert captured["accept"] == "application/vnd.github.v3.diff"
    assert result.endswith("[truncated, too large to review in full]")
    assert omitted == []


def test_fetch_diff_since_builds_compare_url(monkeypatch):
    captured = {}

    def fake_github_request(url, token, accept):
        captured["url"] = url
        captured["accept"] = accept
        return b"diff --git a/foo b/foo\n+world\n"

    monkeypatch.setattr(pr_review, "github_request", fake_github_request)

    result = fetch_diff_since("owner/repo", "abc123", "def456", "token")

    assert (
        captured["url"]
        == "https://api.github.com/repos/owner/repo/compare/abc123...def456"
    )
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
    comments = [
        {"user": {"login": "github-actions[bot]"}, "body": "just a regular comment"}
    ]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") is None


def test_fetch_last_reviewed_sha_returns_most_recent_marker(monkeypatch):
    bot = {"login": "github-actions[bot]"}
    comments = [
        {
            "user": bot,
            "body": f"### 🟡 DeepSeek review\n...\n{pr_review.REVIEW_MARKER_PREFIX}aaaaaaa -->",
        },
        {"user": {"login": "a-human"}, "body": "a human reply in between"},
        {
            "user": bot,
            "body": f"### 🟢 DeepSeek review\n...\n{pr_review.REVIEW_MARKER_PREFIX}bbbbbbb -->",
        },
    ]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") == "bbbbbbb"


def test_fetch_last_reviewed_sha_ignores_marker_from_non_bot_commenter(monkeypatch):
    comments = [
        {
            "user": {"login": "some-collaborator"},
            "body": f"nice work! {pr_review.REVIEW_MARKER_PREFIX}spoofed1 -->",
        }
    ]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") is None


def test_fetch_last_reviewed_sha_uses_last_marker_not_first(monkeypatch):
    # A prompt-injected diff could trick the model into writing marker-shaped
    # text inside its own findings; the real marker is always the one this
    # script itself appends last, so that's the one that must win.
    bot = {"login": "github-actions[bot]"}
    injected_body = (
        f"**Findings:** the diff tried to sneak in {pr_review.REVIEW_MARKER_PREFIX}facade00 -->\n"
        f"...\n{pr_review.REVIEW_MARKER_PREFIX}dead0000 -->"
    )
    comments = [{"user": bot, "body": injected_body}]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") == "dead0000"


def test_fetch_last_reviewed_sha_rejects_malformed_sha(monkeypatch):
    bot = {"login": "github-actions[bot]"}
    comments = [
        {"user": bot, "body": f"{pr_review.REVIEW_MARKER_PREFIX}not a real sha -->"}
    ]
    monkeypatch.setattr(
        pr_review, "github_request", lambda *a, **k: json.dumps(comments).encode()
    )
    assert fetch_last_reviewed_sha("owner/repo", "43", "token") is None


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


def test_render_comment_lists_omitted_files():
    review = {
        "verdict": "green",
        "pr_summary": "summary",
        "findings_markdown": "findings",
        "changes_since_last_review_markdown": None,
    }
    comment = render_comment(
        review, "some/model", "abc123", ["docs/runbook.md", "evil`name.md"]
    )
    assert "**Not reviewed**" in comment
    assert "`docs/runbook.md`, `evilname.md`" in comment


def test_render_comment_has_no_not_reviewed_line_when_nothing_omitted():
    review = {
        "verdict": "green",
        "pr_summary": "summary",
        "findings_markdown": "findings",
        "changes_since_last_review_markdown": None,
    }
    assert "Not reviewed" not in render_comment(review, "some/model", "abc123", [])


def test_post_comment_sends_expected_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data)
        return _FakeResponse(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    post_comment("owner/repo", "43", "token", "a fully rendered comment")

    assert (
        captured["url"] == "https://api.github.com/repos/owner/repo/issues/43/comments"
    )
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

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: ("   ", []))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not be called for an empty diff")

    monkeypatch.setattr(pr_review, "load_claude_md", fail_if_called)
    monkeypatch.setattr(pr_review, "fetch_last_reviewed_sha", fail_if_called)
    monkeypatch.setattr(pr_review, "call_openrouter", fail_if_called)
    monkeypatch.setattr(pr_review, "post_comment", fail_if_called)

    main()  # should return quietly instead of calling the fakes above


def test_main_first_review_posts_rendered_comment_without_since_section(monkeypatch):
    _set_required_env(monkeypatch)

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: ("some diff", []))
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
    assert "Not reviewed" not in posted["body"]


def test_main_second_review_fetches_since_diff_and_includes_section(monkeypatch):
    _set_required_env(monkeypatch)

    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda *a, **k: ("some diff", []))
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
                "changes_since_last_review_markdown": "fixed the earlier bug"
                if since_diff
                else None,
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


def test_main_lists_omitted_files_in_posted_comment(monkeypatch):
    _set_required_env(monkeypatch)

    monkeypatch.setattr(
        pr_review,
        "fetch_pr_diff",
        lambda *a, **k: ("some diff", ["docs/runbook.md"]),
    )
    monkeypatch.setattr(pr_review, "load_claude_md", lambda *a, **k: "claude.md")
    monkeypatch.setattr(pr_review, "fetch_last_reviewed_sha", lambda *a, **k: None)
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

    assert "**Not reviewed**" in posted["body"]
    assert "`docs/runbook.md`" in posted["body"]
