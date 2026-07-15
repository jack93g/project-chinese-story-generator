# Milestones

## 0. Foundation

**Goal:** Establish shared project direction before application code exists.

**Definition of done:**

- Repository includes an appropriate `.gitignore`.
- Architecture documents the MVP purpose, boundaries, components, and data flow.
- Milestones describe the intended delivery sequence and learning goals.
- Documentation is reviewed and committed.

**Learning outcomes:** Translate product goals into boundaries, make explicit architecture decisions, and use Git commits to capture meaningful project progress.

## 1. Vocabulary ingestion

**Goal:** Reliably run a manual Skritter vocabulary sync into PostgreSQL.

**Definition of done:**

- A Skritter client fetches vocabulary using a manually invoked sync function.
- Every sync records status and useful logs; raw API payloads are retained.
- Vocabulary is normalised into PostgreSQL without duplicating shared vocabulary items.
- Automated tests cover parsing, transformation, persistence, and expected failures.

**Learning outcomes:** API-client design, data modelling, transactions, data normalisation, logging, and test-driven boundary handling.

## 2. Backend API

**Goal:** Expose vocabulary and sync state through a maintainable FastAPI application.

**Definition of done:**

- SQLAlchemy models and Alembic migrations represent the operational schema.
- FastAPI endpoints expose vocabulary and sync status with clear request/response models.
- Route handlers remain thin; application logic stays in domain modules.
- API and database behavior are covered by automated tests.

**Learning outcomes:** REST API design, dependency injection, ORM trade-offs, schema migrations, and integration testing.

## 3. Story generation

**Goal:** Generate and save useful stories constrained by learner vocabulary.

**Definition of done:**

- A provider-neutral LLM interface has an OpenAI implementation.
- Generation selects learner vocabulary and records the inputs and output metadata needed for debugging.
- Stories and their vocabulary relationships persist in PostgreSQL.
- Tests cover prompt construction, provider boundaries, and persistence without requiring live model calls.

**Learning outcomes:** abstraction boundaries, prompt design, external-service testing, and reproducibility of AI-assisted features.

## 4. Frontend

**Goal:** Give a learner a simple web experience for generating and reading stories.

**Definition of done:**

- Next.js interface shows vocabulary, sync state, story generation, and saved stories.
- Reader supports toggling pinyin and translations, and highlighting unknown words.
- The interface handles loading, empty, and failure states accessibly.

**Learning outcomes:** React state and data fetching, component design, accessible UI behavior, and frontend-backend contracts.

## 5. Orchestration and delivery

**Goal:** Make the proven MVP repeatable to run, test, and schedule.

**Definition of done:**

- Airflow schedules and monitors the existing sync function.
- Docker Compose supports local development services.
- GitHub Actions runs relevant checks on changes.
- Basic structured logging and operational documentation exist.

**Learning outcomes:** operationalising application code, containers, CI, scheduler boundaries, and observability basics.

## 6. Later: analytics and infrastructure

**Goal:** Extend the stable product with analytics and deployable infrastructure.

**Definition of done:**

- Operational data is exported to BigQuery for analytics without replacing PostgreSQL as the system of record.
- Terraform defines approved deployment infrastructure.
- Useful dashboards answer agreed learner and product questions.

**Learning outcomes:** analytical modelling, infrastructure as code, deployment trade-offs, and metrics-driven iteration.
