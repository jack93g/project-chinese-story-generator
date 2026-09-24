from datetime import datetime

from pydantic import BaseModel

from story_generator.vocabulary.schemas import VocabularyResponse


class StorySummary(BaseModel):
    """
    Public summary of a saved story.

    Deliberately excludes raw provider payloads and generation-request
    internals (see story_generation_requests, owned by Milestone 3) —
    only story-level, display-safe fields are exposed here.
    """

    id: int
    title: str
    created_at: datetime
    target_hsk: int | None


class PaginatedStoryResponse(BaseModel):
    items: list[StorySummary]
    total: int
    limit: int
    offset: int


class StoryDetail(StorySummary):
    """
    A saved story for reading.

    provider and model name what wrote the story, so the reader can show
    it; they are the only generation-request fields exposed, and are None
    for a story with no linked request.
    """

    content: str
    selected_vocabulary: list[VocabularyResponse]
    provider: str | None
    model: str | None
