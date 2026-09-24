"""allow custom words: nullable skritter_vocab_id and vocabulary_list_id

Revision ID: a7c3e91d5b20
Revises: c41adc802ac0
Create Date: 2026-09-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91d5b20'
down_revision: Union[str, Sequence[str], None] = 'c41adc802ac0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'vocabulary_items', 'skritter_vocab_id', existing_type=sa.Text(), nullable=True
    )
    op.alter_column(
        'story_generation_requests',
        'vocabulary_list_id',
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_index(
        'uq_vocabulary_items_custom_writing',
        'vocabulary_items',
        ['writing'],
        unique=True,
        postgresql_where=sa.text('skritter_vocab_id IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema (fails if custom words / list-less requests exist)."""
    op.drop_index('uq_vocabulary_items_custom_writing', table_name='vocabulary_items')
    op.alter_column(
        'story_generation_requests',
        'vocabulary_list_id',
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        'vocabulary_items', 'skritter_vocab_id', existing_type=sa.Text(), nullable=False
    )
