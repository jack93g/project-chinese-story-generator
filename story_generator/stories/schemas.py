from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

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


class QuizQuestion(BaseModel):
    """A comprehension question as the reader sees it: without its answer,
    which the API gives back only once an attempt is marked."""

    question: str
    options: list[str]


class StoryDetail(StorySummary):
    """
    A saved story for reading.

    provider and model name what wrote the story, so the reader can show
    it; they are the only generation-request fields exposed, and are None
    for a story with no linked request.

    translation_en is the English, one string per paragraph of content
    (non-blank lines); None for older stories. It may not line up with
    the paragraphs, in which case the reader shows it as one block.

    questions are the story's comprehension questions, answered through
    POST /stories/{id}/quiz-attempts; None for stories from before
    story-v7.
    """

    content: str
    translation_en: list[str] | None
    questions: list[QuizQuestion] | None
    selected_vocabulary: list[VocabularyResponse]
    provider: str | None
    model: str | None


# Well above any real quiz (story-v7 asks for at most 5 questions); it only
# bounds the work of rejecting a nonsense request.
MAX_QUIZ_ANSWERS = 50


class SubmitQuizAttemptSchema(BaseModel):
    """The chosen option index for each question, in question order. Every
    question must be answered."""

    answers: list[Annotated[int, Field(ge=0)]] = Field(
        min_length=1, max_length=MAX_QUIZ_ANSWERS
    )


class QuizQuestionResult(BaseModel):
    """evidence is the sentence of the story that settles the answer, for
    questions from story-v9 on; None before that."""

    selected: int
    answer: int
    correct: bool
    evidence: str | None


class QuizAttemptResponse(BaseModel):
    """A marked attempt: the score, and each question's chosen and correct
    options, in question order."""

    id: int
    correct_count: int
    question_count: int
    results: list[QuizQuestionResult]


class FlagQuestionSchema(BaseModel):
    """The question being reported, as its index in the story's questions."""

    question_index: int = Field(ge=0)


class QuestionFlagResponse(BaseModel):
    id: int
