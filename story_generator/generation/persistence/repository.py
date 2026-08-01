from sqlalchemy.orm import Session

from story_generator.generation.persistence.models import (
    RawGenerationPayload,
    StoryGenerationRequest,
)
from story_generator.generation.redaction import redact


class GenerationRequestRepository:
    """Persistence operations for generation requests and their raw payloads.

    Transaction boundaries are controlled by the calling service.
    """

    def __init__(self, session: Session):
        self.session = session

    def create(self, request: StoryGenerationRequest) -> StoryGenerationRequest:
        self.session.add(request)
        self.session.flush()
        return request

    def get_by_id(self, request_id: int) -> StoryGenerationRequest | None:
        return self.session.get(StoryGenerationRequest, request_id)

    def add_raw_payload(
        self,
        generation_request_id: int,
        attempt_number: int,
        provider: str,
        request_body: dict | None,
        response_status: int | None,
        payload: dict | None,
    ) -> RawGenerationPayload:
        """
        Persist a raw provider request/response for one generation attempt.

        Only accepts parsed body dicts, never headers or a raw HTTP
        response object — that's enforced by this signature, not just
        convention. Both bodies are additionally passed through
        redact() before the row is constructed, so a secret echoed
        inside a body (not just headers) is still caught.
        """
        raw_payload = RawGenerationPayload(
            generation_request_id=generation_request_id,
            attempt_number=attempt_number,
            provider=provider,
            request_body=redact(request_body) if request_body is not None else None,
            response_status=response_status,
            payload=redact(payload) if payload is not None else None,
        )
        self.session.add(raw_payload)
        self.session.flush()
        return raw_payload

    def list_raw_payloads(self, generation_request_id: int) -> list[RawGenerationPayload]:
        return (
            self.session.query(RawGenerationPayload)
            .filter_by(generation_request_id=generation_request_id)
            .order_by(RawGenerationPayload.attempt_number.asc())
            .all()
        )