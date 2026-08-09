from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from story_generator.database.base import Base
import story_generator.vocabulary.persistence.models  # noqa: F401
MAX_TARGET_WORD_COUNT = 1000

class StoryGenerationRequest(Base):
    """
    Durable job/audit record for one story-generation attempt lifecycle.

    selected_vocabulary_snapshot is an immutable copy of the exact words,
    readings, and definitions selected at request time (e.g.
    [{"id": 10, "writing": "菜单", "reading": "càidān", "definition_en":
    "menu"}]). It intentionally does NOT reference vocabulary_items by
    FK-only lookup, because the source vocabulary list may change after
    the request is created — this table preserves reproducibility.

    Raw provider request/response bodies are NOT stored here — see
    RawGenerationPayload / raw_generation_payloads, which is the sole
    location for that data. This table only holds derived/summary
    fields (status, usage totals, safe error messages) that are safe
    to query and safe to expose selectively.
    """

    __tablename__ = "story_generation_requests"

    id = Column(BigInteger, primary_key=True)
    vocabulary_list_id = Column(BigInteger, ForeignKey("vocabulary_lists.id"), nullable=False)
    target_hsk_level = Column(SmallInteger, nullable=False)
    topic = Column(Text, nullable=True)
    target_word_count = Column(SmallInteger, nullable=False)
    target_vocabulary_count = Column(SmallInteger, nullable=False)
    selected_vocabulary_snapshot = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, server_default="queued")
    prompt_version = Column(Text, nullable=False)
    provider = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    model_parameters = Column(JSONB, nullable=False, server_default="{}")
    validation_report = Column(JSONB, nullable=True)
    provider_request_id = Column(Text, nullable=True)
    usage = Column(JSONB, nullable=False, server_default="{}")
    attempt_count = Column(Integer, nullable=False, server_default="0")
    error_code = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    raw_payloads = relationship(
        "RawGenerationPayload",
        back_populates="generation_request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text])",
            name="story_generation_requests_status_check",
        ),
        CheckConstraint(
            "target_hsk_level BETWEEN 1 AND 6",
            name="story_generation_requests_hsk_level_check",
        ),
        CheckConstraint(
            f"target_word_count > 0 AND target_word_count <= {MAX_TARGET_WORD_COUNT}",
            name="story_generation_requests_word_count_check",
        ),
        CheckConstraint(
            "target_vocabulary_count BETWEEN 1 AND 15",
            name="story_generation_requests_vocabulary_count_check",
        ),
        CheckConstraint(
            "(status = 'queued' AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL) "
            "OR (status IN ('succeeded', 'failed') "
            "    AND started_at IS NOT NULL AND completed_at IS NOT NULL "
            "    AND completed_at >= started_at)",
            name="story_generation_requests_lifecycle_timestamps_check",
        ),
    )


class RawGenerationPayload(Base):
    """
    Raw provider request/response bodies for a single generation attempt.
    This is the ONLY table that stores raw provider payload data —
    story_generation_requests deliberately excludes it.

    Redaction (see story_generator.generation.redaction):
      1. Callers must pass only parsed bodies here, never HTTP headers —
         there is structurally no header field on this model.
      2. request_body/payload are additionally passed through a
         recursive denylist redactor before persistence, as defense in
         depth against secrets echoed inside a body.

    Retention: intended for short-lived debugging/audit use. Recommended
    retention window is 90 days; the purge job itself is out of scope
    for this ticket and tracked as a follow-up.
    """

    __tablename__ = "raw_generation_payloads"

    id = Column(BigInteger, primary_key=True)
    generation_request_id = Column(
        BigInteger,
        ForeignKey("story_generation_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number = Column(Integer, nullable=False)
    provider = Column(Text, nullable=False)
    request_body = Column(JSONB, nullable=True)
    response_status = Column(Integer, nullable=True)
    payload = Column(JSONB, nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    generation_request = relationship("StoryGenerationRequest", back_populates="raw_payloads")