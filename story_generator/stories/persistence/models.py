from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Table, Text, func
from sqlalchemy.orm import relationship

from story_generator.database.base import Base
import story_generator.vocabulary.persistence.models  # noqa: F401


story_vocabulary_items = Table(
    "story_vocabulary_items",
    Base.metadata,
    Column(
        "story_id",
        BigInteger,
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "vocabulary_item_id",
        BigInteger,
        ForeignKey("vocabulary_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Story(Base):
    __tablename__ = "stories"

    id = Column(BigInteger, primary_key=True)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    vocabulary_items = relationship(
        "VocabularyItem",
        secondary=story_vocabulary_items,
        backref="stories",
    )
