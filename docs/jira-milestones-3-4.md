# Jira backlog — Milestones 3 and 4

Create these under an epic for each milestone. Estimates are relative implementation effort, not calendar commitments.

## Milestone 3 — Story generation

### M2-4 — Finalise saved-story read API and contract (Milestone 3 prerequisite)

**Type:** Story | **Estimate:** 3 | **Depends on:** Milestone 2 vocabulary endpoints

Implement paginated `GET /stories` and `GET /stories/{id}`, including empty states, not-found behaviour, and public schemas that deliberately exclude raw provider payloads.

**Acceptance criteria**

- API documentation exposes both endpoints and response schemas.
- Summaries include ID, title, creation time, target HSK and status-safe metadata.
- Detail returns canonical Chinese content and selected vocabulary, and unknown IDs return `404`.
- Unit/API tests cover normal, empty, pagination, and not-found cases.

### M3-1 — Add generation request and story provenance schema

**Type:** Story | **Estimate:** 5 | **Depends on:** M2-4

Create the migration and ORM/repository models for generation lifecycle, immutable request snapshot, provider provenance, validation report, retry metadata, and extended story fields.

**Acceptance criteria**

- Migration upgrades and downgrades cleanly on the test database.
- Valid lifecycle transitions are enforced by service logic.
- Request vocabulary snapshots survive later vocabulary-list changes.
- Raw/provider diagnostic data has documented redaction and retention behaviour.

### M3-2 — Define provider-neutral generation interface and fake provider

**Type:** Story | **Estimate:** 3 | **Depends on:** M3-1

Define canonical provider input/output types, error taxonomy, structured-result parser, and deterministic fake provider.

**Acceptance criteria**

- No story service imports a provider SDK directly.
- Fake-provider tests cover success, malformed output, timeout, and provider error.
- Canonical result has Chinese title and body plus usage metadata.

### M3-3 — Implement versioned prompt builder and vocabulary selection

**Type:** Story | **Estimate:** 5 | **Depends on:** M3-2

Select a deterministic capped vocabulary subset and render a versioned structured-output prompt.

**Acceptance criteria**

- Request rejects missing list and invalid HSK/length/count controls.
- Selection is deterministic for a stored request and preserves required vocabulary definitions/readings.
- Prompt version and selected vocabulary are saved before provider execution.
- Tests cover empty/short/oversized lists and prompt constraints.

### M3-4 — Implement OpenAI provider adapter and configuration

**Type:** Story | **Estimate:** 3 | **Depends on:** M3-2, M3-3

Add OpenAI implementation, timeouts, structured output, error mapping, and secrets configuration.

**Acceptance criteria**

- Live credentials are read only from environment/configuration and never persisted or logged.
- Adapter maps provider response to canonical result and captures safe usage/latency metadata.
- Contract tests run without live calls; a separately marked smoke test is optional.

### M3-5 — Build durable worker and generation lifecycle service

**Type:** Story | **Estimate:** 8 | **Depends on:** M3-1 through M3-4

Build atomic request claiming, processing, validation, persistence, failure recording, and retry eligibility.

**Acceptance criteria**

- Two workers cannot process one request twice.
- Restarting a worker does not lose queued work; stale running work has a documented recovery path.
- Success persists story, requested/used vocabulary links, provenance, and validation report atomically.
- Failure is observable, safe to retry when appropriate, and covered by tests.

### M3-6 — Expose generation and retry endpoints

**Type:** Story | **Estimate:** 5 | **Depends on:** M3-5

Implement `POST /story-generations`, status lookup, and retry endpoint with `202` semantics.

**Acceptance criteria**

- POST returns a request ID and `queued` without waiting for an LLM.
- Status response reveals state, safe error, and resulting story ID once available.
- Retry only accepts eligible failed requests and returns `409` otherwise.
- End-to-end API tests use the fake provider/worker, never a live LLM.

### M3-7 — Create generation evaluation fixtures and provider comparison report

**Type:** Task | **Estimate:** 3 | **Depends on:** M3-2, M3-3

Create representative vocabulary fixtures and a repeatable report for OpenAI and candidate Ollama/Qwen models.

**Acceptance criteria**

- Fixtures cover HSK levels, ambiguous words, short lists, and mixed known vocabulary.
- Report records schema validity, target-word coverage, length, latency, and manual quality notes.
- No provider is made selectable without a recorded comparison.

## Milestone 4 — Reader enrichment

### M4-1 — Define reader-document schema and enrichment lifecycle

**Type:** Story | **Estimate:** 3 | **Depends on:** M3-1, M3-5

Design versioned persisted reader document and separate enrichment status.

**Acceptance criteria**

- Schema holds token IDs/order, offsets, sentence boundaries, vocabulary links, annotations, and version.
- Reprocessing is idempotent and preserves the generated source text.
- Migration and repository tests pass.

### M4-2 — Implement Chinese segmentation and sentence boundaries

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-1

Integrate a documented tokenizer and produce deterministic token/sentence data.

**Acceptance criteria**

- Punctuation, numbers, mixed Latin text, repeated terms, and Unicode offsets are tested.
- Token offsets map exactly back to the original stored story text.
- Tokenizer version/configuration is recorded.

### M4-3 — Match known vocabulary and identify unknown candidates

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-2

Use deterministic longest-match rules to annotate selected/list vocabulary and unknown lexical tokens.

**Acceptance criteria**

- Overlapping vocabulary and repeated occurrences resolve predictably.
- Matches include vocabulary IDs; unmatched lexical words have an explicit unknown-candidate state.
- Matching tests cover Chinese word-boundary edge cases.

### M4-4 — Attach pinyin and English definitions with provenance

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-3

Use existing vocabulary metadata first and add a controlled fallback source for missing fields.

**Acceptance criteria**

- Existing database definitions take precedence.
- Fallback annotations record source/version and do not overwrite source vocabulary silently.
- Missing data remains explicitly missing rather than fabricated.

### M4-5 — Build enrichment worker and reader endpoint

**Type:** Story | **Estimate:** 5 | **Depends on:** M4-1 through M4-4

Run enrichment after successful generation and expose `GET /stories/{id}/reader`.

**Acceptance criteria**

- Successful generation queues enrichment automatically.
- Endpoint returns persisted document only; pending/failed enrichment returns documented status.
- API and end-to-end tests demonstrate generation → enrichment → reader retrieval.

### M4-6 — Add enrichment observability and reprocessing controls

**Type:** Task | **Estimate:** 3 | **Depends on:** M4-5

Add structured logs/metrics, stale-job recovery, and an operator-safe reprocess command.

**Acceptance criteria**

- Operators can identify a story's enrichment version and failure reason.
- Reprocess does not duplicate token data and is auditable.
- Operational instructions are documented.
