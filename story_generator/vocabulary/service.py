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
