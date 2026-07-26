from pydantic import BaseModel


class VocabularyResponse(BaseModel):
    id: int
    skritter_vocab_id: str
    language: str
    writing: str
    reading: str | None
    definition_en: str | None


class PaginatedVocabularyResponse(BaseModel):
    items: list[VocabularyResponse]
    total: int
    limit: int
    offset: int
