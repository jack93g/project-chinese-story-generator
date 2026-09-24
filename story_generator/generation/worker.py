"""
Durable worker for processing queued StoryGenerationRequests.

Claiming is atomic via SELECT ... FOR UPDATE SKIP LOCKED (see
GenerationRequestRepository.claim_next_request) — multiple worker
processes can poll the same table concurrently without ever
processing the same request twice.

Crash recovery: if a worker dies mid-processing, its claimed request
is left in "running" state — there is no in-process liveness
detection (no heartbeat). Instead, run_forever() calls
GenerationRequestService.reclaim_stale() at startup and then every
reclaim_interval seconds, requeueing any "running" request whose
started_at is older than the staleness threshold. Periodic, not just
at startup, because the worker that replaces a killed one usually
starts well inside the threshold (e.g. a deploy recreating the
container), so a startup-only sweep would never see the orphan.
Requests that are both stale AND have already exhausted MAX_ATTEMPTS
are marked failed directly instead of requeued, so a worker that
keeps crashing on the same request cannot loop it indefinitely.

Graceful stop: request_stop() (wired to SIGTERM by the CLI) makes
run_forever() exit after the request in flight, if any, finishes —
so an ordinary stop or deploy doesn't orphan a request at all, as
long as the container's stop grace period outlasts one provider call.

Success persistence is atomic: the Story row, its
StoryVocabularyItem associations, and the StoryGenerationRequest's
succeeded status/usage/validation_report are all written in a single
db.commit() in run_once() — either everything from a successful
generation is saved, or none of it is.

Vocabulary coverage is not required to be 100%: a story is only
rejected (marked failed, no Story row created) when validate_story()
reports coverage below VOCABULARY_COVERAGE_THRESHOLD. The raw
provider exchange is persisted on every outcome — provider error,
insufficient coverage, or success — so every failure mode is
diagnosable from raw_generation_payloads.
"""

import threading
import time
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from story_generator.generation.persistence.repository import (
    GenerationRequestRepository,
)
from story_generator.generation.persistence.service import GenerationRequestService
from story_generator.generation.providers.base import StoryGenerationProvider
from story_generator.generation.providers.errors import ProviderError
from story_generator.generation.providers.types import GenerationRequestInput
from story_generator.generation.validation import validate_story
from story_generator.stories.persistence.models import Story, StoryVocabularyItem
from story_generator.vocabulary.persistence.models import VocabularyItem


class GenerationWorker:
    def __init__(self, provider: StoryGenerationProvider):
        self._provider = provider
        self._stop = threading.Event()

    def request_stop(self) -> None:
        """Ask run_forever() to exit once the request in flight, if any, is
        done. Safe to call from a signal handler."""
        self._stop.set()

    def run_once(self, db: Session) -> bool:
        """
        Attempt to claim and process one queued request.

        Returns True if a request was claimed (regardless of whether
        generation succeeded or failed), False if the queue was empty.
        """
        repository = GenerationRequestRepository(db)
        service = GenerationRequestService(repository)

        request = service.claim_next()
        if request is None:
            return False

        generation_input = GenerationRequestInput(
            target_hsk_level=request.target_hsk_level,
            target_word_count=request.target_word_count,
            target_vocabulary_count=request.target_vocabulary_count,
            vocabulary_snapshot=request.selected_vocabulary_snapshot,
            prompt_version=request.prompt_version,
            topic=request.topic,
        )

        raw_exchange: dict = {
            "request_body": None,
            "response_status": None,
            "response_body": None,
        }

        def _record_raw_exchange(request_body, response_status, response_body):
            raw_exchange["request_body"] = request_body
            raw_exchange["response_status"] = response_status
            raw_exchange["response_body"] = response_body

        try:
            result = self._provider.generate(
                generation_input, on_raw_exchange=_record_raw_exchange
            )
        except ProviderError as exc:
            repository.add_raw_payload(
                generation_request_id=request.id,
                attempt_number=request.attempt_count,
                provider=request.provider,
                request_body=raw_exchange["request_body"],
                response_status=raw_exchange["response_status"],
                payload=raw_exchange["response_body"],
            )
            service.fail(
                request.id, error_code=type(exc).__name__, error_message=str(exc)
            )
            db.commit()
            return True

        validation_report, used_map = validate_story(request, result)

        repository.add_raw_payload(
            generation_request_id=request.id,
            attempt_number=request.attempt_count,
            provider=request.provider,
            request_body=raw_exchange["request_body"],
            response_status=raw_exchange["response_status"],
            payload=raw_exchange["response_body"],
        )

        if not validation_report["meets_coverage_threshold"]:
            request.validation_report = validation_report
            service.fail(
                request.id,
                error_code="InsufficientVocabularyCoverage",
                error_message=(
                    f"Generated story used {validation_report['used_vocabulary_count']}/"
                    f"{validation_report['requested_vocabulary_count']} requested vocabulary "
                    f"words (coverage {validation_report['coverage']:.0%}, "
                    f"required {validation_report['coverage_threshold']:.0%})"
                ),
            )
            db.commit()
            return True

        story = Story(
            generation_request_id=request.id,
            title=result.title,
            content=result.body,
            target_hsk=request.target_hsk_level,
        )
        for item in request.selected_vocabulary_snapshot:
            vocabulary_item = db.get(VocabularyItem, item["id"])
            story.vocabulary_associations.append(
                StoryVocabularyItem(
                    vocabulary_item=vocabulary_item,
                    requested=True,
                    used=used_map.get(item["id"], False),
                )
            )
        db.add(story)

        service.succeed(
            request.id,
            usage={
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
                "latency_ms": result.usage.latency_ms,
            },
        )
        request.validation_report = validation_report

        db.commit()
        return True

    def reclaim_stale(self, db: Session, stale_after: timedelta) -> None:
        repository = GenerationRequestRepository(db)
        service = GenerationRequestService(repository)
        result = service.reclaim_stale(stale_after)
        db.commit()
        if result["failed"]:
            print(
                f"Marked {len(result['failed'])} stale request(s) as failed "
                f"(exhausted retry limit): {result['failed']}"
            )
        if result["requeued"]:
            print(
                f"Requeued {len(result['requeued'])} stale request(s): {result['requeued']}"
            )

    def run_forever(
        self,
        session_factory: sessionmaker,
        poll_interval: float = 5.0,
        stale_after: timedelta | None = None,
        reclaim_interval: float = 300.0,
    ) -> None:
        db = session_factory()
        try:
            # Monotonic, so a wall-clock change can't stall or bunch sweeps.
            next_reclaim = time.monotonic()
            while not self._stop.is_set():
                if stale_after is not None and time.monotonic() >= next_reclaim:
                    self.reclaim_stale(db, stale_after)
                    next_reclaim = time.monotonic() + reclaim_interval

                processed = self.run_once(db)
                if not processed:
                    # Returns early if request_stop() is called meanwhile.
                    self._stop.wait(poll_interval)
        finally:
            db.close()
