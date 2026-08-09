import pytest

from story_generator.generation.vocabulary_selection import (
    EmptyVocabularyListError,
    select_vocabulary,
)
from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList

pytestmark = pytest.mark.db


def _make_list_with_items(db_session, *, skritter_list_id: str, n_items: int) -> VocabularyList:
    vocab_list = VocabularyList(skritter_list_id=skritter_list_id, name="Test list")
    db_session.add(vocab_list)
    db_session.flush()

    for i in range(n_items):
        item = VocabularyItem(
            skritter_vocab_id=f"{skritter_list_id}-item-{i}",
            language="zh",
            writing=f"词{i}",
            reading=f"ci{i}",
            definition_en=f"word {i}",
        )
        db_session.add(item)
        db_session.flush()
        vocab_list.items.append(item)

    db_session.flush()
    return vocab_list


def test_select_vocabulary_raises_on_empty_list(db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="empty", n_items=0)

    with pytest.raises(EmptyVocabularyListError):
        select_vocabulary(db_session, vocab_list, target_vocabulary_count=5)


def test_select_vocabulary_caps_short_list_to_available_items(db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="short", n_items=3)

    result = select_vocabulary(db_session, vocab_list, target_vocabulary_count=10)

    assert len(result) == 3


def test_select_vocabulary_caps_oversized_list_to_target_count(db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="oversized", n_items=20)

    result = select_vocabulary(db_session, vocab_list, target_vocabulary_count=5)

    assert len(result) == 5


def test_select_vocabulary_is_deterministic_ordered_by_id(db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="deterministic", n_items=5)

    first = select_vocabulary(db_session, vocab_list, target_vocabulary_count=3)
    second = select_vocabulary(db_session, vocab_list, target_vocabulary_count=3)

    assert first == second
    assert [item["id"] for item in first] == sorted(item["id"] for item in first)


def test_select_vocabulary_preserves_reading_and_definition(db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="preserve", n_items=2)

    result = select_vocabulary(db_session, vocab_list, target_vocabulary_count=2)

    for item in result:
        assert item["reading"] is not None
        assert item["definition_en"] is not None
        assert item["reading"].startswith("ci")
        assert item["definition_en"].startswith("word")