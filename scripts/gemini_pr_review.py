"""Post an automated code review comment on a PR using the Gemini API.

Run from GitHub Actions (see .github/workflows/gemini-review.yml). Reads
its configuration from environment variables so it needs no CLI arguments:

    GEMINI_API_KEY      Google AI Studio API key (repo secret)
    GITHUB_TOKEN        Token with pull-requests: write (Actions provides this)
    GITHUB_REPOSITORY   "owner/repo" (Actions provides this)
    PR_NUMBER           Pull request number to review

Uses only the standard library so the workflow needs no pip install step.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODEL = "gemini-2.5-flash"
MAX_DIFF_CHARS = 300_000
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


def github_request(url: str, token: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


def fetch_pr_diff(repo: str, pr_number: str, token: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    diff = github_request(url, token, "application/vnd.github.v3.diff").decode("utf-8")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated, too large to review in full]"
    return diff


def load_claude_md() -> str:
    try:
        with open("CLAUDE.md", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(no CLAUDE.md found in this repo)"


def call_gemini(api_key: str, diff: str) -> str:
    system_prompt = REVIEW_SYSTEM_PROMPT.format(claude_md=load_claude_md())
    body = json.dumps(
        {
            "model": GEMINI_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Review this pull request diff:\n\n{diff}"},
            ],
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        GEMINI_API,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read())
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code in RETRY_STATUS_CODES and attempt < MAX_ATTEMPTS:
                wait = 2**attempt
                print(
                    f"Gemini API returned {error.code} (attempt {attempt}/{MAX_ATTEMPTS}), "
                    f"retrying in {wait}s: {detail}",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            print(f"Gemini API error {error.code}: {detail}", file=sys.stderr)
            raise

    raise RuntimeError("unreachable")


def post_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    comment_body = f"### 🤖 Gemini review\n\n{body}"
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
    urllib.request.urlopen(request)


def main() -> None:
    gemini_api_key = env("GEMINI_API_KEY")
    github_token = env("GITHUB_TOKEN")
    repo = env("GITHUB_REPOSITORY")
    pr_number = env("PR_NUMBER")

    diff = fetch_pr_diff(repo, pr_number, github_token)
    if not diff.strip():
        print("Empty diff, nothing to review.")
        return

    review = call_gemini(gemini_api_key, diff)
    post_comment(repo, pr_number, github_token, review)
    print("Posted Gemini review comment.")


if __name__ == "__main__":
    main()
