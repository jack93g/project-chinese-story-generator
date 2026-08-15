import pytest
from datetime import datetime, timezone

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.generation.persistence.repository import GenerationRequestRepository
from story_generator.generation.persistence.service import (
    MAX_ATTEMPTS,
    GenerationRequestService,
    RetryLimitExceededError,
)
from story_generator.vocabulary.persistence.models import VocabularyList

pytestmark = pytest.mark.db


def test_retry_raises_once_max_attempts_reached(db_session):
    vocab_list = VocabularyList(skritter_list_id="retry-limit", name="Test list")
    db_session.add(vocab_list)
    db_session.flush()

    now = datetime.now(timezone.utc)
    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=100,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=[],
        prompt_version="story-v1",
        provider="openai",
        model="gpt-test",
        status="failed",
        attempt_count=MAX_ATTEMPTS,
        started_at=now,
        completed_at=now,
    )
    db_session.add(request)
    db_session.commit()

    service = GenerationRequestService(GenerationRequestRepository(db_session))

    with pytest.raises(RetryLimitExceededError):
        service.retry(request.id)