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
  reclaimed at worker startup and every few minutes after, and a stopping
  worker finishes its current request first.
- Retain redacted provider request/response payloads and generation metadata
  for debugging. Failed requests can be retried up to three attempts.
- Compare OpenAI-compatible providers against a shared evaluation set before
  allowing one to be used by the worker.
- Version the PostgreSQL schema with SQLAlchemy and Alembic.
- Run PostgreSQL, migrations, the API, and the worker locally with one
  `docker compose up` (see [Quick start](#quick-start-with-docker-compose)).
- Deploy to a single DigitalOcean Droplet from GitHub Actions, with
  SHA-tagged images, migrations before each release, one-step rollback, and
  encrypted database backups (see [Deployment and operations](#deployment-and-operations)).

## API

Start the application and open the interactive documentation at
<http://127.0.0.1:8000/docs>.

Every endpoint except `/health` and the login/logout endpoints needs one of
two credentials:

- **A session cookie**, which is how the browser frontend authenticates. Log in
  with `POST /auth/login` using an account created with `manage-users` (see
  [Login accounts](#login-accounts)). The cookie is `HttpOnly`, `Secure` and
  `SameSite=Lax`, and it lasts 30 days unless you log out first. A write
  (`POST`/`DELETE`) authenticated by the cookie must also come from an origin
  listed in `CORS_ALLOWED_ORIGINS`.
- **An `X-API-Key` header** matching `API_ACCESS_KEY` from your `.env`, for
  scripts and `curl`. The API refuses to start if that variable is unset.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Returns `{"status": "ok"}` without requiring database configuration or an API key. |
| `POST` | `/auth/login` | Checks `{"username", "password"}` and sets the session cookie. `401` for a wrong username or password; limited to 10 attempts a minute (`429`). |
| `POST` | `/auth/logout` | Ends the current session and clears the cookie. Returns `204 No Content`. |
| `GET` | `/auth/me` | Returns `{"username"}` for the logged-in session; `401` otherwise (including for API-key requests, which have no user). |
| `GET` | `/vocabulary` | Returns paginated vocabulary items. |
| `GET` | `/vocabulary-lists` | Returns paginated vocabulary-list summaries, including item counts. |
| `GET` | `/vocabulary-lists/{list_id}` | Returns a vocabulary list and its items. |
| `GET` | `/stories` | Returns paginated saved-story summaries. |
| `GET` | `/stories/{story_id}` | Returns a saved story and its selected vocabulary. |
| `DELETE` | `/stories/{story_id}` | Permanently deletes a saved story and its vocabulary associations. Returns `204 No Content`. |
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
- `Dockerfile` builds the image shared by the API, worker, and migration
  services; `docker-compose.yml` wires those together with PostgreSQL, and
  `.dockerignore` keeps `.env` and local artefacts out of the image.
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
- `scripts/` holds the production deploy, backup, and restore scripts that
  run on the Droplet.
- `infra/terraform` defines the Droplet, firewall, SSH key, and DNS record.
- `docs/` holds the architecture, deployment decisions, server setup, and
  operations runbook.

Services coordinate workflows, repositories read and write PostgreSQL, and
external clients make HTTP calls. Keeping these responsibilities separate
makes the import process and API straightforward to test.

## Quick start with Docker Compose

One command starts PostgreSQL, applies migrations, and runs the API and the
generation worker. You need [Docker](https://docs.docker.com/get-docker/) and
nothing else installed. (The frontend dev server runs separately; see
[Frontend](#frontend).)

1. Create a `.env` file in the repository root; do not commit it.

   ```dotenv
   # Used by Docker Compose to create the database and build the containers' DATABASE_URL.
   POSTGRES_USER=story
   POSTGRES_PASSWORD=choose-a-letters-and-digits-password
   POSTGRES_DB=chinese_story_generator

   SKRITTER_ACCESS_TOKEN=your-token
   OPENAI_API_KEY=your-provider-key
   OPENAI_PROVIDER_LABEL=groq
   OPENAI_MODEL=openai/gpt-oss-120b
   OPENAI_BASE_URL=https://api.groq.com/openai/v1/chat/completions

   # Required: scripts and curl send this as the X-API-Key header (the
   # browser logs in instead); the API refuses to start without it.
   API_ACCESS_KEY=choose-a-random-key
   ```

   The password is embedded in database URLs, so use only letters and digits
   (no `/`, `+`, `=`, `@`). Add the two host-side URLs from [Setup](#setup)
   only if you also want to run tools or tests from a local `.venv`.

2. Start everything:

   ```bash
   docker compose up --build -d
   ```

   A one-shot `migrate` service applies the Alembic migrations once
   PostgreSQL is healthy; the API and worker start only after it succeeds.
   Check with `docker compose ps -a` (`migrate` should show `Exited (0)`).

3. Import your vocabulary from Skritter (safe to repeat):

   ```bash
   docker compose run --rm api sync-skritter --all
   ```

4. Create a login for the frontend (it prompts for the password):

   ```bash
   docker compose run --rm api manage-users create yourname
   ```

5. Generate a story. Follow [Generate a story](#generate-a-story) starting from
   the `curl` commands (the API is on `http://127.0.0.1:8000` and the worker is
   already running), then read the result at `GET /stories/{story_id}`. To read
   it in the browser instead, start the frontend as described in
   [Frontend](#frontend).

Useful commands:

```bash
docker compose logs -f worker    # follow the worker
docker compose down              # stop; data is kept in the postgres_data volume
docker compose down -v           # stop AND DELETE all database data
```

The image never contains secrets: `.env` is excluded by `.dockerignore` and
supplied to the containers only at runtime. PostgreSQL is also published on
`127.0.0.1:5432` for local tools, so stop any other PostgreSQL using that port.

## Setup

Use this section to run the API, worker, and tests directly from a local
Python environment instead of Docker. It requires Python 3.12+ and a
PostgreSQL server (the Docker `db` service works: `docker compose up -d db`).

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
API_ACCESS_KEY=choose-a-random-key
```

Use the `postgresql+psycopg://` scheme (plain `postgresql://` selects a
different driver that is not installed). When using the Docker database, use
the same user, password and database name as `POSTGRES_*` in your `.env`, with
host `localhost`; the containers get their own `DATABASE_URL` from Compose.

`DATABASE_URL` is required by database-backed API endpoints, migrations, and
the importer. `SKRITTER_ACCESS_TOKEN` is required only for a Skritter import.
`TEST_DATABASE_URL` must refer to a separate database whose name includes
`test`; the test suite refuses to use the development database.
`OPENAI_API_KEY` and the three `OPENAI_*` provider settings are required only
by the generation worker and live-provider smoke test. `API_ACCESS_KEY` is
required by the API itself — it refuses to start without it.
`SESSION_COOKIE_SECURE` (optional, default `true`) can be set to `false` if
your browser won't keep the Secure login cookie from `http://localhost`;
never set it in production.

## Run the API

If you are using Docker Compose, the API is already running on port 8000 and
you can skip this section. To run it directly from your `.venv` instead, apply
migrations first, then start the development server:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn main:app --reload
```

Check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

## Login accounts

The frontend asks you to log in. There is no sign-up page: create accounts
from the command line. The password is prompted for (at least 12 characters)
rather than passed as an argument, so it stays out of shell history.

```bash
.venv/bin/manage-users create yourname
.venv/bin/manage-users set-password yourname   # also logs out all of its sessions
```

With Docker Compose, prefix these with `docker compose run --rm api` and drop
the `.venv/bin/`. Every account sees the same vocabulary and stories: the login
is a gate, not separate user data.

## Generate a story

With Docker Compose the worker is already running, so go straight to the
`curl` commands below. Otherwise, start the API and, in a separate terminal,
start a worker. The worker can run continuously or process at most one queued
request with `--once`:

```bash
.venv/bin/python -m story_generator.cli.generation_worker
.venv/bin/python -m story_generator.cli.generation_worker --once
```

`--stale-after-minutes` (default 15) and `--reclaim-interval-minutes`
(default 5) control when a request left `running` by a crashed worker is
requeued. Ctrl-C or SIGTERM stops the worker after its current request.

Queue a request using the ID from `GET /vocabulary-lists`, then poll its
status. Replace `1` with an existing vocabulary-list ID and the returned
generation request ID.

```bash
curl -X POST http://127.0.0.1:8000/story-generations \
  -H 'content-type: application/json' \
  -H "X-API-Key: $API_ACCESS_KEY" \
  -d '{
    "vocabulary_list_id": 1,
    "target_hsk_level": 2,
    "target_word_count": 150,
    "target_vocabulary_count": 10,
    "topic": "a trip to the market"
  }'

curl http://127.0.0.1:8000/story-generations/1 -H "X-API-Key: $API_ACCESS_KEY"
```

On success, the status response includes `story_id`; retrieve the completed
story at `GET /stories/{story_id}`. A failed request may be requeued while it
has fewer than three attempts:

```bash
curl -X POST http://127.0.0.1:8000/story-generations/1/retry -H "X-API-Key: $API_ACCESS_KEY"
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

When using Docker Compose, the `migrate` service applies pending migrations
automatically on every `docker compose up`. To apply them manually:

```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic current    # current revision
```

After changing ORM models, create and inspect a migration before applying it.
Create it from your local `.venv`, not with `docker compose run`: the image
holds a build-time copy of `alembic/`, so a file generated in a throwaway
container never reaches your working tree.

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

### Test database with Docker

Database tests run from your local `.venv` (not inside a container) against a
separate, empty database whose name contains `test`. Docker Compose only
creates `POSTGRES_DB`, so create the test database once:

```bash
docker compose up -d db
docker compose exec db createdb -U <POSTGRES_USER> chinese_story_generator_test
```

Then set `TEST_DATABASE_URL` in `.env` with the same user and password as
`DATABASE_URL`, host `localhost`, and the `_test` database name (see
[Setup](#setup)). You never migrate the test database by hand: the test
fixtures apply the migrations when the session starts and roll back each test.

`docker compose down -v` deletes the test database along with the dev one, so
create it again afterwards. `pytest -m "not db"` needs none of this.

Live provider smoke tests are skipped by default because they require real
credentials and may incur cost. Run them explicitly only after configuring an
approved provider:

```bash
RUN_SMOKE_TESTS=1 .venv/bin/python -m pytest -m smoke
```

## Deployment and operations

Merging to `main` builds an image tagged with the commit SHA, pushes it to
GHCR, and deploys it to a single DigitalOcean Droplet: migrations run first,
then the API and worker restart on the new image. Rolling back redeploys an
older SHA through the same workflow.

- [docs/droplet-setup.md](docs/droplet-setup.md): how the server is built,
  by hand and with Terraform.
- [docs/runbook.md](docs/runbook.md): how to deploy, roll back, restart the
  worker, debug failed generations, back up and restore the database, rotate
  secrets, and patch.

Schema migrations must stay backward-compatible (add, don't rename or drop)
so a rollback can run older code against the newer schema; see the runbook's
migration policy.

## Frontend

A Next.js frontend lives in [frontend/](frontend/README.md). It talks only to
the FastAPI endpoints above — see that README for setup and for the commands
to run the API, worker, and frontend together.

