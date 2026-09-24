"""
run_forever() tests: periodic stale reclaim and graceful stop.

These need committed data visible to the worker's own sessions (it opens
them from a session factory), so they use `two_sessions` rather than the
rolled-back `db_session`; that fixture truncates the tables afterwards.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.providers.fake import FakeStoryGenerationProvider
from story_generator.generation.worker import GenerationWorker
from tests.generation.test_worker import _make_queued_request

pytestmark = pytest.mark.db

# Upper bound on any run_forever() call here; the loops below should finish
# in well under a second.
JOIN_TIMEOUT_SECONDS = 10


class _StopOnGenerateProvider:
    """Asks the worker to stop as soon as it starts generating, so the test
    also proves the request in flight still completes after a stop."""

    def __init__(self):
        self._inner = FakeStoryGenerationProvider(
            scenario="success",
            raw_response='{"title": "问候", "body": "小明说你好。"}',
        )
        self.worker: GenerationWorker | None = None
        self.calls = 0

    def generate(self, request, on_raw_exchange=None):
        self.calls += 1
        self.worker.request_stop()
        return self._inner.generate(request, on_raw_exchange=on_raw_exchange)


def _run_in_thread(worker, engine, **kwargs) -> threading.Thread:
    thread = threading.Thread(
        target=worker.run_forever,
        args=(sessionmaker(bind=engine),),
        kwargs=kwargs,
        daemon=True,
    )
    thread.start()
    return thread


def _mark_running(session, request, *, started_at, attempt_count=1):
    """Leave a request as a killed worker would: claimed, never finished."""
    request.status = "running"
    request.started_at = started_at
    request.attempt_count = attempt_count
    session.commit()


def test_run_forever_reclaims_a_request_orphaned_after_startup(engine, two_sessions):
    """The deploy case: the request was orphaned moments before this worker
    started, so the startup sweep sees it as recent. Only a later, periodic
    sweep can requeue it."""
    setup, check = two_sessions
    request = _make_queued_request(setup, skritter_list_id="loop-orphan")
    _mark_running(setup, request, started_at=datetime.now(UTC))

    provider = _StopOnGenerateProvider()
    worker = GenerationWorker(provider=provider)
    provider.worker = worker

    thread = _run_in_thread(
        worker,
        engine,
        poll_interval=0.05,
        stale_after=timedelta(seconds=0.5),
        reclaim_interval=0.1,
    )
    thread.join(JOIN_TIMEOUT_SECONDS)
    if thread.is_alive():
        worker.request_stop()
        pytest.fail("orphaned request was never reclaimed and processed")

    reloaded = check.get(StoryGenerationRequest, request.id)
    assert provider.calls == 1
    assert reloaded.status == "succeeded"
    # One attempt by the "killed" worker, one after the reclaim.
    assert reloaded.attempt_count == 2


def test_run_forever_does_not_reclaim_when_stale_after_is_none(engine, two_sessions):
    setup, check = two_sessions
    request = _make_queued_request(setup, skritter_list_id="loop-no-reclaim")
    _mark_running(setup, request, started_at=datetime.now(UTC) - timedelta(hours=1))

    worker = GenerationWorker(provider=FakeStoryGenerationProvider())
    thread = _run_in_thread(worker, engine, poll_interval=0.05, stale_after=None)
    threading.Event().wait(0.3)
    worker.request_stop()
    thread.join(JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive()
    assert check.get(StoryGenerationRequest, request.id).status == "running"


def test_request_stop_interrupts_the_idle_poll_wait(engine, two_sessions):
    worker = GenerationWorker(provider=FakeStoryGenerationProvider())
    # A poll interval far longer than the join timeout: returning at all
    # proves the wait was cut short rather than slept out.
    thread = _run_in_thread(worker, engine, poll_interval=3600)
    threading.Event().wait(0.2)

    worker.request_stop()
    thread.join(JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive()


def test_reclaim_stale_commits_so_other_sessions_see_it(two_sessions):
    """With an empty queue nothing else commits, so an uncommitted sweep
    would be rolled back when the worker's session closes."""
    setup, check = two_sessions
    request = _make_queued_request(setup, skritter_list_id="loop-commit")
    _mark_running(setup, request, started_at=datetime.now(UTC) - timedelta(hours=1))

    request_id = request.id

    worker = GenerationWorker(provider=FakeStoryGenerationProvider())
    worker.reclaim_stale(setup, timedelta(minutes=15))
    setup.close()

    assert check.get(StoryGenerationRequest, request_id).status == "queued"
