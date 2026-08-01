# Story generation design

## Decision

Story generation is a durable, asynchronous backend workflow. The frontend (introduced in Milestone 5) only starts a request and observes its status; it never calls an LLM directly or constructs prompts.

This is preferred to a synchronous endpoint because LLM calls are slow and fallible. It also gives every request an audit record, enables retries, and works unchanged when a real queue is introduced later.

## End-to-end flow

1. The client fetches `GET /vocabulary-lists` and selects one list, HSK level, plus optional topic and length.
2. `POST /story-generations` validates the list and settings, creates a `queued` generation request, and returns `202 Accepted`.
3. A backend worker claims one request, sets it to `running`, and snapshots a deterministic bounded selection of the list's vocabulary.
4. The worker renders a versioned prompt and sends it to the configured LLM provider. The provider must return a structured story object.
5. The worker validates the result, persists the story, its vocabulary relationships, provider metadata, and validation report, then marks the request `succeeded`. Provider/parsing/validation failure marks it `failed` with a safe error and allows retry.
6. A successful story is enriched in Milestone 4 into a persisted reader document. The frontend reads `GET /stories/{id}` and then `GET /stories/{id}/reader`.

## Public API contract

| Endpoint | Purpose | Initial response |
| --- | --- | --- |
| `GET /stories` | Paginated saved-story summaries | `200` |
| `GET /stories/{story_id}` | Completed story and provenance safe for users | `200` / `404` |
| `POST /story-generations` | Queue a story generation | `202` |
| `GET /story-generations/{request_id}` | Observe generation state and resulting story ID | `200` / `404` |
| `POST /story-generations/{request_id}/retry` | Retry an eligible failed request | `202` / `409` |
| `GET /stories/{story_id}/reader` | Persisted enriched reader document (Milestone 4) | `200` / `409` / `404` |

`POST /story-generations` body:

```json
{
  "vocabulary_list_id": 42,
  "target_hsk_level": 4,
  "topic": "ordering food with friends",
  "target_word_count": 250,
  "target_vocabulary_count": 12
}
```

The service caps `target_vocabulary_count` (initially 8–15) and target length. A snapshot of the selected vocabulary is part of the request, so a later Skritter sync cannot change reproducibility.

## Persistence boundary

Keep the existing `stories` table as the public content record, but migrate it before generation work. Add a `story_generation_requests` table for status, immutable inputs, vocabulary snapshot, prompt template/version, provider/model/parameters, timing/token usage, error, retry information, and a private provider-result field with a retention policy. Extend `stories` with generation request reference, target HSK level, validation report, and reader-enrichment status/version. Extend the story-vocabulary association with a role (`requested`, `used`, `unknown`) and occurrence information belongs in Milestone 4 reader tables/payload, not this join table.

Do not make the provider's JSON response the story API. Parse it into a small canonical object: `title_zh`, `body_zh`, and optional author-facing notes. Store the original result only for diagnosis, with secrets redacted.

## Prompting and quality

Prompts should request JSON matching a schema, Chinese-only title/body, selected required words, target HSK, word-count range, and a short natural story. Prompt templates are versioned in source control and their version is saved with each request.

Validation has two layers:

- Hard failures: schema invalid, empty story, missing required target vocabulary, unsafe/provider error.
- Quality signals: character/word length, target-vocabulary coverage, duplicates, and vocabulary outside the target level/list. These are stored as metadata and may initially warn rather than reject.

HSK should be framed in the UI as “aimed at HSK 4.” A complete HSK vocabulary reference dataset is required before scoring an absolute difficulty claim.

## Provider strategy

Define one `StoryGenerationProvider` interface accepting a canonical generation request and returning the canonical structured result plus usage metadata. Implement OpenAI first for the reliability baseline. Add an Ollama-compatible adapter next if local experimentation is desired; it can target Chinese models such as Qwen, but a model only becomes selectable after it passes the same fixture-based evaluation set. Provider selection is server configuration, not a client request, for the initial release.

The first worker may be a separately run database-polling process. It must claim rows atomically and be safe to restart. This avoids coupling an HTTP process to long work; a dedicated queue can replace the polling mechanism later without changing the public API or request lifecycle.
