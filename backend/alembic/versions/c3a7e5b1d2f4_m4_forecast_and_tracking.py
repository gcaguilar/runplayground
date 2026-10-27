"""goal revisions and tracked actions for M4

Revision ID: c3a7e5b1d2f4
Revises: 8f2c1a9d4e70
Create Date: 2026-10-27 09:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3a7e5b1d2f4"
down_revision: str | None = "8f2c1a9d4e70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goal_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("target_time_s", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("race_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("prediction_time_s", sa.Float(), nullable=True),
        sa.Column("prediction_low_s", sa.Float(), nullable=True),
        sa.Column("prediction_high_s", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("goal_revisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_goal_revisions_distance_m"), ["distance_m"], unique=False
        )
        batch_op.create_index(
            "ix_goal_revisions_distance_created",
            ["distance_m", "created_at"],
            unique=False,
        )

    op.create_table(
        "tracked_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dimension_key", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("baseline_score", sa.Float(), nullable=True),
        sa.Column("baseline_confidence", sa.String(length=20), nullable=True),
        sa.Column("baseline_metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dimension_key"),
    )


def downgrade() -> None:
    op.drop_table("tracked_actions")
    with op.batch_alter_table("goal_revisions", schema=None) as batch_op:
        batch_op.drop_index("ix_goal_revisions_distance_created")
        batch_op.drop_index(batch_op.f("ix_goal_revisions_distance_m"))
    op.drop_table("goal_revisions")
