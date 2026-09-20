from datetime import UTC, datetime

import pytest

from story_generator.vocabulary.persistence.models import (
    VocabularyItem as VocabularyItemModel,
)
from story_generator.vocabulary.persistence.models import (
    VocabularyList,
)
from story_generator.vocabulary.persistence.repository import VocabularyRepository
from story_generator.vocabulary.types import SkritterVocabularyRecord


@pytest.mark.db
def test_ensure_vocab(db_session):
    repo = VocabularyRepository(db_session)

    vocab = SkritterVocabularyRecord(
        skritter_vocab_id="test-123",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    repo.ensure_vocab(vocab)

    result = (
        db_session.query(VocabularyItemModel)
        .filter_by(skritter_vocab_id="test-123")
        .one()
    )

    assert result.writing == "你好"
    assert result.reading == "ni3 hao3"
    assert result.definition_en == "hello"


@pytest.mark.db
def test_ensure_duplicate_vocab_does_not_raise(db_session):
    repo = VocabularyRepository(db_session)

    vocab = SkritterVocabularyRecord(
        skritter_vocab_id="duplicate-test",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    repo.ensure_vocab(vocab)
    repo.ensure_vocab(vocab)  # should not raise


@pytest.mark.db
def test_ensure_vocab_refreshes_existing_skritter_data(db_session):
    repo = VocabularyRepository(db_session)
    original = SkritterVocabularyRecord(
        skritter_vocab_id="refresh-test",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )
    vocabulary_id, inserted = repo.ensure_vocab(original)
    assert inserted is True

    existing = db_session.get(VocabularyItemModel, vocabulary_id)
    existing.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    db_session.flush()

    refreshed = SkritterVocabularyRecord(
        skritter_vocab_id="refresh-test",
        language="zh-Hans",
        writing="您好",
        reading="nin2 hao3",
        definition_en="hello (polite)",
    )
    refreshed_id, inserted = repo.ensure_vocab(refreshed)
    db_session.expire_all()

    saved = db_session.get(VocabularyItemModel, refreshed_id)
    assert inserted is False
    assert refreshed_id == vocabulary_id
    assert saved.language == "zh-Hans"
    assert saved.writing == "您好"
    assert saved.reading == "nin2 hao3"
    assert saved.definition_en == "hello (polite)"
    assert saved.updated_at > datetime(2000, 1, 1, tzinfo=UTC)


@pytest.mark.db
def test_ensure_list_refreshes_existing_skritter_name(db_session):
    repo = VocabularyRepository(db_session)
    list_id = repo.ensure_list("refresh-list", "Original name")

    existing = db_session.get(VocabularyList, list_id)
    existing.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    db_session.flush()

    refreshed_id = repo.ensure_list("refresh-list", "Renamed list")
    db_session.expire_all()

    saved = db_session.get(VocabularyList, refreshed_id)
    assert refreshed_id == list_id
    assert saved.name == "Renamed list"
    assert saved.updated_at > datetime(2000, 1, 1, tzinfo=UTC)
