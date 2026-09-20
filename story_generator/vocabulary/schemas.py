from datetime import datetime

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


class VocabularyListSummary(BaseModel):
    id: int
    skritter_list_id: str
    name: str
    item_count: int
    created_at: datetime
    updated_at: datetime


class PaginatedVocabularyListResponse(BaseModel):
    items: list[VocabularyListSummary]
    total: int
    limit: int
    offset: int


class VocabularyListDetail(VocabularyListSummary):
    items: list[VocabularyResponse]
