"""
Reviewing comprehension questions, for the manage-questions command.

Questions are machine-written, and readers can flag one that seems wrong
(QuestionFlag). This gathers each question with its flags and how readers
have done on it, so a person can judge whether the question is bad. A
question most readers get wrong despite knowing the story is a hint that
its answer key is, too.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from story_generator.stories.persistence.models import Story
from story_generator.stories.persistence.repository import StoryRepository
from story_generator.stories.service import StoryHasNoQuizError, StoryNotFoundError


@dataclass(frozen=True)
class QuestionReview:
    story_id: int
    story_title: str
    # Index into the story's comprehension_questions (0-based).
    index: int
    # {"question", "options", "answer"} and, from story-v9, "evidence".
    question: dict
    flag_count: int
    last_flagged_at: datetime | None
    attempt_count: int
    correct_count: int


class QuestionReviewService:
    def __init__(self, repository: StoryRepository):
        self.repository = repository

    def flagged(self) -> list[QuestionReview]:
        """Every flagged question, most flagged first."""
        summary = self.repository.question_flag_summary()
        stories = {
            story_id: self.repository.get_by_id(story_id)
            for story_id in {story_id for story_id, _, _, _ in summary}
        }
        scores = self._scores(list(stories))
        return [
            self._review(stories[story_id], index, count, last, scores)
            for story_id, index, count, last in summary
        ]

    def story(self, story_id: int) -> tuple[Story, list[QuestionReview]]:
        """A story and all of its questions, flagged or not, in order."""
        story = self.repository.get_by_id(story_id)
        if story is None:
            raise StoryNotFoundError(story_id)
        if story.comprehension_questions is None:
            raise StoryHasNoQuizError(story_id)

        flags = {
            index: (count, last)
            for _, index, count, last in self.repository.question_flag_summary(story_id)
        }
        scores = self._scores([story_id])
        return story, [
            self._review(story, index, *flags.get(index, (0, None)), scores)
            for index in range(len(story.comprehension_questions))
        ]

    def _scores(self, story_ids: list[int]) -> dict[tuple[int, int], list[int]]:
        """(story_id, question index) -> [attempts, answered correctly]."""
        scores: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
        stories = {
            story_id: self.repository.get_by_id(story_id) for story_id in story_ids
        }
        for story_id, answers in self.repository.quiz_answers(story_ids):
            questions = stories[story_id].comprehension_questions
            for index, (answer, question) in enumerate(
                zip(answers, questions, strict=True)
            ):
                score = scores[(story_id, index)]
                score[0] += 1
                score[1] += answer == question["answer"]
        return scores

    @staticmethod
    def _review(story, index, flag_count, last_flagged_at, scores) -> QuestionReview:
        attempts, correct = scores.get((story.id, index), (0, 0))
        return QuestionReview(
            story_id=story.id,
            story_title=story.title,
            index=index,
            question=story.comprehension_questions[index],
            flag_count=flag_count,
            last_flagged_at=last_flagged_at,
            attempt_count=attempts,
            correct_count=correct,
        )
