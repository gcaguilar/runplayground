"""goal lifecycle and archive for M14

Revision ID: e5c8a1f3b7d2
Revises: 9b4d2f7a1c3e
Create Date: 2026-10-27 18:00:00.000000

A closed goal is a final goal revision, not a deleted row. The outcome columns
live on ``goal_revisions`` so the archive can show the target, the prediction
in force and what was actually run. ``race_goals`` still holds at most one
active target per distance; closing deletes that row and frees the distance.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5c8a1f3b7d2"
down_revision: str | None = "9b4d2f7a1c3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("goal_revisions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="recorded",
            )
        )
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("outcome_time_s", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("outcome_activity_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("outcome_note", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_goal_revisions_outcome_activity_id",
            "activities",
            ["outcome_activity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_goal_revisions_outcome_activity_id"),
            ["outcome_activity_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_goal_revisions_closed_at"),
            ["closed_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("goal_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_goal_revisions_closed_at"))
        batch_op.drop_index(batch_op.f("ix_goal_revisions_outcome_activity_id"))
        batch_op.drop_constraint(
            "fk_goal_revisions_outcome_activity_id",
            type_="foreignkey",
        )
        batch_op.drop_column("outcome_note")
        batch_op.drop_column("outcome_activity_id")
        batch_op.drop_column("outcome_time_s")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("status")
