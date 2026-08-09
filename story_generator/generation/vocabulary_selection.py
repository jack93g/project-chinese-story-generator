"""
Deterministic vocabulary selection for a story-generation request.

Selection is capped to target_vocabulary_count and ordered by
VocabularyItem.id ascending — no randomness, no seed, fully
reproducible for a given (list, count) pair:

- Empty list                              -> EmptyVocabularyListError.
- Fewer items than target_vocabulary_count -> silently capped to
  however many items exist ("short list").
- More items than target_vocabulary_count  -> capped to exactly
  target_vocabulary_count, same deterministic order ("oversized list").
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from story_generator.vocabulary.persistence.models import (
    VocabularyItem,
    VocabularyList,
    list_vocabulary,
)


class EmptyVocabularyListError(Exception):
    def __init__(self, vocabulary_list_id: int):
        self.vocabulary_list_id = vocabulary_list_id
        super().__init__(f"Vocabulary list {vocabulary_list_id} has no vocabulary items")


def select_vocabulary(
    db: Session, vocabulary_list: VocabularyList, target_vocabulary_count: int
) -> list[dict]:
    """
    Returns the immutable snapshot shape stored on
    StoryGenerationRequest.selected_vocabulary_snapshot, e.g.
    [{"id": 10, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}]
    """
    stmt = (
        select(VocabularyItem)
        .join(list_vocabulary, list_vocabulary.c.vocabulary_id == VocabularyItem.id)
        .where(list_vocabulary.c.list_id == vocabulary_list.id)
        .order_by(VocabularyItem.id.asc())
        .limit(target_vocabulary_count)
    )
    items = db.execute(stmt).scalars().all()

    if not items:
        raise EmptyVocabularyListError(vocabulary_list.id)

    return [
        {
            "id": item.id,
            "writing": item.writing,
            "reading": item.reading,
            "definition_en": item.definition_en,
        }
        for item in items
    ]