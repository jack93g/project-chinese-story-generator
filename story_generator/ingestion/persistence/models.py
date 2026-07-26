from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import relationship

from story_generator.database.base import Base


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

    __table_args__ = (Index("raw_skritter_payloads_sync_run_id_idx", "sync_run_id"),)
