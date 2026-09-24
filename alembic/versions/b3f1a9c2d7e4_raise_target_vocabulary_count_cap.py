"""raise target vocabulary count cap from 15 to 30

Revision ID: b3f1a9c2d7e4
Revises: ce5b51d1cf29
Create Date: 2026-09-24 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1a9c2d7e4'
down_revision: Union[str, Sequence[str], None] = 'ce5b51d1cf29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Loosening only, so older code (which never sends more than 15) still
    runs on this schema after a rollback.
    """
    op.drop_constraint(
        "story_generation_requests_vocabulary_count_check",
        "story_generation_requests",
        type_="check",
    )
    op.create_check_constraint(
        "story_generation_requests_vocabulary_count_check",
        "story_generation_requests",
        "target_vocabulary_count BETWEEN 1 AND 30",
    )


def downgrade() -> None:
    """Downgrade schema. Fails if any request asked for more than 15 words."""
    op.drop_constraint(
        "story_generation_requests_vocabulary_count_check",
        "story_generation_requests",
        type_="check",
    )
    op.create_check_constraint(
        "story_generation_requests_vocabulary_count_check",
        "story_generation_requests",
        "target_vocabulary_count BETWEEN 1 AND 15",
    )
