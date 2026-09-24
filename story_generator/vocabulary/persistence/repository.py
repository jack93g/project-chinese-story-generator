from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from story_generator.vocabulary.persistence.models import (
    VocabularyItem,
    VocabularyList,
    list_vocabulary,
)
from story_generator.vocabulary.types import SkritterVocabularyRecord


class VocabularyRepository:
    """Persistence operations for vocabulary and vocabulary lists.

    Transaction boundaries are controlled by the calling service.
    """

    def __init__(self, session: Session):
        self.session = session

    def list_page(self, limit: int, offset: int) -> list[VocabularyItem]:
        return (
            self.session.query(VocabularyItem)
            .filter(VocabularyItem.skritter_vocab_id.is_not(None))
            .order_by(VocabularyItem.id.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count(self) -> int:
        return (
            self.session.query(VocabularyItem)
            .filter(VocabularyItem.skritter_vocab_id.is_not(None))
            .count()
        )

    def get_or_create_custom_items(self, writings: list[str]) -> list[VocabularyItem]:
        """Resolve user-entered words to items, in input order.

        Reuses an existing item with the same writing (so Skritter's reading
        and definition come along); otherwise creates a custom item with no
        reading/definition. Does not touch list membership.
        """
        items = []
        for writing in writings:
            item = self._find_by_writing(writing)
            if item is None:
                self.session.execute(
                    pg_insert(VocabularyItem)
                    .values(language="zh", writing=writing)
                    .on_conflict_do_nothing(
                        index_elements=["writing"],
                        index_where=VocabularyItem.skritter_vocab_id.is_(None),
                    )
                )
                item = self._find_by_writing(writing)
            items.append(item)
        return items

    def _find_by_writing(self, writing: str) -> VocabularyItem | None:
        return (
            self.session.query(VocabularyItem)
            .filter_by(language="zh", writing=writing)
            .order_by(VocabularyItem.id.asc())
            .first()
        )

    def ensure_list(self, skritter_list_id: str, name: str) -> int:
        insert_stmt = pg_insert(VocabularyList).values(
            skritter_list_id=skritter_list_id,
            name=name,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["skritter_list_id"],
            set_={
                "name": insert_stmt.excluded.name,
                "updated_at": func.now(),
            },
        ).returning(VocabularyList.id)
        return self.session.execute(stmt).scalar_one()

    def ensure_vocab(self, vocab: SkritterVocabularyRecord) -> tuple[int, bool]:
        existing_id = (
            self.session.query(VocabularyItem.id)
            .filter_by(skritter_vocab_id=vocab.skritter_vocab_id)
            .scalar()
        )
        insert_stmt = pg_insert(VocabularyItem).values(
            skritter_vocab_id=vocab.skritter_vocab_id,
            language=vocab.language,
            writing=vocab.writing,
            reading=vocab.reading,
            definition_en=vocab.definition_en,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["skritter_vocab_id"],
            set_={
                "language": insert_stmt.excluded.language,
                "writing": insert_stmt.excluded.writing,
                "reading": insert_stmt.excluded.reading,
                "definition_en": insert_stmt.excluded.definition_en,
                "updated_at": func.now(),
            },
        ).returning(VocabularyItem.id)
        vocabulary_id = self.session.execute(stmt).scalar_one()
        return vocabulary_id, existing_id is None

    def link_vocab_to_list(self, list_id: int, vocabulary_id: int) -> None:
        stmt = (
            pg_insert(list_vocabulary)
            .values(list_id=list_id, vocabulary_id=vocabulary_id)
            .on_conflict_do_nothing(index_elements=["list_id", "vocabulary_id"])
        )
        self.session.execute(stmt)

    def list_lists(self, limit: int, offset: int) -> list[tuple[VocabularyList, int]]:
        return (
            self.session.query(
                VocabularyList, func.count(list_vocabulary.c.vocabulary_id)
            )
            .outerjoin(list_vocabulary, list_vocabulary.c.list_id == VocabularyList.id)
            .group_by(VocabularyList.id)
            .order_by(VocabularyList.id.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_lists(self) -> int:
        return self.session.query(VocabularyList).count()

    def get_list_by_id(self, list_id: int) -> VocabularyList | None:
        return self.session.get(VocabularyList, list_id)
