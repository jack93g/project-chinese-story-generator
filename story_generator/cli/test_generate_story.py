"""
Manual sanity-check script: exercises the real database and the real
configured OpenAI-compatible provider (OpenAI or OpenRouter, per
.env) end-to-end, short of persisting the generated story itself
(Story persistence doesn't exist yet — that's M3-5).

What this actually does, all for real:
  1. Loads a real VocabularyList from the database (first one found,
     or pass --list-id to pick a specific one).
  2. Creates and persists a real StoryGenerationRequest via
     GenerationRequestService.create() — real vocabulary selection,
     real prompt_version, real row in story_generation_requests.
  3. Transitions it through the real lifecycle: start() -> generate()
     -> succeed()/fail(), persisting status/timestamps/usage for real.
  4. Prints the generated title/body to the terminal — NOT persisted
     anywhere, since Story storage is out of scope until M3-5.

Run directly:

    python scripts/test_generate_story.py
    python scripts/test_generate_story.py --list-id 4
"""

import argparse

from sqlalchemy import select

from story_generator.database.session import get_session_factory
from story_generator.generation.persistence.repository import (
    GenerationRequestRepository,
)
from story_generator.generation.persistence.service import GenerationRequestService
from story_generator.generation.providers.errors import ProviderError
from story_generator.generation.providers.openai import build_openai_provider
from story_generator.generation.providers.types import GenerationRequestInput
from story_generator.generation.schemas import CreateGenerationRequestSchema
from story_generator.vocabulary.persistence.models import VocabularyList


def _pick_vocabulary_list(db, list_id: int | None) -> VocabularyList:
    if list_id is not None:
        vocab_list = db.get(VocabularyList, list_id)
        if vocab_list is None:
            raise SystemExit(f"No VocabularyList with id={list_id}")
        return vocab_list

    vocab_list = db.execute(select(VocabularyList).limit(1)).scalar_one_or_none()
    if vocab_list is None:
        raise SystemExit(
            "No VocabularyList found in the database. Pass --list-id or seed one first."
        )
    return vocab_list


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-id",
        type=int,
        default=None,
        help="VocabularyList id to use (defaults to the first list found)",
    )
    parser.add_argument("--hsk-level", type=int, default=2)
    parser.add_argument("--word-count", type=int, default=150)
    parser.add_argument("--vocab-count", type=int, default=5)
    parser.add_argument("--topic", type=str, default=None)
    args = parser.parse_args()

    session_factory = get_session_factory()
    db = session_factory()

    try:
        vocab_list = _pick_vocabulary_list(db, args.list_id)
        print(f"Using vocabulary list: {vocab_list.name!r} (id={vocab_list.id})")

        repository = GenerationRequestRepository(db)
        service = GenerationRequestService(repository)

        payload = CreateGenerationRequestSchema(
            vocabulary_list_id=vocab_list.id,
            target_hsk_level=args.hsk_level,
            target_word_count=args.word_count,
            target_vocabulary_count=args.vocab_count,
            topic=args.topic,
        )

        request = service.create(db, payload)
        db.commit()
        print(
            f"Created StoryGenerationRequest id={request.id}, status={request.status}"
        )
        print(
            f"Selected vocabulary ({len(request.selected_vocabulary_snapshot)} items):"
        )
        for item in request.selected_vocabulary_snapshot:
            print(f"  - {item['writing']} ({item['reading']}): {item['definition_en']}")
        print()

        service.start(request.id)
        db.commit()
        print(f"Status -> {request.status}")
        print("-" * 60)
        print("Requesting story from provider...")
        print()

        provider = build_openai_provider()
        generation_request = GenerationRequestInput(
            target_hsk_level=request.target_hsk_level,
            target_word_count=request.target_word_count,
            target_vocabulary_count=request.target_vocabulary_count,
            vocabulary_snapshot=request.selected_vocabulary_snapshot,
            prompt_version=request.prompt_version,
            topic=request.topic,
        )

        try:
            result = provider.generate(generation_request)
        except ProviderError as exc:
            service.fail(
                request.id, error_code=type(exc).__name__, error_message=str(exc)
            )
            db.commit()
            print(f"FAILED: {type(exc).__name__}: {exc}")
            print(f"Status -> {request.status}")
            raise SystemExit(1) from exc

        service.succeed(
            request.id,
            usage={
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
                "latency_ms": result.usage.latency_ms,
            },
        )
        db.commit()

        print(f"Title: {result.title}")
        print()
        print(f"Body:\n{result.body}")
        print()
        print("-" * 60)
        print(f"Status -> {request.status}")
        print(
            f"Usage: {result.usage.prompt_tokens} prompt + "
            f"{result.usage.completion_tokens} completion = "
            f"{result.usage.total_tokens} total tokens"
        )
        print(f"Latency: {result.usage.latency_ms}ms")
        print()
        print(
            "NOTE: the story text above was NOT persisted — Story "
            "storage doesn't exist until M3-5. Only the "
            f"StoryGenerationRequest row (id={request.id}) was saved."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
