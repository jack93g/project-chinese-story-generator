"""add archived_at to vocabulary_lists

Revision ID: 36597445e9b0
Revises: b3f1a9c2d7e4
Create Date: 2026-09-25 10:10:15.874325

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "36597445e9b0"
down_revision: Union[str, Sequence[str], None] = "b3f1a9c2d7e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Additive and nullable, so older code runs on this schema after a
    rollback; it just ignores the column and shows archived lists again.
    """
    op.add_column(
        "vocabulary_lists",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema. Archived lists become visible again."""
    op.drop_column("vocabulary_lists", "archived_at")
