"""Post an automated code review comment on a PR using DeepSeek via OpenRouter.

Run from GitHub Actions (see .github/workflows/openrouter-review.yml). Reads
its configuration from environment variables so it needs no CLI arguments:

    OPENROUTER_API_KEY  OpenRouter API key (repo secret)
    GITHUB_TOKEN        Token with pull-requests: write (Actions provides this)
    GITHUB_REPOSITORY   "owner/repo" (Actions provides this)
    PR_NUMBER           Pull request number to review
    GITHUB_BASE_REF     PR base branch (Actions provides this for pull_request
                         events); CLAUDE.md is read from here, not the PR
                         branch, so a PR can't rewrite the review criteria
                         it's judged against

The PR diff itself is still attacker-controlled text fed to the model, so
its output is a suggestion for a human to weigh, not something acted on
automatically.

Uses only the standard library so the workflow needs no pip install step.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"
MAX_DIFF_CHARS = 60_000
REQUEST_TIMEOUT = 30
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4

REVIEW_SYSTEM_PROMPT = """\
You are an independent code reviewer for a Python/FastAPI backend + Next.js \
frontend project. You are reviewing a pull request diff. Below is the \
project's CLAUDE.md, which documents its architecture and conventions - use \
it to judge whether the change respects the project's layering rules and \
testing conventions.

<CLAUDE.md>
{claude_md}
</CLAUDE.md>

Review the diff for:
- Correctness bugs (logic errors, edge cases, off-by-one, error handling)
- Violations of the router -> service -> repository layering described above
- Missing or inadequate test coverage for the change
- Security issues (injection, secrets, unvalidated input)

Do not comment on formatting or style that a linter would catch. Be concise: \
a short summary line, then a bulleted list of specific findings with file \
names. If you find nothing worth flagging, say so plainly in one sentence.
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
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    diff = github_request(url, token, "application/vnd.github.v3.diff").decode("utf-8")
    return truncate(diff, MAX_DIFF_CHARS)


def load_claude_md(repo: str, token: str, base_ref: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/contents/CLAUDE.md?ref={base_ref}"
    try:
        return github_request(url, token, "application/vnd.github.v3.raw").decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return "(no CLAUDE.md found in this repo)"
        raise


def call_openrouter(api_key: str, diff: str, claude_md: str) -> str:
    system_prompt = REVIEW_SYSTEM_PROMPT.format(claude_md=claude_md)
    body = json.dumps(
        {
            "model": OPENROUTER_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Review this pull request diff:\n\n{diff}"},
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

        try:
            payload = json.loads(raw)
            return payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                f"Unexpected OpenRouter response shape: {raw.decode('utf-8', errors='replace')}"
            ) from error

    raise RuntimeError("unreachable")


def post_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    comment_body = f"### 🤖 DeepSeek review\n\n{body}"
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
    base_ref = os.environ.get("GITHUB_BASE_REF") or "main"

    diff = fetch_pr_diff(repo, pr_number, github_token)
    if not diff.strip():
        print("Empty diff, nothing to review.")
        return

    claude_md = load_claude_md(repo, github_token, base_ref)
    review = call_openrouter(openrouter_api_key, diff, claude_md)
    post_comment(repo, pr_number, github_token, review)
    print("Posted DeepSeek review comment.")


if __name__ == "__main__":
    main()
