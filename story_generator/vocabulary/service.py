from __future__ import annotations

from story_generator.vocabulary.persistence.models import VocabularyList
from story_generator.vocabulary.persistence.repository import VocabularyRepository
from story_generator.vocabulary.schemas import (
    PaginatedVocabularyListResponse,
    PaginatedVocabularyResponse,
    VocabularyListDetail,
    VocabularyListSummary,
    VocabularyResponse,
)


class VocabularyService:
    def __init__(self, repository: VocabularyRepository):
        self.repository = repository

    def list(self, limit: int, offset: int) -> PaginatedVocabularyResponse:
        vocabulary = self.repository.list_page(limit=limit, offset=offset)
        total = self.repository.count()

        items = [
            VocabularyResponse(
                id=item.id,
                skritter_vocab_id=item.skritter_vocab_id,
                language=item.language,
                writing=item.writing,
                reading=item.reading,
                definition_en=item.definition_en,
            )
            for item in vocabulary
        ]

        return PaginatedVocabularyResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )


class VocabularyListNotFoundError(Exception):
    def __init__(self, list_id: int):
        self.list_id = list_id
        super().__init__(f"Vocabulary list {list_id} not found")


class SkritterListNotFoundError(Exception):
    def __init__(self, skritter_list_id: str):
        self.skritter_list_id = skritter_list_id
        super().__init__(
            f"No vocabulary list with Skritter ID {skritter_list_id} "
            "(run `manage-lists list` to see them)"
        )


class VocabularyListService:
    def __init__(self, repository: VocabularyRepository):
        self.repository = repository

    def list(self, limit: int, offset: int) -> PaginatedVocabularyListResponse:
        rows = self.repository.list_lists(limit=limit, offset=offset)
        total = self.repository.count_lists()

        items = [
            VocabularyListSummary(
                id=vocab_list.id,
                skritter_list_id=vocab_list.skritter_list_id,
                name=vocab_list.name,
                item_count=item_count,
                created_at=vocab_list.created_at,
                updated_at=vocab_list.updated_at,
            )
            for vocab_list, item_count in rows
        ]

        return PaginatedVocabularyListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def list_all(self) -> list[tuple[VocabularyList, int]]:
        """Every list with its word count, for the manage-lists command."""
        return self.repository.list_all_lists()

    def set_hidden(
        self, skritter_list_ids: list[str], hidden: bool
    ) -> list[VocabularyList]:
        """Hide or show lists by Skritter ID; changes nothing if any is unknown."""
        lists = self.repository.get_lists_by_skritter_ids(skritter_list_ids)
        found = {vocab_list.skritter_list_id for vocab_list in lists}
        missing = [list_id for list_id in skritter_list_ids if list_id not in found]
        if missing:
            raise SkritterListNotFoundError(missing[0])
        for vocab_list in lists:
            vocab_list.hidden = hidden
        return lists

    def get(self, list_id: int) -> VocabularyListDetail:
        vocab_list = self.repository.get_list_by_id(list_id)

        if vocab_list is None:
            raise VocabularyListNotFoundError(list_id)

        return VocabularyListDetail(
            id=vocab_list.id,
            skritter_list_id=vocab_list.skritter_list_id,
            name=vocab_list.name,
            item_count=len(vocab_list.items),
            created_at=vocab_list.created_at,
            updated_at=vocab_list.updated_at,
            items=[
                VocabularyResponse(
                    id=item.id,
                    skritter_vocab_id=item.skritter_vocab_id,
                    language=item.language,
                    writing=item.writing,
                    reading=item.reading,
                    definition_en=item.definition_en,
                )
                for item in vocab_list.items
            ],
        )
