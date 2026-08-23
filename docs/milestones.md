# Milestones

## 0. Foundation

**Goal:** Establish shared project direction before application code exists.

### Definition of done

- Repository includes an appropriate `.gitignore`.
- Architecture documents the MVP purpose, boundaries, components, and data flow.
- Milestones describe the intended delivery sequence and learning goals.
- Documentation is reviewed and committed.

### Learning outcomes

- Translate product goals into clear technical boundaries.
- Make explicit architecture decisions before writing code.
- Use Git commits to capture meaningful project progress.

---

## 1. Vocabulary ingestion

**Goal:** Reliably synchronise Skritter vocabulary into PostgreSQL.

### Definition of done

- A Skritter client fetches vocabulary using a manually invoked sync function.
- Every sync reports useful progress and status information.
- Vocabulary and vocabulary lists are normalised into PostgreSQL using a many-to-many relationship without duplicating shared vocabulary items.
- Database constraints enforce referential integrity and idempotent imports.
- Automated tests cover parsing, transformation, persistence, and expected failure scenarios.

### Learning outcomes

- API client design.
- Service and repository boundaries.
- Relational data modelling and normalisation.
- Transactions and idempotent imports.
- Logging and progress reporting.
- Test-driven development and boundary testing.

---

## 2. Backend API

**Goal:** Expose application data through a maintainable FastAPI application.

### Definition of done

- SQLAlchemy models and Alembic migrations represent the operational schema.
- FastAPI exposes REST endpoints for vocabulary, vocabulary lists, saved stories, and sync status. Story creation is owned by Milestone 3.
- Route handlers remain thin; business logic stays within service and domain modules.
- API and database behaviour are covered by automated tests.

### Learning outcomes

- REST API design.
- Dependency injection.
- ORM design and trade-offs.
- Database migrations.
- Integration testing.

---

## 3. Story generation

**Goal:** Generate and persist useful stories through a durable, backend-owned asynchronous workflow.

### Product and technical decisions

- A generation is requested with a vocabulary-list ID, target HSK level, and optional controls such as topic and target length. The server selects a bounded set of vocabulary from that list; the client never supplies the prompt or arbitrary vocabulary IDs.
- `POST /story-generations` creates a durable request and returns `202 Accepted` with its ID and `queued` status. A backend worker processes queued requests. `GET /story-generations/{id}` exposes lifecycle state; `GET /stories/{id}` returns a completed story. This is also the frontend contract for Milestone 4.
- A story has a stable, provider-independent shape: Chinese title and body, requested/used target vocabulary, validation results, and generation provenance. The complete provider response is retained separately for debugging; it is not the public API contract.
- Start with OpenAI behind a provider-neutral interface. Add Ollama-compatible Chinese-model providers only after the evaluation harness is in place, so models are compared against the same prompts and checks rather than selected by anecdote.
- Generation is accepted when every selected target word is present and the generated text passes structural checks. HSK level is a target, not a guarantee: automated checks should flag unsupported vocabulary for review rather than claim formal HSK certification.

### Definition of done

- A provider-neutral LLM interface has an OpenAI implementation and a documented provider test double.
- A durable generation request lifecycle (`queued`, `running`, `succeeded`, `failed`) is persisted and exposed through the API.
- A worker selects a bounded, deterministic vocabulary sample from the requested list, builds a versioned prompt, invokes the configured provider, validates the structured result, and persists a completed story.
- Generation records request inputs, selected vocabulary, prompt version, provider/model settings, token/latency metadata, validation outcome, and a redacted/raw provider response retention policy needed for debugging and reproducibility.
- Stories persist their requested and actually used vocabulary relationships. Failed requests retain a safe diagnostic message and remain retryable.
- Tests cover request validation, vocabulary selection, prompt construction, provider boundaries, lifecycle transitions, persistence, and generation without live model calls.

### Learning outcomes

- Abstraction boundaries.
- Prompt engineering.
- External service testing.
- AI reproducibility.
- Persisting generated content.

---

## 4. Frontend

**Goal:** Provide a simple end-to-end interface for selecting vocabulary, generating a story, and reading it.

### Definition of done

- A Next.js application displays vocabulary lists, sync status, saved stories, and story-generation controls.
- A learner can choose a vocabulary list, target HSK level, and optional topic/length, then start a story-generation request.
- The interface observes queued, running, succeeded, and failed generation states, including retry where eligible.
- A completed story is readable in Chinese and shows its selected-vocabulary glossary using the existing pinyin and English definitions.
- The interface handles loading, empty, and failure states accessibly.
- Frontend tests cover the generation flow and story reading against the published API contract.

### Learning outcomes

- React state management.
- Data fetching and asynchronous workflow UI.
- Component design.
- Accessible UI development.
- Frontend-backend contracts.

---

## 5. Interactive reader enrichment

**Goal:** Enrich completed stories for an interactive Chinese-learning reading experience, informed by the first frontend release.

### Definition of done

- A selected tokenizer segments story text into ordered tokens and punctuation, preserving character offsets and sentence boundaries.
- Vocabulary occurrences are matched deterministically against the story's selected vocabulary and known vocabulary; unmatched lexical tokens are marked as unknown candidates.
- Pinyin and English definitions are attached from the vocabulary database when available. Any fallback enrichment source and its provenance are persisted.
- A versioned reader-document payload is persisted and exposed at `GET /stories/{id}/reader` for efficient frontend rendering.
- The reader supports inline pinyin/English toggles and visually distinguishes known, selected, and unknown vocabulary.
- Tests cover segmentation edge cases, repeated and overlapping vocabulary, Unicode offsets, matching, API serialization, and safe reprocessing.

### Learning outcomes

- Text processing.
- Chinese tokenisation and vocabulary matching.
- Data enrichment pipelines.
- Evidence-based backend optimisation for frontend performance.

---

## 6. Orchestration and delivery

**Goal:** Make the MVP repeatable to run, test, and schedule.

### Definition of done

- Docker Compose provisions local development services.
- GitHub Actions runs automated tests and quality checks.
- Airflow schedules and monitors the existing vocabulary sync.
- Structured logging and operational documentation support debugging and maintenance.

### Learning outcomes

- Containerised development.
- Continuous integration.
- Workflow orchestration.
- Observability.
- Operating production-style services.

---

## 7. Analytics and infrastructure

**Goal:** Extend the stable product with analytics and deployable infrastructure.

### Definition of done

- Operational data is exported to BigQuery for analytics while PostgreSQL remains the operational system of record.
- Terraform defines deployment infrastructure.
- Dashboards answer agreed learner and product questions.
- Infrastructure changes are reproducible and version controlled.

### Learning outcomes

- Analytical modelling.
- Infrastructure as code.
- Deployment trade-offs.
- Metrics-driven product development.
