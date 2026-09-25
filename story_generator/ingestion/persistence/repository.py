from typing import Any

from sqlalchemy import delete, func, select, update
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

    def fail_interrupted_runs(self, error_message: str) -> int:
        """Mark every run still in "running" as failed; returns how many.

        Only call this while holding the sync lock, when no run can
        legitimately be in progress.
        """
        result = self.session.execute(
            update(SyncRun)
            .where(SyncRun.status == "running")
            .values(
                status="failed",
                completed_at=func.now(),
                error_message=error_message,
            )
        )
        return result.rowcount

    def prune_raw_payloads(self, keep_runs: int) -> int:
        """Delete raw payloads of all but the newest `keep_runs` runs."""
        newest_runs = select(SyncRun.id).order_by(SyncRun.id.desc()).limit(keep_runs)
        result = self.session.execute(
            delete(RawSkritterPayload).where(
                RawSkritterPayload.sync_run_id.not_in(newest_runs)
            )
        )
        return result.rowcount

    def get_latest(self) -> SyncRun | None:
        return (
            self.session.query(SyncRun)
            .order_by(SyncRun.id.desc())
            .limit(1)
            .one_or_none()
        )


# Arbitrary, but fixed: every sync process must use the same key.
SYNC_LOCK_KEY = 7_302_418


class SyncLock:
    """A PostgreSQL advisory lock that lets only one sync run at a time.

    Give it a session of its own that nothing else uses. The lock is
    transaction-scoped and the session never commits, so it is released by
    `release()` (a rollback) or, if the process dies, when its connection
    closes. It can't leak into a pooled connection.

    The transaction sits idle for the whole sync (up to ~15 minutes with
    --refresh). If PostgreSQL's idle_in_transaction_session_timeout is ever
    set lower than that, the server ends it and drops the lock mid-sync.
    """

    def __init__(self, session: Session):
        self.session = session

    def try_acquire(self) -> bool:
        return self.session.execute(
            select(func.pg_try_advisory_xact_lock(SYNC_LOCK_KEY))
        ).scalar_one()

    def release(self) -> None:
        self.session.rollback()
