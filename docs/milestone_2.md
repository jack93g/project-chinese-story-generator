Current baseline:
Ingestion, parser, and raw SQL repository code exist.
No FastAPI, SQLAlchemy, or Alembic setup exists yet.
The checked-in SQL schema is effectively empty.
Tests currently cannot collect because the project isn’t installed/configured as an importable package.
Recommended implementation order:
Establish the backend foundation
Add project packaging/configuration so tests import story_generator reliably.
Add FastAPI, SQLAlchemy 2.x, Alembic, and a test database strategy.
Replace the import-on-load main.py script with an application factory, e.g. create_app().

Define the operational schema and migration baseline
Model the existing vocabulary tables and list membership in SQLAlchemy.
Add sync_runs and raw payload storage, since sync status is an API requirement.
Add a minimal stories model now (content, title, timestamps, metadata); defer LLM-generation-specific fields and story-vocabulary relationships to Milestone 3 unless needed for the read API.
Generate an initial Alembic migration and verify both upgrade and downgrade against an empty database.

Preserve ingestion behind service/repository boundaries
Refactor direct psycopg repository calls to use a SQLAlchemy session or unit-of-work boundary.
Keep parsing and Skritter access unchanged where possible.
Make sync runs record started/completed/failed state, counts, errors, and timestamps.
Ensure the sync operation is callable by a service, not triggered when the app imports.

Add thin REST routes
GET /vocabulary — paginated vocabulary, optional list filter/search.
GET /vocabulary/{id} — one vocabulary item.
GET /vocabulary-lists and GET /vocabulary-lists/{id} — lists and their entries.
GET /stories, GET /stories/{id} — saved stories; initially empty is valid.
GET /sync-status — latest run plus recent sync history.
Optionally POST /sync only if manually triggering an import is intended to be part of this milestone; otherwise keep sync as a CLI/service operation.

Add API contracts and dependency injection
Use Pydantic response models so database entities never leak directly from routes.
Add dependencies for session lifecycle and services.
Centralize 404 handling, pagination validation, and database error translation.

Build the test suite around behaviour
Unit tests for services and mappings.
Integration tests that apply Alembic migrations to a disposable PostgreSQL database.
FastAPI tests covering successful, empty, invalid, and not-found responses.
Regression tests for idempotent ingestion and sync failure status recording.

Suggested first delivery slice: “read-only vocabulary API.” It gives a complete vertical path—migration → ORM → service → route → integration test—while keeping stories and sync triggering small until their domain behavior is defined.