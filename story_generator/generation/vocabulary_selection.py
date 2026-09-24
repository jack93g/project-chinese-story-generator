"""
Deterministic vocabulary selection for a story-generation request.

Custom words (user-entered) always come first, in the order given. The
list then fills the remaining slots up to target_vocabulary_count,
ordered by VocabularyItem.id ascending and skipping words already
chosen as custom — no randomness, fully reproducible:

- Neither custom words nor list items   -> EmptyVocabularyListError.
- Fewer items than target_vocabulary_count -> silently capped to
  however many items exist ("short list").
- More items than target_vocabulary_count  -> capped to exactly
  target_vocabulary_count ("oversized list").
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from story_generator.vocabulary.persistence.models import (
    VocabularyItem,
    VocabularyList,
    list_vocabulary,
)


class EmptyVocabularyListError(Exception):
    def __init__(self, vocabulary_list_id: int | None):
        self.vocabulary_list_id = vocabulary_list_id
        super().__init__(
            f"Vocabulary list {vocabulary_list_id} has no vocabulary items"
        )


def _snapshot_entry(item: VocabularyItem) -> dict:
    return {
        "id": item.id,
        "writing": item.writing,
        "reading": item.reading,
        "definition_en": item.definition_en,
    }


def select_vocabulary(
    db: Session,
    vocabulary_list: VocabularyList | None,
    target_vocabulary_count: int,
    custom_items: list[VocabularyItem] | None = None,
) -> list[dict]:
    """
    Returns the immutable snapshot shape stored on
    StoryGenerationRequest.selected_vocabulary_snapshot, e.g.
    [{"id": 10, "writing": "菜单", "reading": "càidān", "definition_en": "menu"}]
    """
    selected = [_snapshot_entry(item) for item in custom_items or []]
    remaining = target_vocabulary_count - len(selected)

    if vocabulary_list is not None and remaining > 0:
        stmt = (
            select(VocabularyItem)
            .join(list_vocabulary, list_vocabulary.c.vocabulary_id == VocabularyItem.id)
            .where(list_vocabulary.c.list_id == vocabulary_list.id)
            .where(VocabularyItem.writing.not_in([e["writing"] for e in selected]))
            .order_by(VocabularyItem.id.asc())
            .limit(remaining)
        )
        selected.extend(
            _snapshot_entry(item) for item in db.execute(stmt).scalars().all()
        )

    if not selected:
        raise EmptyVocabularyListError(
            vocabulary_list.id if vocabulary_list is not None else None
        )

    return selected
