# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Python/FastAPI backend that imports a learner's Chinese vocabulary from
Skritter, stores it in PostgreSQL, and generates personalised Chinese
learning stories through a durable, worker-based background workflow. A
Next.js frontend in `frontend/` (see [frontend/CLAUDE.md](frontend/CLAUDE.md))
talks only to this API — never directly to PostgreSQL.

## Commands

Backend (from repo root, Python 3.12+, requires PostgreSQL):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

.venv/bin/alembic upgrade head              # apply migrations (required before running the API)
.venv/bin/python -m uvicorn main:app --reload   # run the API on :8000

.venv/bin/python -m story_generator.cli.generation_worker           # run continuously
.venv/bin/python -m story_generator.cli.generation_worker --once    # process at most one queued request

.venv/bin/sync-skritter --list-id YOUR_LIST_ID   # import one vocabulary list
.venv/bin/sync-skritter --all                    # import every list
```

Tests:

```bash
.venv/bin/python -m pytest -m "not db"      # no PostgreSQL required
.venv/bin/python -m pytest -m db            # integration tests, needs TEST_DATABASE_URL
RUN_SMOKE_TESTS=1 .venv/bin/python -m pytest -m smoke   # live provider calls, real credentials/cost

.venv/bin/python -m pytest tests/generation/test_worker.py::test_name -v   # single test
```

Migrations, after changing an ORM model (they must stay additive/backward-
compatible so a rollback can run older code on the newer schema; see the
migration policy in [docs/runbook.md](docs/runbook.md)):

```bash
.venv/bin/alembic revision --autogenerate -m "describe the change"
.venv/bin/alembic check     # detect drift between models and schema
```

Docker Compose (repo root; runs `db` Postgres 17, `api`, `worker` — the
frontend dev server stays separate):

```bash
docker compose up --build -d                      # start everything
docker compose run --rm api alembic upgrade head  # apply migrations (fresh db has no tables)
docker compose run --rm api sync-skritter --all   # import vocabulary
docker compose exec db createdb -U "$POSTGRES_USER" chinese_story_generator_test   # once, for host-run db tests
docker compose down                               # stop; data persists in the `postgres_data` volume (`down -v` wipes it)
```

Frontend (`cd frontend`): `npm run dev`, `npm run build`, `npm run lint`, `npm run test`.

Environment (`.env` in repo root, never commit it): `DATABASE_URL`,
`TEST_DATABASE_URL` (must contain `test` and differ from `DATABASE_URL` — the
test suite refuses to run otherwise), `SKRITTER_ACCESS_TOKEN`, `OPENAI_API_KEY`,
`OPENAI_PROVIDER_LABEL`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `API_ACCESS_KEY` (required: the API won't start without it;
clients send it as an `X-API-Key` header; only `GET /health` is open),
`CORS_ALLOWED_ORIGINS` (comma-separated browser origins; defaults to the
local Next.js dev server), plus `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB` (used by Compose to create the database and build the
containers' `DATABASE_URL`).

- Database URLs must use the `postgresql+psycopg://` scheme (psycopg 3 is the
  only declared driver; plain `postgresql://` selects psycopg2, which isn't
  installed in the Docker image).
- `.env` URLs use `localhost` for tools run from `.venv` on the host. Compose
  overrides `DATABASE_URL` for `api`/`worker` to use the `db` service host, so
  don't change `.env` for that.
- The password is embedded in the URLs, so keep it URL-safe (letters and
  digits; no `/`, `+`, `=`, `@`).
- The image must never contain secrets (it is published as a public GHCR
  package, so the Droplet can pull it without credentials): `.env` is
  excluded by `.dockerignore` and injected only at runtime via `env_file`.

## Architecture

**Layering (strict, one-directional) — every module in `story_generator/`
follows this:**

```
router (story_generator/api/routers/*) → service → repository → SQLAlchemy/PostgreSQL
```

- **Router**: HTTP ↔ Python only. Validates/parses the request, calls exactly
  one service method, translates domain errors to `HTTPException`. No SQL, no
  business logic.
- **Service**: business rules and orchestration in plain Python objects.
  Raises domain-specific exceptions (e.g. `VocabularyListNotFoundError`).
  Never touches HTTP or writes SQL directly.
- **Repository**: the only layer that speaks SQL/ORM. No business rules.

[docs/architecture.md](docs/architecture.md) traces a full request
end-to-end through these layers and is the reference for how a new endpoint
should be structured.

**Modules** (`story_generator/`):

- `api/` — FastAPI app assembly (`app.py`), routers, request-scoped DB
  dependency (`dependencies.py`).
- `ingestion/` — Skritter client and sync orchestration; retains raw
  API payloads for reprocessing/debugging. Sync is idempotent.
- `vocabulary/` — vocabulary parsing, services, persistence.
- `stories/` — saved-story queries and persistence.
- `generation/` — the story-generation workflow:
  - `providers/` — provider-neutral interface plus adapters (OpenAI-compatible
    chat completions, a `fake` provider for tests). `provider_registry.py`
    holds an explicit allowlist of `(OPENAI_PROVIDER_LABEL, OPENAI_MODEL,
    OPENAI_BASE_URL)` combinations — the worker refuses to start with an
    unreviewed combination, including the code-level OpenAI default. New
    providers/models must be evaluated with
    `story_generator.cli.provider_comparison` and added here deliberately.
  - `vocabulary_selection.py` — deterministic sampling of known vocabulary
    for a request.
  - `worker.py` / `cli/generation_worker.py` — durable worker loop. Multiple
    workers can run safely: claiming a queued request is done at the database
    level so two workers never process the same one, and stale `running`
    requests are reclaimed at startup and then every few minutes. SIGTERM
    stops the worker after its current request (Compose gives it 90s). Requests move
    `queued → running → succeeded|failed`, with up to 3 attempts and a retry
    endpoint for failed ones.
  - `redaction.py` — redacts provider request/response payloads before they
    are persisted for debugging.
  - `validation.py` — validates generated stories actually cover the
    requested vocabulary.
- `database/` — shared SQLAlchemy engine/session setup (`base.py`,
  `session.py`).
- `cli/` — `ingestion` (Skritter sync), `generation_worker`,
  `provider_comparison` (evaluate a provider against a fixed eval set before
  allowlisting it, without touching the application database).

**Core data model**: `vocabulary_items` (shared, normalised) and
`vocabulary_lists`/`list_vocabulary` (Skritter list membership), `sync_runs` +
`raw_skritter_payloads` (ingestion audit trail), `story_generation_requests` +
`raw_generation_payloads` (generation lifecycle/debug trail), `stories` +
`story_vocabulary_items` (generated output).

## Deployment

Production is one DigitalOcean Droplet running the Compose stack plus Caddy
(`docker-compose.prod.yml`, layered on `docker-compose.yml`; it requires
`IMAGE_TAG` set to a git SHA). Merging to `main` runs
`.github/workflows/deploy-backend.yml`: build and push a SHA-tagged image to
GHCR, then SSH to the Droplet, where `scripts/droplet-deploy.sh` migrates
first and then recreates `api` and `worker`. Rollback is the same workflow
with an older SHA.

- `scripts/droplet-deploy.sh` and `scripts/db-backup.sh` run on the Droplet as
  hand-installed copies, so changes to them need copying over after merge
  (see the runbook).
- `infra/terraform/cloud-init.yaml` must stay plain ASCII.
- Docs: [docs/droplet-setup.md](docs/droplet-setup.md) (how the server is built),
  [docs/runbook.md](docs/runbook.md) (operating procedures).

## Testing conventions

- `tests/conftest.py` provides `db_session` (each test wrapped in a
  transaction that's rolled back afterward — tests never leak data) and
  `client` (a `TestClient` with `get_db` overridden to use `db_session`).
  `two_sessions` is a deliberate exception for tests proving cross-session
  commit/rollback behavior (e.g. claiming logic) and truncates tables itself.
- Tests are marked `db` (needs PostgreSQL, via `TEST_DATABASE_URL`) or
  `smoke` (live provider calls, skipped unless `RUN_SMOKE_TESTS=1`); unmarked
  tests run without any external dependency.
- `TEST_DATABASE_URL` is validated at first use (not import time) so
  `pytest -m "not db"` runs without PostgreSQL configured at all.
