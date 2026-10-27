"""manual intensity overrides for M11

Revision ID: d4b8f2a6c1e9
Revises: c3a7e5b1d2f4
Create Date: 2026-10-27 12:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4b8f2a6c1e9"
down_revision: str | None = "c3a7e5b1d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("intensity_override", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("rpe", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_column("rpe")
        batch_op.drop_column("intensity_override")
