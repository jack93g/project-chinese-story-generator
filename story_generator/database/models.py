from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from story_generator.database.base import Base

# Many-to-many join table between vocabulary_lists and vocabulary_items
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    items = relationship(
        "VocabularyItem",
        secondary=list_vocabulary,
        back_populates="lists",
    )


class VocabularyItem(Base):
    __tablename__ = "vocabulary_items"

    id = Column(BigInteger, primary_key=True)
    skritter_vocab_id = Column(Text, nullable=False, unique=True)
    language = Column(Text, nullable=False)
    writing = Column(Text, nullable=False)
    reading = Column(Text, nullable=True)
    definition_en = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    lists = relationship(
        "VocabularyList",
        secondary=list_vocabulary,
        back_populates="items",
    )




class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(BigInteger, primary_key=True)
    source = Column(Text, nullable=False, server_default="skritter")
    status = Column(Text, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    summary = Column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        CheckConstraint(
            "status = ANY (ARRAY['running'::text, 'succeeded'::text, 'failed'::text])",
            name="sync_runs_status_check",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="sync_runs_check",
        ),
    )

    payloads = relationship("RawSkritterPayload", back_populates="sync_run")


class RawSkritterPayload(Base):
    __tablename__ = "raw_skritter_payloads"

    id = Column(BigInteger, primary_key=True)
    sync_run_id = Column(
        BigInteger,
        ForeignKey("sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_path = Column(Text, nullable=False)
    request_params = Column(JSONB, nullable=False, server_default="{}")
    response_status = Column(Integer, nullable=False)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    sync_run = relationship("SyncRun", back_populates="payloads")

    __table_args__ = (
        Index("raw_skritter_payloads_sync_run_id_idx", "sync_run_id"),
    )


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