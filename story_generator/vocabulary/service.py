from story_generator.vocabulary.persistence.repository import VocabularyRepository
from story_generator.vocabulary.schemas import (
    PaginatedVocabularyResponse,
    VocabularyResponse,
)


class VocabularyService:
    def __init__(self, repository: VocabularyRepository):
        self.repository = repository

    def list(self, limit: int, offset: int) -> PaginatedVocabularyResponse:
        vocabulary = self.repository.list(limit=limit, offset=offset)
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
