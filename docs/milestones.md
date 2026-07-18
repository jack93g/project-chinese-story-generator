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
- FastAPI exposes REST endpoints for vocabulary, vocabulary lists, stories, and sync status.
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

**Goal:** Generate and persist useful stories constrained by learner vocabulary.

### Definition of done

- A provider-neutral LLM interface has an OpenAI implementation.
- Story generation selects appropriate learner vocabulary.
- Generation records the inputs, model configuration, and metadata needed for debugging and reproducibility.
- Stories and their vocabulary relationships persist in PostgreSQL.
- Tests cover prompt construction, provider boundaries, persistence, and generation without requiring live model calls.

### Learning outcomes

- Abstraction boundaries.
- Prompt engineering.
- External service testing.
- AI reproducibility.
- Persisting generated content.

---

## 4. Reader enrichment

**Goal:** Prepare generated stories for an effective reading experience.

### Definition of done

- Stories are tokenised after generation.
- Vocabulary occurrences are matched against the learner's vocabulary.
- Unknown words are identified.
- Pinyin and English definitions are attached to each token.
- Reader metadata is persisted for efficient frontend rendering.

### Learning outcomes

- Text processing.
- Tokenisation.
- Data enrichment pipelines.
- Backend preparation for frontend performance.

---

## 5. Frontend

**Goal:** Provide a simple web interface for generating and reading stories.

### Definition of done

- A Next.js application displays vocabulary, sync status, story generation, and saved stories.
- The reader supports toggling pinyin and English translations.
- Known and unknown vocabulary are visually distinguishable.
- The interface handles loading, empty, and failure states accessibly.

### Learning outcomes

- React state management.
- Data fetching.
- Component design.
- Accessible UI development.
- Frontend-backend contracts.

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