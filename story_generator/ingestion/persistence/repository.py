from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from story_generator.ingestion.persistence.models import RawSkritterPayload, SyncRun


class SyncRunRepository:
    """Persistence operations for ingestion run audit records."""

    def __init__(self, session: Session):
        self.session = session

    def create_sync_run(self, source: str = "skritter") -> SyncRun:
        sync_run = SyncRun(source=source, status="running")
        self.session.add(sync_run)
        self.session.flush()
        return sync_run

    def add_raw_payload(
        self,
        sync_run_id: int,
        request_path: str,
        request_params: dict[str, Any],
        response_status: int,
        payload: Any,
    ) -> RawSkritterPayload:
        raw_payload = RawSkritterPayload(
            sync_run_id=sync_run_id,
            request_path=request_path,
            request_params=request_params or {},
            response_status=response_status,
            payload=payload,
        )
        self.session.add(raw_payload)
        return raw_payload

    def complete_sync_run(self, sync_run_id: int, summary: dict[str, Any]) -> None:
        sync_run = self.session.query(SyncRun).filter_by(id=sync_run_id).one()
        sync_run.status = "succeeded"
        sync_run.completed_at = func.now()
        sync_run.summary = summary

    def fail_sync_run(
        self,
        sync_run_id: int,
        error_message: str,
        summary: dict[str, Any] | None = None,
    ) -> None:
        sync_run = self.session.query(SyncRun).filter_by(id=sync_run_id).one()
        sync_run.status = "failed"
        sync_run.completed_at = func.now()
        sync_run.error_message = error_message
        if summary is not None:
            sync_run.summary = summary
