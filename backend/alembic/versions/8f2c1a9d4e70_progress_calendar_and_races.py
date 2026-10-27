"""progress views, calendar and planned races

Revision ID: 8f2c1a9d4e70
Revises: f543296bf69b
Create Date: 2026-10-26 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8f2c1a9d4e70"
down_revision: str | None = "f543296bf69b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_races",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("race_date", sa.Date(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("goal_time_s", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(length=1), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("planned_races", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_planned_races_activity_id"), ["activity_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_planned_races_race_date"), ["race_date"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("planned_races", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_planned_races_race_date"))
        batch_op.drop_index(batch_op.f("ix_planned_races_activity_id"))

    op.drop_table("planned_races")
