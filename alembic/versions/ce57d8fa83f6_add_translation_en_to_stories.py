"""add translation_en to stories

Revision ID: ce57d8fa83f6
Revises: d823803523b7
Create Date: 2026-09-25 13:34:08.637346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ce57d8fa83f6'
down_revision: Union[str, Sequence[str], None] = 'd823803523b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Additive and nullable, so older code runs on this schema after a
    rollback; it just ignores the column and shows no translations.
    """
    op.add_column('stories', sa.Column('translation_en', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('stories', 'translation_en')
