from collections.abc import Sequence

from story_generator.stories.persistence.models import QuestionFlag, QuizAttempt
from story_generator.stories.persistence.repository import StoryRepository
from story_generator.stories.schemas import (
    PaginatedStoryResponse,
    QuestionFlagResponse,
    QuizAttemptResponse,
    QuizQuestion,
    QuizQuestionResult,
    StoryDetail,
    StorySummary,
)
from story_generator.vocabulary.schemas import VocabularyResponse


class StoryNotFoundError(Exception):
    def __init__(self, story_id: int):
        self.story_id = story_id
        super().__init__(f"Story {story_id} not found")


class StoryHasNoQuizError(Exception):
    def __init__(self, story_id: int):
        self.story_id = story_id
        super().__init__(f"Story {story_id} has no comprehension questions")


class InvalidQuestionIndexError(Exception):
    def __init__(self, story_id: int, question_index: int, question_count: int):
        super().__init__(
            f"Story {story_id} has {question_count} questions; "
            f"question {question_index} is out of range"
        )


class InvalidQuizAnswersError(Exception):
    """The answers don't fit the story's questions (wrong number of them, or
    an option index out of range). The message is safe to show."""


class StoryService:
    def __init__(self, repository: StoryRepository):
        self.repository = repository

    def list(self, limit: int, offset: int) -> PaginatedStoryResponse:
        stories = self.repository.list_page(limit=limit, offset=offset)
        total = self.repository.count()

        items = [
            StorySummary(
                id=story.id,
                title=story.title,
                created_at=story.created_at,
                target_hsk=story.target_hsk,
            )
            for story in stories
        ]

        return PaginatedStoryResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get(self, story_id: int) -> StoryDetail:
        story = self.repository.get_by_id(story_id)

        if story is None:
            raise StoryNotFoundError(story_id)

        request = story.generation_request

        return StoryDetail(
            id=story.id,
            title=story.title,
            created_at=story.created_at,
            target_hsk=story.target_hsk,
            content=story.content,
            translation_en=story.translation_en,
            questions=[
                QuizQuestion(question=q["question"], options=q["options"])
                for q in story.comprehension_questions
            ]
            if story.comprehension_questions is not None
            else None,
            selected_vocabulary=[
                VocabularyResponse(
                    id=item.id,
                    skritter_vocab_id=item.skritter_vocab_id,
                    language=item.language,
                    writing=item.writing,
                    reading=item.reading,
                    definition_en=item.definition_en,
                )
                for item in story.vocabulary_items
            ],
            provider=request.provider if request else None,
            model=request.model if request else None,
        )

    def delete(self, story_id: int) -> None:
        story = self.repository.get_by_id(story_id)

        if story is None:
            raise StoryNotFoundError(story_id)

        self.repository.delete(story)

    def submit_quiz_attempt(
        self, story_id: int, answers: Sequence[int], user_id: int | None
    ) -> QuizAttemptResponse:
        """Mark answers against the story's questions and record the attempt."""
        story = self.repository.get_by_id(story_id)

        if story is None:
            raise StoryNotFoundError(story_id)
        questions = story.comprehension_questions
        if questions is None:
            raise StoryHasNoQuizError(story_id)

        if len(answers) != len(questions):
            raise InvalidQuizAnswersError(
                f"Expected {len(questions)} answers, one per question, "
                f"got {len(answers)}"
            )
        for number, (answer, question) in enumerate(
            zip(answers, questions, strict=True), 1
        ):
            if answer >= len(question["options"]):
                raise InvalidQuizAnswersError(
                    f"Question {number} has {len(question['options'])} options; "
                    f"answer {answer} is out of range"
                )

        results = [
            QuizQuestionResult(
                selected=answer,
                answer=question["answer"],
                correct=answer == question["answer"],
                evidence=question.get("evidence"),
            )
            for answer, question in zip(answers, questions, strict=True)
        ]
        correct_count = sum(result.correct for result in results)
        attempt = self.repository.add_quiz_attempt(
            QuizAttempt(
                story_id=story.id,
                user_id=user_id,
                answers=list(answers),
                correct_count=correct_count,
                question_count=len(questions),
            )
        )

        return QuizAttemptResponse(
            id=attempt.id,
            correct_count=correct_count,
            question_count=len(questions),
            results=results,
        )

    def flag_question(
        self, story_id: int, question_index: int, user_id: int | None
    ) -> QuestionFlagResponse:
        """Record a report that one of the story's questions seems wrong."""
        story = self.repository.get_by_id(story_id)

        if story is None:
            raise StoryNotFoundError(story_id)
        questions = story.comprehension_questions
        if questions is None:
            raise StoryHasNoQuizError(story_id)
        if question_index >= len(questions):
            raise InvalidQuestionIndexError(story_id, question_index, len(questions))

        flag = self.repository.add_question_flag(
            QuestionFlag(
                story_id=story.id, user_id=user_id, question_index=question_index
            )
        )
        return QuestionFlagResponse(id=flag.id)
