"""github_publishing_columns -- the idempotent-publishing schema half

Revision ID: 0006_github_publishing_columns
Revises: 0005_wip_commit_sha
Create Date: 2026-09-26

The Phase 10 publishing slice's schema half (GIT-03, GIT-04, D-05, D-06).
Three nullable columns, added as a direct structural copy of
``0005_wip_commit_sha``'s pattern: three ``op.add_column`` calls with no
server default and no backfill.

* **``runs.published_commit_sha``** (``String``, nullable) -- the SHA of the
  commit the publish step pushed immediately before opening the pull request,
  or NULL when the run has not yet published. NULL is correct for every
  pre-existing row -- no backfill is needed, exactly as NULL means "not yet
  set" on ``role_executions.wip_commit_sha``.
* **``human_interactions.clarification_comment_id``** (``BigInteger``,
  nullable) -- the id of the GitHub comment Dark Factory itself posted
  alongside a question (plan 10-03), or NULL.
* **``human_interactions.github_comment_id``** (``BigInteger``, nullable) --
  the id of the inbound GitHub comment that answered a question (plan 10-04),
  or NULL.

Both ``clarification_comment_id`` and ``github_comment_id`` are
``sa.BigInteger``, not ``sa.Integer``: GitHub comment ids already exceed the
32-bit range, and ``sa.Integer`` would silently overflow/truncate one --
this is the GIT-04 64-bit precision edge made mechanical.

``runs`` and ``human_interactions`` are already inside ``migrations/env.py``'s
``_OWNED_TABLES`` set (confirmed by reading that file before writing this
migration), so no change is needed there. Column types must match the ORM
exactly -- ``migrations/env.py`` runs with ``compare_type=True``.

Reversible: ``downgrade()`` drops the three columns in reverse order. The
revision id is kept <= 32 chars for ``alembic_version.version_num``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_github_publishing_columns"
down_revision: str | Sequence[str] | None = "0005_wip_commit_sha"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("published_commit_sha", sa.String(), nullable=True),
    )
    op.add_column(
        "human_interactions",
        sa.Column("clarification_comment_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "human_interactions",
        sa.Column("github_comment_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("human_interactions", "github_comment_id")
    op.drop_column("human_interactions", "clarification_comment_id")
    op.drop_column("runs", "published_commit_sha")
