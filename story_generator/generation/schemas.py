from pydantic import BaseModel, Field, field_validator

# TODO: placeholder cap until product specifies the real maximum story
# length. Mirror any change here in the story_generation_requests
# word-count CHECK constraint (migration) — this is validated at both
# layers deliberately; see StoryGenerationRequest docstring.
MAX_TARGET_WORD_COUNT = 1000


class CreateGenerationRequestSchema(BaseModel):
    """
    Input schema for creating a new StoryGenerationRequest.

    Field-level bounds mirror (but do not replace) the DB CHECK
    constraints on StoryGenerationRequest — validating here lets us
    reject bad input with a clean 422 before touching the DB; the DB
    constraints remain the source of truth.

    provider/model are deliberately NOT accepted here — they're
    resolved from trusted server configuration in
    GenerationRequestService.create(), not chosen by the caller, so
    StoryGenerationRequest.provider/.model remain a trustworthy record
    of what actually ran rather than an unvalidated client claim.
    """

    vocabulary_list_id: int
    target_hsk_level: int = Field(ge=1, le=6)
    target_word_count: int = Field(gt=0, le=MAX_TARGET_WORD_COUNT)
    target_vocabulary_count: int = Field(ge=1, le=15)
    topic: str | None = None

    @field_validator("topic")
    @classmethod
    def blank_topic_to_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class GenerationRequestDetail(BaseModel):
    id: int
    vocabulary_list_id: int
    target_hsk_level: int
    topic: str | None
    target_word_count: int
    target_vocabulary_count: int
    selected_vocabulary_snapshot: list[dict]
    status: str
    prompt_version: str
    provider: str
    model: str

    model_config = {"from_attributes": True}