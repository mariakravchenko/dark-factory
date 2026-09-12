"""artifact metadata rows -- the artifacts table

Revision ID: 0004_artifacts
Revises: 0003_pause_resume_lease
Create Date: 2026-09-12

The Phase 4 tracer's schema slice (ART-01, ART-02, ART-03, STATE-05). One
table, ``artifacts``, storing **metadata only** for every artifact file a role
attempt produces -- ``id, run_id, role_execution_id, type, path, checksum,
metadata, created_at`` -- byte-for-byte equivalent to
``dark_factory.persistence.models.ArtifactReference``. The file's body text
never crosses into Neon: the filesystem under
``.dark-factory/runs/<run-id>/artifacts/<role>/`` holds the real content.

* ``metadata`` is a NOT NULL ``JSONB`` column with a ``'{}'::jsonb`` server
  default -- named ``metadata`` in the database even though the ORM's Python
  attribute is ``artifact_metadata`` (``metadata`` is reserved on a SQLAlchemy
  declarative class).
* ``uq_artifact_role_execution_path`` is a unique constraint on
  ``(role_execution_id, path)`` -- the same defence-in-depth philosophy as
  ``uq_role_exec_attempt`` on ``role_executions``: two artifacts reported for
  the same attempt at the same path collide rather than silently merge.
* ``ix_artifacts_run_id`` serves the only query shape this table has today --
  "this run's artifacts".

Reversible: ``downgrade()`` drops the index then the table, mirror order (the
``0003`` pattern).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_artifacts"
down_revision: str | Sequence[str] | None = "0003_pause_resume_lease"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("role_execution_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["role_execution_id"], ["role_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "role_execution_id", "path", name="uq_artifact_role_execution_path"
        ),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_run_id", table_name="artifacts")
    op.drop_table("artifacts")
