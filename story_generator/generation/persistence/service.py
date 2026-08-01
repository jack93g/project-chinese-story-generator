from datetime import datetime, timezone

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.persistence.repository import GenerationRequestRepository


VALID_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running"},
    "running": {"succeeded", "failed"},
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


class GenerationRequestService:
    def __init__(self, repository: GenerationRequestRepository):
        self.repository = repository

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