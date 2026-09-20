from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SyncRunResponse(BaseModel):
    id: int
    source: str
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    summary: dict[str, Any]


class SyncStatusResponse(BaseModel):
    latest_run: SyncRunResponse | None


class SkritterResponseError(ValueError):
    """A successful Skritter response did not match the expected API shape."""


def validate_skritter_response(
    model: type[BaseModel], payload: object, endpoint: str
) -> BaseModel:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise SkritterResponseError(
            f"Malformed Skritter response from {endpoint}: {details}"
        ) from exc


class SkritterDefinitions(BaseModel):
    en: str | None = None


class SkritterVocabulary(BaseModel):
    id: str
    language: str | None = None
    lang: str | None = None
    writing: str
    reading: str
    customDefinition: str | None = None
    definitions: SkritterDefinitions = Field(default_factory=SkritterDefinitions)

    @model_validator(mode="after")
    def requires_language(self) -> "SkritterVocabulary":
        if not self.language and not self.lang:
            raise ValueError("either 'language' or 'lang' is required")
        return self


class SkritterVocabularyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vocabs: list[SkritterVocabulary] = Field(alias="Vocabs", min_length=1)


class SkritterListRow(BaseModel):
    vocabId: str


class SkritterListSection(BaseModel):
    rows: list[SkritterListRow]


class SkritterVocabularyList(BaseModel):
    id: str
    name: str
    sections: list[SkritterListSection]


class SkritterVocabularyListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vocab_list: SkritterVocabularyList = Field(alias="VocabList")


class SkritterVocabularyListSummary(BaseModel):
    id: str
    name: str


class SkritterVocabularyListsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vocab_lists: list[SkritterVocabularyListSummary] = Field(alias="VocabLists")
    cursor: str | None = None
