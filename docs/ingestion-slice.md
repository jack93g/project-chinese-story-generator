# Selected List Ingestion Slice

## Source
- List name: "Discussing social concepts, stereotypes etc"
- Skritter list ID: 5667140514938880
- API endpoints used: https://legacy.skritter.com/api/v0/vocablists/5667140514938880

## Inputs
- List payload
- Vocabulary payloads

## Database outputs
- sync run
- raw payload records
- vocabulary list
- vocabulary items
- list membership records

## Success criteria
- List and word count can be queried in PostgreSQL
- Re-running does not duplicate rows
- Raw payloads remain available for debugging

## Scope
- One manually selected Chinese list
- Read-only Skritter API requests
- No claim that list membership means the learner “knows” every word
- No incremental sync or scheduling yet


## Proposed normalised model

- `sync_runs`: one attempted import and its outcome
- `raw_skritter_payloads`: original JSON response, endpoint, status, and fetch time
- `vocabulary_lists`: one imported Skritter list
- `vocabulary_list_sections`: ordered sections within a list
- `vocabulary_list_rows`: ordered source rows, with simplified and traditional Skritter Vocab IDs
- `vocabulary_items`: normalized word details fetched from `/vocabs`