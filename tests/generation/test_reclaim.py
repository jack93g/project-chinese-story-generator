from datetime import datetime, timedelta, timezone

import pytest

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.persistence.repository import GenerationRequestRepository
from story_generator.generation.persistence.service import MAX_ATTEMPTS, GenerationRequestService
from story_generator.vocabulary.persistence.models import VocabularyList

pytestmark = pytest.mark.db


def _make_running_request(session, *, skritter_list_id: str, started_at, attempt_count: int = 1):
    vocab_list = VocabularyList(skritter_list_id=skritter_list_id, name="Test list")
    session.add(vocab_list)
    session.flush()

    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=100,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[],
        prompt_version="story-v1",
        provider="openai",
        model="gpt-test",
        status="running",
        started_at=started_at,
        attempt_count=attempt_count,
    )
    session.add(request)
    session.flush()
    return request


def test_reclaim_stale_requeues_old_running_requests_under_attempt_limit(db_session):
    stale_started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    request = _make_running_request(
        db_session, skritter_list_id="reclaim-stale", started_at=stale_started_at, attempt_count=1
    )
    db_session.commit()

    service = GenerationRequestService(GenerationRequestRepository(db_session))
    result = service.reclaim_stale(timedelta(minutes=15))

    db_session.refresh(request)
    assert request.id in result["requeued"]
    assert request.id not in result["failed"]
    assert request.status == "queued"
    assert request.started_at is None


def test_reclaim_stale_does_not_touch_recent_running_requests(db_session):
    recent_started_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    request = _make_running_request(
        db_session, skritter_list_id="reclaim-recent", started_at=recent_started_at, attempt_count=1
    )
    db_session.commit()

    service = GenerationRequestService(GenerationRequestRepository(db_session))
    result = service.reclaim_stale(timedelta(minutes=15))

    db_session.refresh(request)
    assert request.id not in result["requeued"]
    assert request.id not in result["failed"]
    assert request.status == "running"


def test_reclaim_stale_fails_requests_that_have_exhausted_max_attempts(db_session):
    stale_started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    request = _make_running_request(
        db_session,
        skritter_list_id="reclaim-exhausted",
        started_at=stale_started_at,
        attempt_count=MAX_ATTEMPTS,
    )
    db_session.commit()

    service = GenerationRequestService(GenerationRequestRepository(db_session))
    result = service.reclaim_stale(timedelta(minutes=15))

    db_session.refresh(request)
    assert request.id in result["failed"]
    assert request.id not in result["requeued"]
    assert request.status == "failed"
    assert request.error_code == "StaleWorkerRetryLimitExceeded"
    assert request.completed_at is not None


def test_repeated_reclaim_cycles_eventually_exhaust_and_stop_reclaiming(db_session):
    """
    Simulates a worker that keeps crashing on the same request: each
    cycle, the request is claimed (attempt_count += 1 happens at
    claim time, not modeled directly here — we drive attempt_count up
    manually to represent MAX_ATTEMPTS worth of crash cycles), goes
    stale, and gets reclaimed — until the attempt cap is hit, at which
    point reclaim must stop requeuing it and fail it instead.
    """
    stale_started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    request = _make_running_request(
        db_session,
        skritter_list_id="reclaim-repeated",
        started_at=stale_started_at,
        attempt_count=MAX_ATTEMPTS - 1,
    )
    db_session.commit()

    service = GenerationRequestService(GenerationRequestRepository(db_session))

    # One attempt still remaining: reclaim requeues it.
    result = service.reclaim_stale(timedelta(minutes=15))
    db_session.refresh(request)
    assert request.status == "queued"
    assert request.id in result["requeued"]

    # Simulate the worker claiming it again (attempt_count -> MAX_ATTEMPTS),
    # crashing again, and going stale again.
    request.status = "running"
    request.started_at = stale_started_at
    request.attempt_count = MAX_ATTEMPTS
    db_session.commit()

    # Now at the cap: reclaim must fail it, not requeue it again.
    result = service.reclaim_stale(timedelta(minutes=15))
    db_session.refresh(request)
    assert request.status == "failed"
    assert request.id in result["failed"]
    assert request.id not in result["requeued"]