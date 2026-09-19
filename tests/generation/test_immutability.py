from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import DBAPIError

from story_generator.generation.persistence.models import StoryGenerationRequest
from story_generator.vocabulary.persistence.models import VocabularyList


pytestmark = pytest.mark.db


def test_selected_vocabulary_snapshot_cannot_be_mutated_after_creation(db_session):
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

    request.selected_vocabulary_snapshot = [
        {"id": 2, "writing": "再见", "reading": "zai4 jian4", "definition_en": "goodbye"}
    ]

    with pytest.raises(DBAPIError, match="immutable"):
        db_session.flush()

    # The session is left in a failed-transaction state after the DB
    # error; roll back explicitly so the db_session fixture's own
    # teardown rollback doesn't itself error out.
    db_session.rollback()


def test_unrelated_field_updates_still_succeed(db_session):
    """
    Sanity check that the trigger only blocks changes to the snapshot
    column itself, not ordinary status-lifecycle updates.
    """
    vocab_list = VocabularyList(skritter_list_id="list-2", name="Another list")
    db_session.add(vocab_list)
    db_session.flush()

    snapshot = [{"id": 1, "writing": "你好", "reading": "ni3 hao3", "definition_en": "hello"}]

    request = StoryGenerationRequest(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=2,
        target_word_count=150,
        target_vocabulary_count=1,
        selected_vocabulary_snapshot=snapshot,
        prompt_version="story-v1",
        provider="anthropic",
        model="claude-sonnet-5",
    )
    db_session.add(request)
    db_session.flush()

    request.status = "running"
    request.started_at = datetime.now(timezone.utc)
    db_session.flush()  # should not raise

    assert request.status == "running"
    assert request.selected_vocabulary_snapshot == snapshot