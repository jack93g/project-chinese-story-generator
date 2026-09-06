# Milestone 4 — Lean frontend MVP backlog

## Outcome

A learner can select an imported vocabulary list, choose a target HSK level, request a story, wait for the result, and read the saved Chinese story with its selected-vocabulary glossary.

This milestone is intentionally a thin vertical slice. It proves that the current backend story-generation workflow is usable before investing in interactive reading aids.

## Assumptions

- The existing FastAPI endpoints are the only frontend data source; the frontend never accesses PostgreSQL directly.
- There is one local learner for this MVP. Authentication, accounts, and per-user data isolation are out of scope.
- Generation is asynchronous. The UI creates a request with `POST /story-generations` and polls `GET /story-generations/{id}` until it reaches `succeeded` or `failed`.
- `GET /stories/{id}` supplies the Chinese story and its selected vocabulary, including pinyin and English definitions.
- The initial provider and worker are already configured and running outside the frontend.

## Not in scope

- Inline pinyin or English translation in the story text.
- Highlighting word occurrences, unknown-word detection, tokenisation, or `GET /stories/{id}/reader`.
- User authentication, registration, settings, payments, or sharing.
- Vocabulary editing, syncing, or generation-provider selection from the UI.
- A component library, complex visual design system, mobile-native app, analytics, or production deployment.

These are candidates for later milestones only after the basic flow has been used and validated.

## Jira tickets

### M4-1 — Scaffold the Next.js frontend

**Type:** Story | **Estimate:** 3 | **Depends on:** M3 story-generation API being committed and runnable

Create a standalone Next.js application in `frontend/` within this repository. Add a clear local-development setup and configure the API base URL through an environment variable.

**Acceptance criteria**

- `frontend/` has its own package configuration, development command, production build command, and lint/test command.
- The frontend can call the locally running FastAPI API without hard-coding a deployment-specific URL.
- A minimal app shell has navigation to Generate and Saved stories.
- README documents how to start the API, worker, and frontend together.

### M4-2 — Display vocabulary lists and the story-generation form

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-1

Build the Generate page. Fetch vocabulary lists, let the learner choose one list and a target HSK level, and offer optional topic and target-length controls.

**Acceptance criteria**

- The page loads `GET /vocabulary-lists` and displays each list name and vocabulary-item count.
- A list and HSK level are required before Generate is enabled.
- Topic and target word count are optional and use sensible MVP defaults.
- Loading, empty-list, validation, and API-error states are clear and accessible.
- The submitted form payload matches `POST /story-generations` exactly; the client does not construct prompts or choose vocabulary items.

### M4-3 — Implement asynchronous generation status and retry

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-2

After submission, show generation state and poll the generation-status endpoint until completion or failure.

**Acceptance criteria**

- Submitting a valid form calls `POST /story-generations` once and transitions to a clear queued/running state.
- The UI polls `GET /story-generations/{id}` at a modest interval (for example, every 2–3 seconds) and stops polling when the request is terminal or the page is left.
- On `succeeded`, the learner is taken to the resulting story using `story_id`.
- On `failed`, the safe API error is shown and an eligible retry calls `POST /story-generations/{id}/retry`.
- The UI does not expose provider/model details or raw diagnostic payloads.

### M4-4 — Build the saved-story reader and glossary

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-1

Build a readable story-detail page using `GET /stories/{id}` and show the selected vocabulary as a glossary.

**Acceptance criteria**

- The page presents Chinese title and body with readable typography and preserves line breaks.
- The glossary shows each selected word with pinyin and English definition.
- Direct navigation to an unknown story has a useful not-found state.
- Loading and API-error states are handled accessibly.
- No tokenisation, inline annotations, or unknown-word claims are attempted.

### M4-5 — Add saved-story list and minimal end-to-end tests

**Type:** Story | **Estimate:** 3 | **Depends on:** M4-3, M4-4

Provide a route to previously generated stories and verify the main learner journey with automated tests.

**Acceptance criteria**

- Saved stories are loaded from `GET /stories` and link to their reader page.
- Empty and loading states are displayed.
- Tests cover: selecting a list and submitting a generation request; successful completion leading to a story; failed generation and retry; and reading a story/glossary.
- The frontend production build and tests run in CI or a documented local command.

## Suggested delivery order

```text
M4-1 → M4-2 → M4-3
     └→ M4-4 → M4-5
```

M4-4 can run alongside M4-2/M4-3 once the app shell exists. The milestone is complete when M4-5 is complete.

## Later improvements

Use the first MVP to decide which reader enhancements matter. Likely next candidates are inline vocabulary highlighting, click-to-reveal pinyin/definition, unknown-word identification, and reader preferences. Those belong to Milestone 5, not this MVP.
