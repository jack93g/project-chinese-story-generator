# Architecture

## Purpose

AI Chinese Story Generator helps a learner practise Chinese through short, personalised stories built around vocabulary they already know. The application imports a learner's vocabulary from Skritter, stores it reliably, and uses that vocabulary to generate and present reading material.

## Users

- **Chinese learner:** connects Skritter, reviews synced vocabulary, generates stories, and reads saved stories with optional learning aids.
- **Project maintainer:** operates the application, investigates sync failures, and improves generation quality using stored metadata and raw source data.

## System boundaries

The MVP is a modular monolith: one backend codebase and deployable application with clear internal modules. It owns operational application data in PostgreSQL.

External systems are kept at explicit boundaries:

- **Skritter API** is the source for a learner's vocabulary.
- **OpenAI** is the initial story-generation provider. A provider interface will allow other implementations, such as Ollama, later.
- **PostgreSQL** is the system of record for users, connections, sync history, vocabulary, and stories.

Airflow, Docker Compose, GitHub Actions, BigQuery, Terraform, and deployment infrastructure are deliberately outside Milestone 0. Airflow will later schedule proven application sync code; it will not own ingestion business logic. BigQuery is a later analytics destination, not an operational database.

## Components

The backend will remain one application while separating responsibilities into modules:

- **`ingestion`:** Skritter client, raw-payload capture, sync orchestration, and failure logging.
- **`vocabulary`:** validates and normalises source data, then maintains vocabulary and learner associations.
- **`stories`:** selects vocabulary, records generation requests/results, and retrieves saved stories.
- **`llm`:** provider-neutral generation interface and provider-specific implementations.
- **`api`:** thin FastAPI route handlers that validate requests and call application modules.

The web interface will be a separate Next.js application. It calls the backend API and renders stories with optional pinyin, translations, and unknown-word highlighting.

## Data flow

1. A learner connects their Skritter account.
2. The ingestion module requests vocabulary from the Skritter API and records a `sync_run`.
3. The unmodified response is stored as a `raw_skritter_payload` for investigation and reprocessing.
4. The vocabulary module normalises valid records into shared `vocabulary_items` and learner-specific `user_vocabulary` records.
5. A learner requests a story. The stories module chooses appropriate known vocabulary and asks the configured LLM provider to generate a story.
6. The application saves the story and its vocabulary relationships in `stories` and `story_vocabulary_items`.
7. The frontend fetches saved stories and vocabulary metadata, then lets the learner reveal or hide reading aids.

## Core data model

| Entity | Responsibility |
| --- | --- |
| `users` | Learner identity and application preferences. |
| `skritter_connections` | A user's Skritter connection and credential metadata. |
| `sync_runs` | Status, timing, and diagnostics for each vocabulary sync. |
| `raw_skritter_payloads` | Original Skritter responses retained for debugging and reprocessing. |
| `vocabulary_items` | Normalised vocabulary shared across users. |
| `user_vocabulary` | A learner's relationship to each vocabulary item and learning state. |
| `stories` | Generated story content, settings, and generation metadata. |
| `story_vocabulary_items` | Vocabulary selected for or found in each story. |
