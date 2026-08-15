from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
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

    def claim_next_request(self) -> StoryGenerationRequest | None:
        """
        Atomically claim the oldest queued request.

        SELECT ... FOR UPDATE SKIP LOCKED: this transaction's SELECT
        takes a row lock; any concurrent worker running the same
        SKIP LOCKED query simply skips this row and finds the next
        one, rather than blocking on it. Committing promptly (this
        method commits before returning) releases the lock quickly
        and makes the new "running" status visible to other workers
        — the row is intentionally NOT held locked for the duration
        of the (potentially slow) provider call that follows.
        """
        stmt = (
            select(StoryGenerationRequest)
            .where(StoryGenerationRequest.status == "queued")
            .order_by(StoryGenerationRequest.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        request = self.session.execute(stmt).scalar_one_or_none()
        if request is None:
            return None

        request.status = "running"
        request.started_at = datetime.now(timezone.utc)
        request.attempt_count += 1
        self.session.commit()
        return request

    def reclaim_stale_running(self, stale_after: timedelta, max_attempts: int) -> dict[str, list[int]]:
        """
        Crash-recovery path: for every "running" request whose started_at
        predates the staleness threshold —
        - if attempt_count < max_attempts, requeue it (it gets another
            real attempt via the normal claim path);
        - otherwise, mark it failed directly with a diagnostic message,
            so a worker that keeps crashing on the same request cannot
            loop it through reclaim indefinitely, bypassing the same
            MAX_ATTEMPTS cap that governs manual retry().

        Two plain bulk UPDATEs (not routed through the ORM-instance state
        machine) since this is an administrative sweep over potentially
        many rows, not a single-request transition.
        """
        threshold = datetime.now(timezone.utc) - stale_after

        requeue_stmt = (
            update(StoryGenerationRequest)
            .where(StoryGenerationRequest.status == "running")
            .where(StoryGenerationRequest.started_at < threshold)
            .where(StoryGenerationRequest.attempt_count < max_attempts)
            .values(status="queued", started_at=None)
            .returning(StoryGenerationRequest.id)
        )
        requeued_ids = [row[0] for row in self.session.execute(requeue_stmt)]

        now = datetime.now(timezone.utc)
        exhaust_stmt = (
            update(StoryGenerationRequest)
            .where(StoryGenerationRequest.status == "running")
            .where(StoryGenerationRequest.started_at < threshold)
            .where(StoryGenerationRequest.attempt_count >= max_attempts)
            .values(
                status="failed",
                completed_at=now,
                error_code="StaleWorkerRetryLimitExceeded",
                error_message=(
                    f"Request remained 'running' past the staleness threshold "
                    f"({stale_after}) and had already reached {max_attempts} attempts; "
                    f"marked failed instead of reclaimed to avoid an indefinite crash loop."
                ),
            )
            .returning(StoryGenerationRequest.id)
        )
        failed_ids = [row[0] for row in self.session.execute(exhaust_stmt)]

        self.session.commit()
        return {"requeued": requeued_ids, "failed": failed_ids}

    def add_raw_payload(
        self,
        generation_request_id: int,
        attempt_number: int,
        provider: str,
        request_body: dict | None,
        response_status: int | None,
        payload: dict | None,
    ) -> RawGenerationPayload:
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