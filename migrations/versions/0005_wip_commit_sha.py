"""wip_commit_sha -- the WIP-recovery audit tie on role_executions

Revision ID: 0005_wip_commit_sha
Revises: 0004_artifacts
Create Date: 2026-09-15

The Phase 5 recovery slice's schema half (GIT-01, GIT-02, D-05..D-08). One
nullable column, ``role_executions.wip_commit_sha``, added as a direct
structural copy of ``0003_pause_resume_lease``'s ``runs.owner_token`` /
``runs.lock_expires_at`` pattern: a single ``op.add_column`` with no server
default and no backfill.

* **``wip_commit_sha``** (``String``, nullable) -- the SHA of the recovery
  commit a role's before-hook made while entering (finding the worktree left
  dirty by the previous role's attempt), or NULL when the attempt performed
  no recovery. NULL is the correct value for every pre-existing row -- no
  backfill is needed, exactly as NULL on the lease columns means "unclaimed"
  with no back-fill required.

``role_executions`` is already inside ``migrations/env.py``'s ``_OWNED_TABLES``
set (confirmed by reading that file before writing this migration), so no
change is needed there.

Reversible: ``downgrade()`` drops the column. The revision id is kept <= 32
chars for ``alembic_version.version_num``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_wip_commit_sha"
down_revision: str | Sequence[str] | None = "0004_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "role_executions",
        sa.Column("wip_commit_sha", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("role_executions", "wip_commit_sha")
