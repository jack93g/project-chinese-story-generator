from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.persistence.repository import (
    GenerationRequestRepository,
)
from story_generator.generation.persistence.service import (
    GenerationRequestNotFoundError,
    GenerationRequestService,
    InvalidTransitionError,
)
from story_generator.vocabulary.persistence.models import VocabularyList

pytestmark = pytest.mark.db


def _make_request(db_session, **overrides):
    vocab_list = VocabularyList(skritter_list_id="list-1", name="Test list")
    db_session.add(vocab_list)
    db_session.flush()

    status = overrides.get("status", "queued")
    now = datetime.now(UTC)

    timestamp_defaults: dict = {}
    if status == "running":
        timestamp_defaults = {"started_at": now}
    elif status in ("succeeded", "failed"):
        timestamp_defaults = {"started_at": now, "completed_at": now}

    defaults = dict(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=5,
        selected_vocabulary_snapshot=[
            {
                "id": 1,
                "writing": "你好",
                "reading": "ni3 hao3",
                "definition_en": "hello",
            }
        ],
        prompt_version="story-v1",
        provider="anthropic",
        model="claude-sonnet-5",
    )
    defaults.update(timestamp_defaults)
    defaults.update(overrides)

    request = StoryGenerationRequest(**defaults)
    db_session.add(request)
    db_session.flush()
    return request


def test_start_transitions_queued_to_running(db_session):
    request = _make_request(db_session)
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    updated = service.start(request.id)

    assert updated.status == "running"
    assert updated.started_at is not None
    assert updated.attempt_count == 1


def test_succeed_transitions_running_to_succeeded(db_session):
    request = _make_request(db_session, status="running")
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    updated = service.succeed(
        request.id, usage={"prompt_tokens": 100, "completion_tokens": 50}
    )

    assert updated.status == "succeeded"
    assert updated.completed_at is not None
    assert updated.usage == {"prompt_tokens": 100, "completion_tokens": 50}


def test_fail_transitions_running_to_failed(db_session):
    request = _make_request(db_session, status="running")
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    updated = service.fail(
        request.id, error_code="provider_timeout", error_message="Request timed out"
    )

    assert updated.status == "failed"
    assert updated.completed_at is not None
    assert updated.error_code == "provider_timeout"
    assert updated.error_message == "Request timed out"


def test_retry_transitions_failed_to_queued_and_clears_error_fields(db_session):
    request = _make_request(
        db_session,
        status="failed",
        error_code="provider_timeout",
        error_message="Request timed out",
    )
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    updated = service.retry(request.id)

    assert updated.status == "queued"
    assert updated.started_at is None
    assert updated.completed_at is None
    assert updated.error_code is None
    assert updated.error_message is None


def test_cannot_start_a_request_that_is_already_running(db_session):
    request = _make_request(db_session, status="running")
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    with pytest.raises(InvalidTransitionError):
        service.start(request.id)


def test_cannot_transition_out_of_succeeded(db_session):
    request = _make_request(db_session, status="succeeded")
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    with pytest.raises(InvalidTransitionError):
        service.retry(request.id)


def test_cannot_succeed_a_queued_request_directly(db_session):
    request = _make_request(db_session, status="queued")
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    with pytest.raises(InvalidTransitionError):
        service.succeed(request.id)


def test_operating_on_unknown_request_raises_not_found(db_session):
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    with pytest.raises(GenerationRequestNotFoundError):
        service.start(999999)


def test_database_rejects_succeeded_request_without_started_at(db_session):
    vocab_list = VocabularyList(skritter_list_id="list-3", name="Yet another list")
    db_session.add(vocab_list)
    db_session.flush()

    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[{"id": 1, "writing": "你好"}],
        prompt_version="story-v1",
        provider="anthropic",
        model="claude-sonnet-5",
        status="succeeded",
        started_at=None,
        completed_at=datetime.now(UTC),
    )
    db_session.add(request)

    with pytest.raises(IntegrityError, match="lifecycle_timestamps_check"):
        db_session.flush()

    db_session.rollback()


def test_database_accepts_thirty_vocabulary_words(db_session):
    request = _make_request(db_session, target_vocabulary_count=30)

    assert request.id is not None


def test_database_rejects_more_than_thirty_vocabulary_words(db_session):
    with pytest.raises(IntegrityError, match="vocabulary_count_check"):
        _make_request(db_session, target_vocabulary_count=31)

    db_session.rollback()
