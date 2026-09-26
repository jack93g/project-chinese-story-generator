from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from story_generator.stories.persistence.models import (
    QuestionFlag,
    QuizAttempt,
    Story,
)


class StoryRepository:
    """Persistence operations for stories.

    Transaction boundaries are controlled by the calling service.
    """

    def __init__(self, session: Session):
        self.session = session

    def list_page(self, limit: int, offset: int) -> list[Story]:
        return (
            self.session.query(Story)
            .order_by(Story.id.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count(self) -> int:
        return self.session.query(Story).count()

    def get_by_id(self, story_id: int) -> Story | None:
        return self.session.get(Story, story_id)

    def delete(self, story: Story) -> None:
        self.session.delete(story)

    def add_quiz_attempt(self, attempt: QuizAttempt) -> QuizAttempt:
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def add_question_flag(self, flag: QuestionFlag) -> QuestionFlag:
        self.session.add(flag)
        self.session.flush()
        return flag

    def question_flag_summary(
        self, story_id: int | None = None
    ) -> list[tuple[int, int, int, datetime]]:
        """(story_id, question_index, flag count, last flagged at) for every
        flagged question, or only story_id's; most flagged first, then most
        recently flagged."""
        count = func.count(QuestionFlag.id)
        last_flagged = func.max(QuestionFlag.created_at)
        query = self.session.query(
            QuestionFlag.story_id, QuestionFlag.question_index, count, last_flagged
        )
        if story_id is not None:
            query = query.filter(QuestionFlag.story_id == story_id)
        return [
            tuple(row)
            for row in query.group_by(
                QuestionFlag.story_id, QuestionFlag.question_index
            )
            .order_by(count.desc(), last_flagged.desc())
            .all()
        ]

    def quiz_answers(self, story_ids: list[int]) -> list[tuple[int, list[int]]]:
        """(story_id, answers) for every quiz attempt on these stories."""
        return [
            tuple(row)
            for row in self.session.query(QuizAttempt.story_id, QuizAttempt.answers)
            .filter(QuizAttempt.story_id.in_(story_ids))
            .all()
        ]
