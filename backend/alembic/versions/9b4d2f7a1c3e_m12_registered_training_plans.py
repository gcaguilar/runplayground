"""registered training plans and sessions for M12

Revision ID: 9b4d2f7a1c3e
Revises: c3a7e5b1d2f4
Create Date: 2026-10-27 12:00:00.000000

A parallel branch is expected to add its own migration on top of
``c3a7e5b1d2f4``. This branch only owns one head; the duplicate will be
resolved with an alembic merge when both land, never by mixing histories here.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b4d2f7a1c3e"
down_revision: str | None = "d4b8f2a6c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("goal_race_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("parent_plan_id", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["goal_race_id"], ["planned_races.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_plan_id"], ["training_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("training_plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_training_plans_start_date"), ["start_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_training_plans_end_date"), ["end_date"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_training_plans_goal_race_id"), ["goal_race_id"], unique=False
        )
        batch_op.create_index(
            "uq_training_plans_single_active",
            ["is_active"],
            unique=True,
            sqlite_where=sa.text("is_active = 1"),
        )

    op.create_table(
        "training_plan_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("intensity", sa.String(length=20), nullable=False, server_default="easy"),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["training_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("training_plan_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_training_plan_sessions_plan_id"), ["plan_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_training_plan_sessions_session_date"),
            ["session_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_training_plan_sessions_activity_id"),
            ["activity_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_training_plan_sessions_plan_date",
            ["plan_id", "session_date", "position"],
            unique=False,
        )
        batch_op.create_index(
            "uq_training_plan_sessions_activity",
            ["activity_id"],
            unique=True,
            sqlite_where=sa.text("activity_id IS NOT NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plan_sessions", schema=None) as batch_op:
        batch_op.drop_index("uq_training_plan_sessions_activity")
        batch_op.drop_index("ix_training_plan_sessions_plan_date")
        batch_op.drop_index(batch_op.f("ix_training_plan_sessions_activity_id"))
        batch_op.drop_index(batch_op.f("ix_training_plan_sessions_session_date"))
        batch_op.drop_index(batch_op.f("ix_training_plan_sessions_plan_id"))
    op.drop_table("training_plan_sessions")

    with op.batch_alter_table("training_plans", schema=None) as batch_op:
        batch_op.drop_index("uq_training_plans_single_active")
        batch_op.drop_index(batch_op.f("ix_training_plans_goal_race_id"))
        batch_op.drop_index(batch_op.f("ix_training_plans_end_date"))
        batch_op.drop_index(batch_op.f("ix_training_plans_start_date"))
    op.drop_table("training_plans")
