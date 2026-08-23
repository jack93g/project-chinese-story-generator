# Chinese Story Generator

A Python backend for importing Chinese vocabulary from Skritter, browsing it
through an API, and generating Chinese-language learning stories through a
durable background workflow.

## Current capabilities

- Synchronise one or all Skritter vocabulary lists into PostgreSQL.
- Store vocabulary, list membership, sync-run history, and raw Skritter API
  payloads. Re-running an import is idempotent and does not duplicate
  vocabulary or list memberships.
- Serve a FastAPI for vocabulary, vocabulary lists, saved stories, sync
  status, and asynchronous story-generation requests.
- Queue generation requests, select a deterministic vocabulary sample,
  generate a structured story through an OpenAI-compatible provider, validate
  vocabulary coverage, and persist the completed story and its vocabulary
  usage.
- Run one or more durable workers safely: database-level claiming prevents two
  workers from processing the same request. Stale running requests are
  reclaimed when a worker starts.
- Retain redacted provider request/response payloads and generation metadata
  for debugging. Failed requests can be retried up to three attempts.
- Compare OpenAI-compatible providers against a shared evaluation set before
  allowing one to be used by the worker.
- Version the PostgreSQL schema with SQLAlchemy and Alembic.

## API

Start the application and open the interactive documentation at
<http://127.0.0.1:8000/docs>.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Returns `{"status": "ok"}` without requiring database configuration. |
| `GET` | `/vocabulary` | Returns paginated vocabulary items. |
| `GET` | `/vocabulary-lists` | Returns paginated vocabulary-list summaries, including item counts. |
| `GET` | `/vocabulary-lists/{list_id}` | Returns a vocabulary list and its items. |
| `GET` | `/stories` | Returns paginated saved-story summaries. |
| `GET` | `/stories/{story_id}` | Returns a saved story and its selected vocabulary. |
| `GET` | `/sync-status` | Returns the most recent Skritter sync run, or `{"latest_run": null}`. |
| `POST` | `/story-generations` | Queues a story-generation request and returns `202 Accepted`. |
| `GET` | `/story-generations/{generation_request_id}` | Returns the request status and completed story ID, if available. |
| `POST` | `/story-generations/{generation_request_id}/retry` | Requeues an eligible failed request and returns `202 Accepted`. |

The collection endpoints accept `limit` (1–100, default `50`) and `offset`
(default `0`). Unknown story, vocabulary-list, and generation-request IDs
return `404`.

To queue a story, submit a vocabulary list ID, target HSK level (1–6), target
word count (1–1000), requested vocabulary count (1–15), and optionally a
topic. The API returns immediately; a separate worker performs the provider
call. A request moves through `queued` → `running` → `succeeded` or `failed`.
Only failed requests may be retried, and no request may be attempted more than
three times.

## Project structure

```text
API client → FastAPI routes → services → PostgreSQL
                                  ↓
                    Skritter API / OpenAI-compatible provider
```

- `main.py` is the web-server entry point.
- `story_generator/api` contains thin FastAPI routes and request-scoped
  database dependencies.
- `story_generator/ingestion` contains the Skritter client and sync workflow.
- `story_generator/vocabulary` owns vocabulary parsing, services, and
  persistence.
- `story_generator/stories` owns saved-story queries and persistence.
- `story_generator/generation` contains generation request lifecycle,
  vocabulary selection, versioned prompts, provider adapters, validation, and
  the durable worker.
- `story_generator/database` contains shared SQLAlchemy setup.
- `story_generator/cli` provides manual vocabulary sync, generation-worker,
  and provider-comparison commands.

Services coordinate workflows, repositories read and write PostgreSQL, and
external clients make HTTP calls. Keeping these responsibilities separate
makes the import process and API straightforward to test.

## Setup

The project requires Python 3.12+ and PostgreSQL.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Create a `.env` file in the repository root; do not commit it.

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/chinese_story_generator
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/chinese_story_generator_test
SKRITTER_ACCESS_TOKEN=your-token
OPENAI_API_KEY=your-provider-key
# Required for the worker; see “Configure a generation provider”.
OPENAI_PROVIDER_LABEL=groq
OPENAI_MODEL=openai/gpt-oss-120b
OPENAI_BASE_URL=https://api.groq.com/openai/v1/chat/completions
```

`DATABASE_URL` is required by database-backed API endpoints, migrations, and
the importer. `SKRITTER_ACCESS_TOKEN` is required only for a Skritter import.
`TEST_DATABASE_URL` must refer to a separate database whose name includes
`test`; the test suite refuses to use the development database.
`OPENAI_API_KEY` and the three `OPENAI_*` provider settings are required only
by the generation worker and live-provider smoke test.

## Run the API

Apply migrations first, then start the development server:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn main:app --reload
```

Check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

## Generate a story

Start the API and, in a separate terminal, start a worker. The worker can run
continuously or process at most one queued request with `--once`:

```bash
.venv/bin/python -m story_generator.cli.generation_worker
.venv/bin/python -m story_generator.cli.generation_worker --once
```

Queue a request using the ID from `GET /vocabulary-lists`, then poll its
status. Replace `1` with an existing vocabulary-list ID and the returned
generation request ID.

```bash
curl -X POST http://127.0.0.1:8000/story-generations \
  -H 'content-type: application/json' \
  -d '{
    "vocabulary_list_id": 1,
    "target_hsk_level": 2,
    "target_word_count": 150,
    "target_vocabulary_count": 10,
    "topic": "a trip to the market"
  }'

curl http://127.0.0.1:8000/story-generations/1
```

On success, the status response includes `story_id`; retrieve the completed
story at `GET /stories/{story_id}`. A failed request may be requeued while it
has fewer than three attempts:

```bash
curl -X POST http://127.0.0.1:8000/story-generations/1/retry
```

### Configure a generation provider

The worker uses an OpenAI-compatible Chat Completions endpoint. It will start
only when the exact `(OPENAI_PROVIDER_LABEL, OPENAI_MODEL, OPENAI_BASE_URL)`
combination appears in the reviewed allowlist in
`story_generator/generation/providers/provider_registry.py`. This prevents an
unreviewed model or endpoint from being used by accident.

The repository currently approves the Groq example shown in `.env` above.
Although the code defaults to OpenAI's `gpt-4o` endpoint when these settings
are absent, that default is not currently approved and the worker will reject
it until it is evaluated and added to the allowlist.

To evaluate another provider or model, run the comparison harness, review the
generated transcripts, add `manual_quality_notes` to its JSON report, render
the report again, and then add the reviewed report to the allowlist:

```bash
.venv/bin/python -m story_generator.cli.provider_comparison run \
  --provider 'provider-label|https://provider.example/v1/chat/completions|model-name|API_KEY_ENV_VAR'

# Edit manual_quality_notes in the generated JSON report, then:
.venv/bin/python -m story_generator.cli.provider_comparison render \
  --input reports/provider-comparisons/TIMESTAMP.json
```

The comparison command does not write to the application database. For local
OpenAI-compatible servers that do not require a key, the final part of the
provider specification may name an unset environment variable.

## Database migrations

Alembic versions the schema in `alembic/versions`.

```bash
# Apply all migrations using DATABASE_URL
.venv/bin/alembic upgrade head

# Check whether SQLAlchemy metadata differs from the current schema
.venv/bin/alembic check
```

After changing ORM models, create and inspect a migration before applying it:

```bash
.venv/bin/alembic revision --autogenerate -m "describe the change"
```

## Import vocabulary from Skritter

After applying migrations, synchronise either one list or every list available
to the configured Skritter account:

```bash
# Installed command
.venv/bin/sync-skritter --list-id YOUR_LIST_ID
.venv/bin/sync-skritter --all

# Equivalent module invocation
.venv/bin/python -m story_generator.cli.ingestion --list-id YOUR_LIST_ID
.venv/bin/python -m story_generator.cli.ingestion --all
```

Each invocation creates a sync-run audit record. A full sync continues after
an individual list fails, records the failure, and exits with a non-zero
status if any list failed. Raw Skritter responses are retained with the run
for debugging and are deliberately excluded from `/sync-status` responses.

## Run tests

Run tests that do not require PostgreSQL:

```bash
.venv/bin/python -m pytest -m "not db"
```

Run database integration tests against `TEST_DATABASE_URL`:

```bash
.venv/bin/python -m pytest -m db
```

Live provider smoke tests are skipped by default because they require real
credentials and may incur cost. Run them explicitly only after configuring an
approved provider:

```bash
RUN_SMOKE_TESTS=1 .venv/bin/python -m pytest -m smoke
```

## Roadmap

The detailed delivery plan is in [docs/milestones.md](docs/milestones.md).
Vocabulary ingestion, the backend API, and the durable story-generation
workflow are implemented. The next planned product milestone is a frontend
for selecting vocabulary, requesting stories, and reading completed results.
