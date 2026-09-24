import re

from pydantic import BaseModel, Field, field_validator, model_validator

# TODO: placeholder cap until product specifies the real maximum story
# length. Mirror any change here in the story_generation_requests
# word-count CHECK constraint (migration) — this is validated at both
# layers deliberately; see StoryGenerationRequest docstring.
MAX_TARGET_WORD_COUNT = 1000
MAX_TOPIC_LENGTH = 200
MAX_CUSTOM_WORDS = 15
MAX_CUSTOM_WORD_LENGTH = 20
# CJK-only: custom words are interpolated into the LLM prompt, so anything
# else (latin text, punctuation) is rejected rather than sanitised.
_CUSTOM_WORD_PATTERN = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff]+$")

# Error codes we generate ourselves — their error_message is written
# by us and safe to expose verbatim via the API. Anything else (e.g.
# a raw ProviderXxxError class name) may echo provider-side text we
# didn't design for external display, so it's collapsed to a generic
# message instead. error_code itself is always exposed either way.
_SAFE_DIAGNOSTIC_ERROR_CODES = {
    "InsufficientVocabularyCoverage",
    "StaleWorkerRetryLimitExceeded",
}

_GENERIC_ERROR_MESSAGE = "Story generation failed. You may retry this request."


def safe_error_message(error_code: str | None, error_message: str | None) -> str | None:
    if error_code is None:
        return None
    if error_code in _SAFE_DIAGNOSTIC_ERROR_CODES:
        return error_message
    return _GENERIC_ERROR_MESSAGE


class CreateGenerationRequestSchema(BaseModel):
    """
    Input schema for creating a new StoryGenerationRequest.

    Field-level bounds mirror (but do not replace) the DB CHECK
    constraints on StoryGenerationRequest — validating here lets us
    reject bad input with a clean 422 before touching the DB; the DB
    constraints remain the source of truth.

    provider/model are deliberately NOT accepted here — they're
    resolved from trusted server configuration in
    GenerationRequestService.create(), not chosen by the caller.
    """

    vocabulary_list_id: int | None = None
    target_hsk_level: int = Field(ge=1, le=6)
    target_word_count: int = Field(gt=0, le=MAX_TARGET_WORD_COUNT)
    target_vocabulary_count: int = Field(ge=1, le=15)
    topic: str | None = Field(default=None, max_length=MAX_TOPIC_LENGTH)
    custom_words: list[str] = Field(default_factory=list, max_length=MAX_CUSTOM_WORDS)

    @field_validator("custom_words")
    @classmethod
    def normalize_custom_words(cls, words: list[str]) -> list[str]:
        cleaned: list[str] = []
        for word in words:
            word = word.strip()
            if not word or word in cleaned:
                continue
            if len(word) > MAX_CUSTOM_WORD_LENGTH or not _CUSTOM_WORD_PATTERN.match(
                word
            ):
                raise ValueError(
                    f"Custom words must be Chinese characters only, at most "
                    f"{MAX_CUSTOM_WORD_LENGTH} long: {word!r}"
                )
            cleaned.append(word)
        return cleaned

    @model_validator(mode="after")
    def require_a_vocabulary_source(self) -> "CreateGenerationRequestSchema":
        if self.vocabulary_list_id is None and not self.custom_words:
            raise ValueError("Provide a vocabulary list, custom words, or both")
        if len(self.custom_words) > self.target_vocabulary_count:
            raise ValueError(
                f"{len(self.custom_words)} custom words exceed "
                f"target_vocabulary_count ({self.target_vocabulary_count})"
            )
        return self

    @field_validator("topic")
    @classmethod
    def blank_topic_to_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class GenerationCreatedResponse(BaseModel):
    """Returned immediately by POST /story-generations, before any provider call."""

    id: int
    status: str


class GenerationStatusResponse(BaseModel):
    """Returned by GET /story-generations/{id} and the retry endpoint."""

    id: int
    status: str
    error_code: str | None
    error_message: str | None
    story_id: int | None

    @classmethod
    def from_request(cls, request, story_id: int | None) -> "GenerationStatusResponse":
        return cls(
            id=request.id,
            status=request.status,
            error_code=request.error_code,
            error_message=safe_error_message(request.error_code, request.error_message),
            story_id=story_id,
        )
