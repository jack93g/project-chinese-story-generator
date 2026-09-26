from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

import story_generator.auth.persistence.models  # noqa: F401
import story_generator.generation.persistence.models  # noqa: F401
import story_generator.vocabulary.persistence.models  # noqa: F401
from story_generator.database.base import Base


class StoryVocabularyItem(Base):
    __tablename__ = "story_vocabulary_items"

    story_id = Column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    vocabulary_item_id = Column(
        BigInteger,
        ForeignKey("vocabulary_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requested = Column(Boolean, nullable=False, server_default="false")
    used = Column(Boolean, nullable=False, server_default="false")

    story = relationship("Story", back_populates="vocabulary_associations")
    vocabulary_item = relationship("VocabularyItem")


class Story(Base):
    __tablename__ = "stories"

    id = Column(BigInteger, primary_key=True)
    generation_request_id = Column(
        BigInteger,
        ForeignKey("story_generation_requests.id"),
        nullable=True,
        unique=True,
    )
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    # English, one string per paragraph of content (see
    # generation.validation.split_paragraphs); null for stories generated
    # before story-v6 or when the model gave no usable translation.
    translation_en = Column(JSONB, nullable=True)
    # Multiple-choice questions on the story, [{"question": str, "options":
    # [str, ...], "answer": int}] with answer indexing options, plus, from
    # story-v9, "evidence": the sentence of content that settles the answer.
    # Null for stories generated before story-v7 or when the model gave none
    # usable.
    comprehension_questions = Column(JSONB, nullable=True)
    target_hsk = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    generation_request = relationship("StoryGenerationRequest")
    vocabulary_associations = relationship(
        "StoryVocabularyItem",
        back_populates="story",
        cascade="all, delete-orphan",
    )
    vocabulary_items = association_proxy(
        "vocabulary_associations",
        "vocabulary_item",
        creator=lambda item: StoryVocabularyItem(vocabulary_item=item),
    )


class QuizAttempt(Base):
    """
    One go at a story's comprehension questions, marked by the API. Kept
    as an event: a story can be attempted any number of times, and every
    attempt is a new row.

    user_id is null when the attempt came in with the API key (no user)
    or its user has since been deleted.
    """

    __tablename__ = "quiz_attempts"

    id = Column(BigInteger, primary_key=True)
    story_id = Column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The chosen option index for each question, in question order.
    answers = Column(JSONB, nullable=False)
    correct_count = Column(Integer, nullable=False)
    question_count = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "correct_count >= 0 AND correct_count <= question_count",
            name="quiz_attempts_correct_count_check",
        ),
        Index("quiz_attempts_story_id_idx", "story_id"),
        Index("quiz_attempts_user_id_idx", "user_id"),
    )


class QuestionFlag(Base):
    """
    A reader's report that one of a story's comprehension questions seems
    wrong: its answer isn't settled by the story, say, or a wrong option is
    also true. Kept as an event, like QuizAttempt, to measure how often
    generated questions are bad.

    question_index indexes stories.comprehension_questions, which never
    change once written. user_id is null for the API key or a deleted user.
    """

    __tablename__ = "question_flags"

    id = Column(BigInteger, primary_key=True)
    story_id = Column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    question_index = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "question_index >= 0", name="question_flags_question_index_check"
        ),
        Index("question_flags_story_id_idx", "story_id"),
        Index("question_flags_user_id_idx", "user_id"),
    )
