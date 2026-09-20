"""Post an automated code review comment on a PR using DeepSeek via OpenRouter.

Run from GitHub Actions (see .github/workflows/openrouter-review.yml). Reads
its configuration from environment variables so it needs no CLI arguments:

    OPENROUTER_API_KEY  OpenRouter API key (repo secret)
    GITHUB_TOKEN        Token with pull-requests: write (Actions provides this)
    GITHUB_REPOSITORY   "owner/repo" (Actions provides this)
    PR_NUMBER           Pull request number to review
    PR_HEAD_SHA         SHA of the PR's head commit (Actions provides this)
    GITHUB_BASE_REF     PR base branch (Actions provides this for pull_request
                         events); CLAUDE.md is read from here, not the PR
                         branch, so a PR can't rewrite the review criteria
                         it's judged against

The model is prompted to return a small JSON object (verdict/summary/
findings) which is rendered into a fixed comment template here, rather than
trusting it to produce well-formed markdown directly. Each posted comment
carries a hidden `<!-- deepseek-review-sha: ... -->` marker with the SHA it
reviewed; on a later push, the previous marker is used to also diff and
summarize what changed since that last review.

The PR diff itself is still attacker-controlled text fed to the model, so
its output is a suggestion for a human to weigh, not something acted on
automatically. The workflow checks out the PR's base SHA (not the PR's own
code) before running this script, so a PR cannot modify the script itself
to exfiltrate the secrets in its environment.

Uses only the standard library so the workflow needs no pip install step.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
# Verified against OpenRouter's live /models catalog on 2026-09-11.
OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"
MAX_DIFF_CHARS = 60_000
REQUEST_TIMEOUT = 30
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4

REVIEW_MARKER_PREFIX = "<!-- deepseek-review-sha: "
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{7,40}")
VERDICT_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

REVIEW_SYSTEM_PROMPT = """\
You are an independent code reviewer for a Python/FastAPI backend + Next.js \
frontend project, reviewing a pull request diff. Below is the project's \
CLAUDE.md, documenting its architecture and conventions - use it to judge \
whether the change respects the layering rules and testing conventions.

<CLAUDE.md>
{claude_md}
</CLAUDE.md>

Review the diff for:
- Correctness bugs (logic errors, edge cases, off-by-one, error handling)
- Violations of the router -> service -> repository layering described above
- Missing or inadequate test coverage for the change
- Security issues (injection, secrets, unvalidated input)

Do not comment on formatting or style a linter would catch.

The user message may also include a second diff showing what changed since \
a previous review of this same PR. If it does, use it to fill in \
"changes_since_last_review_markdown" below, focused on whether it addresses \
issues a reviewer would have raised on the first diff. If it doesn't, set \
that field to null.

Respond with ONLY a single JSON object, no markdown code fence and no prose \
outside it, with exactly these keys:
{{
  "verdict": "green" | "yellow" | "red",
  "pr_summary": string, 1-3 plain sentences on what this PR does,
  "findings_markdown": string, a markdown bullet list of specific findings \
with file names, or one sentence saying none were found,
  "changes_since_last_review_markdown": string or null, per the rule above
}}

verdict guide: green = nothing worth a human's attention; yellow = minor \
issues or missing tests, not blocking; red = a correctness bug, security \
issue, or clear layering violation.
"""


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind("\n", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars
    return text[:cutoff] + "\n\n... [truncated, too large to review in full]"


def github_request(url: str, token: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def fetch_pr_diff(repo: str, pr_number: str, token: str) -> str:
    if not pr_number.isdigit():
        raise ValueError(f"PR_NUMBER must be numeric, got: {pr_number!r}")
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    diff = github_request(url, token, "application/vnd.github.v3.diff").decode("utf-8")
    return truncate(diff, MAX_DIFF_CHARS)


def fetch_diff_since(repo: str, prev_sha: str, head_sha: str, token: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/compare/{prev_sha}...{head_sha}"
    diff = github_request(url, token, "application/vnd.github.v3.diff").decode("utf-8")
    return truncate(diff, MAX_DIFF_CHARS)


def load_claude_md(repo: str, token: str, base_ref: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/contents/CLAUDE.md?ref={urllib.parse.quote(base_ref, safe='')}"
    try:
        return github_request(url, token, "application/vnd.github.v3.raw").decode(
            "utf-8"
        )
    except urllib.error.HTTPError as error:
        if error.code == 404:
            print(
                f"Warning: no CLAUDE.md found at ref {base_ref!r}, "
                "reviewing without repo-specific context.",
                file=sys.stderr,
            )
            return "(no CLAUDE.md found in this repo)"
        raise


def fetch_last_reviewed_sha(repo: str, pr_number: str, token: str) -> str | None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments?per_page=100"
    comments = json.loads(github_request(url, token, "application/vnd.github+json"))
    for comment in reversed(comments):
        # Only trust comments actually posted by this workflow's token - anyone
        # with comment access could otherwise write a fake marker themselves.
        if (comment.get("user") or {}).get("login") != "github-actions[bot]":
            continue
        body = comment.get("body") or ""
        if REVIEW_MARKER_PREFIX not in body:
            continue
        # rsplit, not split: a prompt-injected diff could trick the model into
        # writing marker-shaped text earlier in its own findings. Our real
        # marker is always the one this script appended last.
        tail = body.rsplit(REVIEW_MARKER_PREFIX, 1)[1]
        sha = tail.split("-->", 1)[0].strip()
        if SHA_PATTERN.fullmatch(sha):
            return sha
    return None


def call_openrouter(
    api_key: str, diff: str, claude_md: str, since_diff: str | None = None
) -> str:
    system_prompt = REVIEW_SYSTEM_PROMPT.format(claude_md=claude_md)
    user_content = f"Review this pull request diff:\n\n<diff>\n{diff}\n</diff>"
    if since_diff:
        user_content += (
            "\n\nHere is what changed since the previous review of this PR:"
            f"\n\n<changes_since_last_review>\n{since_diff}\n</changes_since_last_review>"
        )

    body = json.dumps(
        {
            "model": OPENROUTER_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        OPENROUTER_API,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jack93g/project-chinese-story-generator",
            "X-Title": "project-chinese-story-generator PR review",
        },
        method="POST",
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code in RETRY_STATUS_CODES and attempt < MAX_ATTEMPTS:
                wait = 2**attempt
                print(
                    f"OpenRouter API returned {error.code} (attempt {attempt}/{MAX_ATTEMPTS}), "
                    f"retrying in {wait}s: {detail}",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            print(f"OpenRouter API error {error.code}: {detail}", file=sys.stderr)
            raise
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < MAX_ATTEMPTS:
                wait = 2**attempt
                print(
                    f"OpenRouter request failed ({error}) (attempt {attempt}/{MAX_ATTEMPTS}), "
                    f"retrying in {wait}s",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise

        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError(f"content is {type(content).__name__}, not str")
            return content
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                f"Unexpected OpenRouter response shape: {raw.decode('utf-8', errors='replace')}"
            ) from error

    raise RuntimeError("unreachable")


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def parse_review(content: str) -> dict:
    try:
        data = extract_json_object(content)
        verdict = data["verdict"]
        if not isinstance(verdict, str) or verdict.lower() not in VERDICT_EMOJI:
            raise ValueError(f"unexpected verdict: {verdict!r}")
        pr_summary = data["pr_summary"]
        findings_markdown = data["findings_markdown"]
        if not isinstance(pr_summary, str) or not isinstance(findings_markdown, str):
            raise ValueError("pr_summary/findings_markdown must be strings")
        since = data.get("changes_since_last_review_markdown")
        if since is not None and not isinstance(since, str):
            raise ValueError(
                "changes_since_last_review_markdown must be a string or null"
            )
        return {
            "verdict": verdict.lower(),
            "pr_summary": pr_summary,
            "findings_markdown": findings_markdown,
            "changes_since_last_review_markdown": since or None,
        }
    except (json.JSONDecodeError, KeyError, ValueError) as error:
        raise RuntimeError(f"Unexpected review JSON shape: {content}") from error


def render_comment(review: dict, model: str, head_sha: str) -> str:
    emoji = VERDICT_EMOJI[review["verdict"]]
    lines = [
        f"### {emoji} DeepSeek review",
        "",
        f"**Summary:** {review['pr_summary']}",
        "",
        "**Findings:**",
        "",
        review["findings_markdown"],
    ]

    since = review["changes_since_last_review_markdown"]
    if since:
        lines += [
            "",
            "---",
            "",
            "**What changed since the last review:**",
            "",
            since,
        ]

    lines += [
        "",
        "---",
        "",
        "_Automated, unverified output generated from this PR's diff - "
        "weigh it like a first-pass opinion, not a verdict._",
        "",
        f"_Review generated by `{model}` via OpenRouter_",
        f"{REVIEW_MARKER_PREFIX}{head_sha} -->",
    ]
    return "\n".join(lines)


def post_comment(repo: str, pr_number: str, token: str, comment_body: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    request = urllib.request.Request(
        url,
        data=json.dumps({"body": comment_body}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT):
        pass


def main() -> None:
    openrouter_api_key = env("OPENROUTER_API_KEY")
    github_token = env("GITHUB_TOKEN")
    repo = env("GITHUB_REPOSITORY")
    pr_number = env("PR_NUMBER")
    head_sha = env("PR_HEAD_SHA")
    base_ref = os.environ.get("GITHUB_BASE_REF") or "main"

    diff = fetch_pr_diff(repo, pr_number, github_token)
    if not diff.strip():
        print("Empty diff, nothing to review.")
        return

    claude_md = load_claude_md(repo, github_token, base_ref)

    since_diff = None
    last_sha = fetch_last_reviewed_sha(repo, pr_number, github_token)
    if last_sha and last_sha != head_sha:
        try:
            since_diff = (
                fetch_diff_since(repo, last_sha, head_sha, github_token) or None
            )
        except urllib.error.HTTPError as error:
            print(
                f"Warning: could not diff against previous review ({last_sha}): {error}",
                file=sys.stderr,
            )

    content = call_openrouter(openrouter_api_key, diff, claude_md, since_diff)
    review = parse_review(content)
    comment = render_comment(review, OPENROUTER_MODEL, head_sha)
    post_comment(repo, pr_number, github_token, comment)
    print("Posted DeepSeek review comment.")


if __name__ == "__main__":
    main()
