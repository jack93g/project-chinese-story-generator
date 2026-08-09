"""cap target word count on story_generation_requests

Revision ID: c41adc802ac0
Revises: 28a0f0eedb61
Create Date: 2026-08-09 13:14:31.849329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c41adc802ac0'
down_revision: Union[str, Sequence[str], None] = '28a0f0eedb61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "story_generation_requests_word_count_check",
        "story_generation_requests",
        type_="check",
    )
    op.create_check_constraint(
        "story_generation_requests_word_count_check",
        "story_generation_requests",
        "target_word_count > 0 AND target_word_count <= 1000",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "story_generation_requests_word_count_check",
        "story_generation_requests",
        type_="check",
    )
    op.create_check_constraint(
        "story_generation_requests_word_count_check",
        "story_generation_requests",
        "target_word_count > 0",
    )