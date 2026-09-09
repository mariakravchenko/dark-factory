"""pause/resume + single-owner lease — human_interactions, runs lease columns

Revision ID: 0003_pause_resume_lease
Revises: 0002_role_exec_uniqueness
Create Date: 2026-09-09

The Phase 2 Wave-0 substrate. One vertical slice, applied together (Task 1
checkpoint = ``recommended`` = A2-TEXT + A3-NOT-NULL + A4-ONE-REVISION):

* **``human_interactions``** (STATE-04) — one row per question asked of a human.
  ``question`` is a single ``TEXT`` column holding the newline-join of
  ``WorkerResult.questions`` (A2). ``role_execution_id`` is NOT NULL — every
  question originates in a role attempt (A3). ``status`` is a ``VARCHAR(16)`` +
  named ``CHECK`` (``interaction_status``) carrying exactly ``WAITING`` /
  ``ANSWERED`` / ``CANCELLED``, never a native PG ``ENUM``, so a future value edit
  is an ``ALTER TABLE ... CHECK`` change. The column set stays byte-for-byte
  equivalent to ``dark_factory.persistence.models.HumanInteraction``.
* **``uq_one_waiting_interaction_per_run``** — a *partial* unique index on
  ``run_id`` restricted to ``status = 'WAITING'``: at most one open question per
  run is a database invariant, not application discipline. Any number of
  ``ANSWERED`` / ``CANCELLED`` rows may coexist.
* **``runs.owner_token``** (uuid, nullable) + **``runs.lock_expires_at``**
  (timestamptz, nullable) — the single-owner lease. Both nullable with no
  server default: NULL in both is exactly "unclaimed and claimable", so no
  back-fill of existing rows is needed. ``lock_expires_at`` is only ever written
  as a SQL expression over the database clock (plan 02-03 onward).

Reversible: ``downgrade()`` drops the two ``runs`` columns, the partial index and
the table, in mirror order. The revision id is kept <= 32 chars for
``alembic_version.version_num``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from dark_factory.domain.interaction import InteractionStatus

revision: str = "0003_pause_resume_lease"
down_revision: str | Sequence[str] | None = "0002_role_exec_uniqueness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must stay byte-for-byte equivalent to models._INTERACTION_STATUS.
_INTERACTION_STATUS = sa.Enum(
    InteractionStatus,
    native_enum=False,
    create_constraint=True,
    length=16,
    name="interaction_status",
    values_callable=lambda enum: [member.value for member in enum],
)


def upgrade() -> None:
    op.create_table(
        "human_interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("role_execution_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("status", _INTERACTION_STATUS, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["role_execution_id"], ["role_executions.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_human_interactions_run_id",
        "human_interactions",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "uq_one_waiting_interaction_per_run",
        "human_interactions",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'WAITING'"),
    )

    op.add_column("runs", sa.Column("owner_token", sa.Uuid(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "lock_expires_at")
    op.drop_column("runs", "owner_token")
    op.drop_index("uq_one_waiting_interaction_per_run", table_name="human_interactions")
    op.drop_index("ix_human_interactions_run_id", table_name="human_interactions")
    op.drop_table("human_interactions")
