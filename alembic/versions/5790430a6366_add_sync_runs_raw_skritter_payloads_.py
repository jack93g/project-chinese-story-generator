"""add sync_runs, raw_skritter_payloads, stories, story_vocabulary_items models

Revision ID: 5790430a6366
Revises: 6b3efc08b610
Create Date: 2026-07-19 18:55:09.076409

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5790430a6366'
down_revision: Union[str, Sequence[str], None] = '6b3efc08b610'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sync_runs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False, server_default='skritter'),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
    sa.CheckConstraint("status = ANY (ARRAY['running'::text, 'succeeded'::text, 'failed'::text])", name='sync_runs_status_check'),
    sa.CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='sync_runs_check'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('raw_skritter_payloads',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('sync_run_id', sa.BigInteger(), nullable=False),
    sa.Column('request_path', sa.Text(), nullable=False),
    sa.Column('request_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
    sa.Column('response_status', sa.Integer(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('raw_skritter_payloads_sync_run_id_idx', 'raw_skritter_payloads', ['sync_run_id'], unique=False)
    op.create_table('stories',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('story_vocabulary_items',
    sa.Column('story_id', sa.BigInteger(), nullable=False),
    sa.Column('vocabulary_item_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['vocabulary_item_id'], ['vocabulary_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('story_id', 'vocabulary_item_id')
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('story_vocabulary_items')
    op.drop_table('stories')
    op.drop_index('raw_skritter_payloads_sync_run_id_idx', table_name='raw_skritter_payloads')
    op.drop_table('raw_skritter_payloads')
    op.drop_table('sync_runs')