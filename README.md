# Chinese Story Generator

A backend application that imports Chinese vocabulary from Skritter, stores it
in PostgreSQL, and will generate personalised stories from that vocabulary.

## Current capabilities

- Import vocabulary lists and vocabulary items from Skritter.
- Store vocabulary, list membership, sync history, raw API payloads, and saved
  stories in PostgreSQL.
- Manage the database schema with SQLAlchemy models and Alembic migrations.
- Run a FastAPI application with a health endpoint at `/health`.

Story generation and the main data API are the next milestones.

## How the application is organised

```text
Frontend or API client → FastAPI routes → services → PostgreSQL
                                          ↓
                                    external APIs, such as Skritter
```

The modules have deliberately separate responsibilities:

- **`main.py`** creates the FastAPI application. It is the web server entry
  point, not the place for ingestion or database business logic.
- **`story_generator/api`** will contain HTTP routes. Routes validate a request,
  call a service, and return JSON; they should stay thin.
- **`story_generator/ingestion`** contains the Skritter client and the
  vocabulary-import workflow.
- **`story_generator/database`** contains shared SQLAlchemy setup: the
  declarative base, database engine, and session factory.
- **`story_generator/vocabulary/persistence`** contains vocabulary ORM mappings
  and PostgreSQL persistence operations.
- **`story_generator/ingestion/persistence`** contains sync-run audit mappings
  and persistence operations.
- **`story_generator/vocabulary`** contains vocabulary-specific parsing and
  domain data structures.
- **`story_generator/cli/ingestion.py`** is the manual command-line entry point for a
  vocabulary sync.

### Client, repository, and service

- **Skritter client:** makes authenticated HTTP requests to the Skritter API.
  It does not write to the database.
- **Repository:** reads and writes PostgreSQL data. It does not make HTTP
  requests.
- **Service:** coordinates a workflow. For a vocabulary sync, it gets data from
  the client, parses it, asks the repository to persist it, and controls the
  transaction outcome.

## Setup

This project uses Python 3.12 and PostgreSQL.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Runtime dependencies and the `dev` test extra are defined in
`pyproject.toml`.

Create a `.env` file in the project root. Do not commit it.

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/chinese_story_generator
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/chinese_story_generator_test
SKRITTER_ACCESS_TOKEN=your-token
```

`TEST_DATABASE_URL` must point to a separate database whose name includes
`test`. The test suite refuses to use the development database.

## Run the API

```bash
.venv/bin/python -m uvicorn main:app --reload
```

Open <http://127.0.0.1:8000/health>. A healthy application returns:

```json
{"status": "ok"}
```

FastAPI also provides interactive API documentation at
<http://127.0.0.1:8000/docs> once routes are added.

## Database migrations

Alembic keeps the database schema versioned in `alembic/versions`.

```bash
# Apply all migrations to the database named by DATABASE_URL
.venv/bin/alembic upgrade head

# Check whether the SQLAlchemy models differ from the applied schema
.venv/bin/alembic check
```

Generate a migration only after changing SQLAlchemy models, then inspect the
generated migration before applying it:

```bash
.venv/bin/alembic revision --autogenerate -m "describe the change"
```

## Run a vocabulary import

Apply migrations first, then import either one list or every list available to
the configured Skritter account:

```bash
.venv/bin/python -m story_generator.cli.ingestion --list-id YOUR_LIST_ID
.venv/bin/python -m story_generator.cli.ingestion --all
```

The importer is designed to be idempotent: importing the same vocabulary and
list membership again should not create duplicate records.

## Run tests

Run fast unit and API tests that do not need PostgreSQL:

```bash
.venv/bin/python -m pytest -m "not db"
```

Run database integration tests against `TEST_DATABASE_URL`:

```bash
.venv/bin/python -m pytest -m db
```

## Project roadmap

The detailed goals and learning outcomes are in [docs/milestones.md](docs/milestones.md).
The current focus is Milestone 2: exposing vocabulary, lists, stories, and
sync status through a maintainable FastAPI application.
