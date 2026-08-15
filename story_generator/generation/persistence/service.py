from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from story_generator.config import get_openai_model, get_openai_provider_label
from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.persistence.repository import GenerationRequestRepository
from story_generator.generation.prompts.builder import CURRENT_PROMPT_VERSION
from story_generator.generation.schemas import CreateGenerationRequestSchema
from story_generator.generation.vocabulary_selection import (
    EmptyVocabularyListError,  # noqa: F401  (re-exported for router)
    select_vocabulary,
)
from story_generator.vocabulary.persistence.models import VocabularyList

MAX_ATTEMPTS = 3

VALID_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running"},
    # "running" -> "queued" is the crash-recovery reclaim path (see
    # GenerationRequestService.reclaim_stale), not a normal retry.
    "running": {"succeeded", "failed", "queued"},
    "failed": {"queued"},
    "succeeded": set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, current_status: str, new_status: str):
        self.current_status = current_status
        self.new_status = new_status
        super().__init__(f"Cannot transition from '{current_status}' to '{new_status}'")


class GenerationRequestNotFoundError(Exception):
    def __init__(self, request_id: int):
        self.request_id = request_id
        super().__init__(f"Generation request {request_id} not found")


class VocabularyListNotFoundError(Exception):
    def __init__(self, vocabulary_list_id: int):
        self.vocabulary_list_id = vocabulary_list_id
        super().__init__(f"Vocabulary list {vocabulary_list_id} not found")


class RetryLimitExceededError(Exception):
    def __init__(self, request_id: int, attempt_count: int):
        self.request_id = request_id
        self.attempt_count = attempt_count
        super().__init__(
            f"Generation request {request_id} has exceeded the retry limit "
            f"({attempt_count} attempts, max {MAX_ATTEMPTS})"
        )


class GenerationRequestService:
    def __init__(self, repository: GenerationRequestRepository):
        self.repository = repository

    def create(self, db: Session, payload: CreateGenerationRequestSchema) -> StoryGenerationRequest:
        vocabulary_list = db.get(VocabularyList, payload.vocabulary_list_id)
        if vocabulary_list is None:
            raise VocabularyListNotFoundError(payload.vocabulary_list_id)

        snapshot = select_vocabulary(db, vocabulary_list, payload.target_vocabulary_count)

        request = StoryGenerationRequest(
            vocabulary_list_id=vocabulary_list.id,
            target_hsk_level=payload.target_hsk_level,
            topic=payload.topic,
            target_word_count=payload.target_word_count,
            target_vocabulary_count=payload.target_vocabulary_count,
            selected_vocabulary_snapshot=snapshot,
            prompt_version=CURRENT_PROMPT_VERSION,
            provider=get_openai_provider_label(),
            model=get_openai_model(),
        )
        return self.repository.create(request)

    def claim_next(self) -> StoryGenerationRequest | None:
        """Atomically claim the oldest queued request. See repository docstring."""
        return self.repository.claim_next_request()

    def reclaim_stale(self, stale_after: timedelta) -> dict[str, list[int]]:
        """Requeue 'running' requests stuck past the staleness threshold,
        or mark them failed if they've already exhausted MAX_ATTEMPTS."""
        return self.repository.reclaim_stale_running(stale_after, max_attempts=MAX_ATTEMPTS)

    def start(self, request_id: int) -> StoryGenerationRequest:
        request = self._get(request_id)
        self._transition(request, "running")
        request.started_at = datetime.now(timezone.utc)
        request.attempt_count += 1
        return request

    def succeed(self, request_id: int, usage: dict | None = None) -> StoryGenerationRequest:
        request = self._get(request_id)
        self._transition(request, "succeeded")
        request.completed_at = datetime.now(timezone.utc)
        if usage is not None:
            request.usage = usage
        return request

    def fail(self, request_id: int, error_code: str, error_message: str) -> StoryGenerationRequest:
        request = self._get(request_id)
        self._transition(request, "failed")
        request.completed_at = datetime.now(timezone.utc)
        request.error_code = error_code
        request.error_message = error_message
        return request

    def retry(self, request_id: int) -> StoryGenerationRequest:
        request = self._get(request_id)
        if request.attempt_count >= MAX_ATTEMPTS:
            raise RetryLimitExceededError(request_id, request.attempt_count)
        self._transition(request, "queued")
        request.started_at = None
        request.completed_at = None
        request.error_code = None
        request.error_message = None
        return request

    def _transition(self, request: StoryGenerationRequest, new_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(request.status, set())
        if new_status not in allowed:
            raise InvalidTransitionError(request.status, new_status)
        request.status = new_status

    def _get(self, request_id: int) -> StoryGenerationRequest:
        request = self.repository.get_by_id(request_id)
        if request is None:
            raise GenerationRequestNotFoundError(request_id)
        return request