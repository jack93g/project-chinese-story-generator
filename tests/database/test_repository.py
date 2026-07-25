from story_generator.database.session import SessionLocal
from story_generator.database.repository import Repository
from story_generator.vocabulary.models import VocabularyItem
import pytest


@pytest.mark.db
def test_ensure_vocab(db_session):
    repo = Repository(db_session)

    vocab = VocabularyItem(
        skritter_vocab_id="test-123",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    repo.ensure_vocab(vocab)

    from story_generator.database.models import VocabularyItem as VocabularyItemModel
    result = db_session.query(VocabularyItemModel).filter_by(
        skritter_vocab_id="test-123"
    ).one()

    assert result.writing == "你好"
    assert result.reading == "ni3 hao3"
    assert result.definition_en == "hello"

@pytest.mark.db
def test_ensure_duplicate_vocab_does_not_raise(db_session):
    repo = Repository(db_session)

    vocab = VocabularyItem(
        skritter_vocab_id="duplicate-test",
        language="zh",
        writing="你好",
        reading="ni3 hao3",
        definition_en="hello",
    )

    repo.ensure_vocab(vocab)
    repo.ensure_vocab(vocab)  # should not raise