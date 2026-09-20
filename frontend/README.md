## Chinese Story Generator — frontend

A Next.js (App Router) frontend for the story-generation API in the parent
repository. It never talks to PostgreSQL directly; every data access goes
through the FastAPI backend.

## Setup

Requires Node.js 20+.

```bash
npm install
cp .env.example .env.local
```

`.env.local` sets `NEXT_PUBLIC_API_BASE_URL`, the base URL of the FastAPI
backend. It defaults to `http://127.0.0.1:8000`, matching the backend's local
development server; change it if the API runs elsewhere. `NEXT_PUBLIC_*`
variables are inlined into the browser bundle, so keep secrets out of them.

## Commands

```bash
npm run dev     # start the development server on http://localhost:3000
npm run build   # production build
npm run start   # serve the production build
npm run lint    # eslint
npm run test    # vitest
```

## Running the full stack

The frontend calls the FastAPI backend, which requires PostgreSQL and (for
generation) a running worker.

**With Docker Compose (simplest).** First create the repository root `.env`
(including the `POSTGRES_*` values) as described in the root README's
[Quick start](../README.md#quick-start-with-docker-compose). Then, from the
repository root, start the database, migrations, API, and worker, install the
frontend dependencies once, and run the frontend:

```bash
docker compose up --build -d
cd frontend && npm install && npm run dev
```

A brand-new Docker database has no vocabulary, so the Generate page shows no
vocabulary lists until you import them
(`docker compose run --rm api sync-skritter --all`).

**Without Docker.** From the repository root, in separate terminals:

```bash
# 1. API (after `alembic upgrade head`)
.venv/bin/python -m uvicorn main:app --reload

# 2. Worker — required for queued story generations to actually run
.venv/bin/python -m story_generator.cli.generation_worker

# 3. Frontend
cd frontend && npm run dev
```

See the repository root [README](../README.md) for backend setup, database
migrations, and provider configuration.

## Project structure

- `app/page.tsx` — home page: introduces the app and links to the generate
  and saved-stories pages.
- `app/generate/page.tsx` — picks a vocabulary list and HSK level, submits a
  story-generation request, then polls it to completion. Shows a safe error
  and a retry option if generation fails, and stops polling on a
  non-recoverable status error (e.g. an unknown request) or on unmount.
- `app/stories/page.tsx` — saved-stories list, linking to each story's
  reader page, with a delete action that asks for inline confirmation and
  shows an error if the deletion fails.
- `app/stories/[id]/page.tsx` — story reader: Chinese title and body with a
  vocabulary glossary (pinyin and English definition), including a
  not-found state for an unknown story ID.
- `app/components/` — shared UI, e.g. the top navigation.
- `lib/api.ts` — typed fetch helpers for every backend endpoint the frontend
  calls (vocabulary lists, story generations, saved stories including
  deletion), including pagination and error handling.

## Status

Milestone 4 is implemented: a learner can select a vocabulary list, submit a
story-generation request, watch it complete (or retry a failure), and read
the resulting story with its vocabulary glossary from the saved-stories
list, with visual polish (M4-6) applied across the app. Saved stories can
also be deleted from the list. Tickets are tracked
on the [GitHub Project board](https://github.com/users/jack93g/projects/1),
not in markdown.
