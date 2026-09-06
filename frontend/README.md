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
generation) a running worker. From the repository root, in separate
terminals:

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

- `app/` — routes (App Router). `app/generate` and `app/stories` are
  placeholders pending later milestones.
- `app/components/` — shared UI, e.g. the top navigation.
- `lib/api.ts` — resolves `NEXT_PUBLIC_API_BASE_URL` for API calls.

## Status

This is the Milestone 4 scaffold (app shell, navigation, environment
config). Fetching vocabulary lists, submitting a generation request, polling
for status, and reading saved stories are implemented in later milestones —
see [docs/milestone-4-frontend-backlog.md](../docs/milestone-4-frontend-backlog.md).
