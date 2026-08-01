"""enforce immutability of selected_vocabulary_snapshot

Revision ID: 28a0f0eedb61
Revises: d168c0429aed
Create Date: 2026-08-01 17:00:47.785246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28a0f0eedb61'
down_revision: Union[str, Sequence[str], None] = 'd168c0429aed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_selected_vocabulary_snapshot_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.selected_vocabulary_snapshot IS DISTINCT FROM OLD.selected_vocabulary_snapshot THEN
                RAISE EXCEPTION
                    'selected_vocabulary_snapshot is immutable and cannot be modified after creation (request id: %)',
                    OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER story_generation_requests_snapshot_immutable
        BEFORE UPDATE ON story_generation_requests
        FOR EACH ROW
        EXECUTE FUNCTION prevent_selected_vocabulary_snapshot_mutation();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS story_generation_requests_snapshot_immutable "
        "ON story_generation_requests;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_selected_vocabulary_snapshot_mutation();")