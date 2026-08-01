# Chinese Story Generator

A Python backend for importing Chinese vocabulary from Skritter, browsing the
imported vocabulary and saved stories through an API, and laying the durable
foundation for AI-assisted story generation.

## Current capabilities

- Synchronise one or all Skritter vocabulary lists into PostgreSQL.
- Store vocabulary, list membership, sync-run history, and raw Skritter API
  payloads. Re-running an import is idempotent and does not duplicate
  vocabulary or list memberships.
- Serve a FastAPI read API for vocabulary, vocabulary lists, saved stories,
  and the latest sync status.
- Persist saved stories and their selected vocabulary.
- Persist story-generation requests and enforce their lifecycle
  (`queued` → `running` → `succeeded` or `failed`, with failed requests
  retryable). Generation payload persistence redacts secret-like fields.
- Version the PostgreSQL schema with SQLAlchemy and Alembic.

The repository does not yet expose story-generation endpoints, run a
generation worker, or call an LLM provider. Those are the remaining parts of
the story-generation milestone.

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

The collection endpoints accept `limit` (1–100, default `50`) and `offset`
(default `0`). Unknown story and vocabulary-list IDs return `404`.

## Project structure

```text
API client → FastAPI routes → services → PostgreSQL
                                  ↓
                         Skritter API / future LLM provider
```

- `main.py` is the web-server entry point.
- `story_generator/api` contains thin FastAPI routes and request-scoped
  database dependencies.
- `story_generator/ingestion` contains the Skritter client and sync workflow.
- `story_generator/vocabulary` owns vocabulary parsing, services, and
  persistence.
- `story_generator/stories` owns saved-story queries and persistence.
- `story_generator/generation` contains the durable generation-request
  lifecycle and redaction logic; it is not yet an API or worker.
- `story_generator/database` contains shared SQLAlchemy setup.
- `story_generator/cli/ingestion.py` provides the manual sync command.

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
```

`DATABASE_URL` is required by database-backed API endpoints, migrations, and
the importer. `SKRITTER_ACCESS_TOKEN` is required only for a Skritter import.
`TEST_DATABASE_URL` must refer to a separate database whose name includes
`test`; the test suite refuses to use the development database.

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

## Roadmap

The detailed delivery plan is in [docs/milestones.md](docs/milestones.md).
Vocabulary ingestion and the read API are implemented. The current work is
Milestone 3: completing the provider-backed, asynchronous story-generation
workflow and its API.
