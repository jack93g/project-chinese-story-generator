from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

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
