"""add hidden to vocabulary_lists

Revision ID: d823803523b7
Revises: 36597445e9b0
Create Date: 2026-09-25 14:59:42.738123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd823803523b7'
down_revision: Union[str, Sequence[str], None] = '36597445e9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Additive with a default, so older code runs on this schema after a
    rollback; it just ignores the column and shows hidden lists again.
    """
    op.add_column('vocabulary_lists', sa.Column('hidden', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    """Downgrade schema. Hidden lists become visible again."""
    op.drop_column('vocabulary_lists', 'hidden')
