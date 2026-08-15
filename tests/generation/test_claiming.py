import pytest

from story_generator.generation.persistence.repository import GenerationRequestRepository
from story_generator.generation.persistence.service import GenerationRequestService
from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList

pytestmark = pytest.mark.db


def _make_queued_request(session, *, skritter_list_id: str):
    vocab_list = VocabularyList(skritter_list_id=skritter_list_id, name="Test list")
    session.add(vocab_list)
    session.flush()

    item = VocabularyItem(
        skritter_vocab_id=f"{skritter_list_id}-item-1",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )
    session.add(item)
    session.flush()
    vocab_list.items.append(item)
    session.flush()

    from story_generator.generation.persistence.models import StoryGenerationRequest

    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=100,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[
            {"id": item.id, "writing": "你好", "reading": "ni3 hao3", "definition_en": "hello"}
        ],
        prompt_version="story-v1",
        provider="openai",
        model="gpt-test",
    )
    session.add(request)
    session.commit()
    return request


def test_claim_next_transitions_to_running_and_increments_attempt_count(db_session):
    request = _make_queued_request(db_session, skritter_list_id="claim-1")
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    claimed = service.claim_next()

    assert claimed.id == request.id
    assert claimed.status == "running"
    assert claimed.started_at is not None
    assert claimed.attempt_count == 1


def test_claim_next_returns_none_when_queue_is_empty(db_session):
    service = GenerationRequestService(GenerationRequestRepository(db_session))

    assert service.claim_next() is None


def test_two_workers_cannot_claim_the_same_request(two_sessions):
    session_a, session_b = two_sessions
    request = _make_queued_request(session_a, skritter_list_id="claim-concurrent")

    service_a = GenerationRequestService(GenerationRequestRepository(session_a))
    service_b = GenerationRequestService(GenerationRequestRepository(session_b))

    claimed_by_a = service_a.claim_next()
    assert claimed_by_a is not None
    assert claimed_by_a.id == request.id
    assert claimed_by_a.status == "running"

    # session_a already committed inside claim_next(), so the row is
    # visible to session_b with status='running' — session_b's claim
    # query (WHERE status='queued') correctly finds nothing.
    claimed_by_b = service_b.claim_next()
    assert claimed_by_b is None