import pytest

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.persistence.repository import GenerationRequestRepository
from story_generator.vocabulary.persistence.models import VocabularyList


pytestmark = pytest.mark.db


def _make_request(db_session) -> StoryGenerationRequest:
    vocab_list = VocabularyList(skritter_list_id="list-1", name="Test list")
    db_session.add(vocab_list)
    db_session.flush()

    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[
            {"id": 1, "writing": "你好", "reading": "ni3 hao3", "definition_en": "hello"}
        ],
        prompt_version="story-v1",
        provider="anthropic",
        model="claude-sonnet-5",
    )
    db_session.add(request)
    db_session.flush()
    return request


def test_add_raw_payload_redacts_secrets_in_request_body(db_session):
    request = _make_request(db_session)
    repository = GenerationRequestRepository(db_session)

    raw = repository.add_raw_payload(
        generation_request_id=request.id,
        attempt_number=1,
        provider="anthropic",
        request_body={"api_key": "sk-live-secret", "model": "claude-sonnet-5"},
        response_status=200,
        payload={"content": "story text"},
    )

    db_session.expire(raw)  # force a re-read from the DB, not the Python cache
    persisted = repository.list_raw_payloads(request.id)[0]

    assert persisted.request_body == {
        "api_key": "[REDACTED]",
        "model": "claude-sonnet-5",
    }


def test_add_raw_payload_redacts_secrets_echoed_in_response_body(db_session):
    request = _make_request(db_session)
    repository = GenerationRequestRepository(db_session)

    repository.add_raw_payload(
        generation_request_id=request.id,
        attempt_number=1,
        provider="anthropic",
        request_body={"model": "claude-sonnet-5"},
        response_status=401,
        payload={"error": "unauthorized", "request": {"authorization": "Bearer xyz"}},
    )

    persisted = repository.list_raw_payloads(request.id)[0]

    assert persisted.payload["request"]["authorization"] == "[REDACTED]"
    assert persisted.payload["error"] == "unauthorized"


def test_add_raw_payload_preserves_non_secret_fields(db_session):
    request = _make_request(db_session)
    repository = GenerationRequestRepository(db_session)

    repository.add_raw_payload(
        generation_request_id=request.id,
        attempt_number=1,
        provider="anthropic",
        request_body=None,
        response_status=200,
        payload={"writing": "你好", "count": 5},
    )

    persisted = repository.list_raw_payloads(request.id)[0]

    assert persisted.request_body is None
    assert persisted.payload == {"writing": "你好", "count": 5}