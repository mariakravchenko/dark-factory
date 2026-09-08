"""role_executions (run_id, role, attempt) uniqueness

Revision ID: 0002_role_exec_uniqueness
Revises: 0001_walking_skeleton
Create Date: 2026-09-08

Defence-in-depth for STATE-03 (IN-02). ``attempt`` is already computed as
``MAX(attempt) + 1`` scoped to ``(run_id, role)`` under a ``runs``-row lock in
the single mutation path (``persistence/mutations.py``), so duplicates cannot
arise there. This adds a DB-level ``UNIQUE (run_id, role, attempt)`` so a future
writer that bypasses the lock gets a constraint violation instead of silently
inserting a duplicate attempt row.

``0001`` is left untouched — it is already applied. This is a separate,
reversible revision. The revision id is kept <= 32 chars for
``alembic_version.version_num``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_role_exec_uniqueness"
down_revision: str | Sequence[str] | None = "0001_walking_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "uq_role_exec_attempt"


def upgrade() -> None:
    op.create_unique_constraint(
        _CONSTRAINT, "role_executions", ["run_id", "role", "attempt"]
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "role_executions", type_="unique")
