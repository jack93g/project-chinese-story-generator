"""enforce status-aware lifecycle timestamp constraint

Revision ID: d168c0429aed
Revises: 73e4edaa4c08
Create Date: 2026-08-01 14:15:42.404873

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd168c0429aed'
down_revision: Union[str, Sequence[str], None] = '73e4edaa4c08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        'story_generation_requests_completed_after_started_check',
        'story_generation_requests',
        type_='check',
    )
    op.create_check_constraint(
        'story_generation_requests_lifecycle_timestamps_check',
        'story_generation_requests',
        "(status = 'queued' AND started_at IS NULL AND completed_at IS NULL) "
        "OR (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL) "
        "OR (status IN ('succeeded', 'failed') "
        "    AND started_at IS NOT NULL AND completed_at IS NOT NULL "
        "    AND completed_at >= started_at)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'story_generation_requests_lifecycle_timestamps_check',
        'story_generation_requests',
        type_='check',
    )
    op.create_check_constraint(
        'story_generation_requests_completed_after_started_check',
        'story_generation_requests',
        'completed_at IS NULL OR completed_at >= started_at',
    )