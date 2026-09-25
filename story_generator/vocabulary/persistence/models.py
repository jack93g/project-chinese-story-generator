from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from story_generator.database.base import Base

list_vocabulary = Table(
    "list_vocabulary",
    Base.metadata,
    Column(
        "list_id",
        BigInteger,
        ForeignKey("vocabulary_lists.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "vocabulary_id",
        BigInteger,
        ForeignKey("vocabulary_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class VocabularyList(Base):
    __tablename__ = "vocabulary_lists"

    id = Column(BigInteger, primary_key=True)
    skritter_list_id = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Set when a full sync no longer finds the list in Skritter. Archived lists
    # are hidden and can't be used for new stories, but the row stays so past
    # generation requests keep pointing at it. Cleared if the list comes back.
    archived_at = Column(DateTime(timezone=True), nullable=True)
    # Set by hand (`manage-lists hide`) for lists the learner doesn't want to
    # use. Hidden lists keep syncing but, like archived ones, are left out of
    # the API and can't be used for new stories. Sync never changes it.
    hidden = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    items = relationship(
        "VocabularyItem",
        secondary=list_vocabulary,
        back_populates="lists",
    )

    @property
    def is_available(self) -> bool:
        """Whether the list can be shown and used for new stories."""
        return self.archived_at is None and not self.hidden


class VocabularyItem(Base):
    """
    A word. skritter_vocab_id is NULL for user-entered custom words (which
    have no Skritter identity); those are deduplicated by writing via the
    partial unique index below.
    """

    __tablename__ = "vocabulary_items"

    id = Column(BigInteger, primary_key=True)
    skritter_vocab_id = Column(Text, nullable=True, unique=True)
    language = Column(Text, nullable=False)
    writing = Column(Text, nullable=False)
    reading = Column(Text, nullable=True)
    definition_en = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    lists = relationship(
        "VocabularyList",
        secondary=list_vocabulary,
        back_populates="items",
    )

    __table_args__ = (
        Index(
            "uq_vocabulary_items_custom_writing",
            "writing",
            unique=True,
            postgresql_where=skritter_vocab_id.is_(None),
        ),
    )
