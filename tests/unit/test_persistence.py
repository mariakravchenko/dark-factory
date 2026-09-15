"""Unit coverage for ``dark_factory.persistence`` — the ORM models and the engine.

No database is touched here: every assertion is against SQLAlchemy metadata
(``__table__``) or against an ``Engine`` object built from obviously-fake,
``monkeypatch``-ed connection strings. ``create_engine`` is lazy, so no socket
is opened. The live-schema guarantees are proved separately in
``tests/db/test_schema_shape.py`` against the real PostgreSQL.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# Obviously-fake, >=8-char placeholder connection strings.
FAKE_DB_URL = (
    "postgresql+psycopg://fakeuser:fakepass@fake-host.example:5432/darkfactory"
)
FAKE_DB_URL_DIRECT = (
    "postgresql+psycopg://fakeuser:fakepass@fake-direct.example:5432/darkfactory"
)

RUN_COLUMNS = {
    "id",
    "source_kind",
    "source_ref",
    "normalized_task",
    "workflow",
    "status",
    "current_role",
    "current_step",
    "repository",
    "base_branch",
    "working_branch",
    "owner_token",
    "lock_expires_at",
    "pr_number",
    "pr_url",
    "qa_developer_iterations",
    "quality_gate_iterations",
    "created_at",
    "updated_at",
}

ROLE_EXECUTION_COLUMNS = {
    "id",
    "run_id",
    "role",
    "worker",
    "status",
    "attempt",
    "worker_session_id",
    "result",
    "error",
    "wip_commit_sha",
    "created_at",
    "updated_at",
}

RUN_EVENT_COLUMNS = {
    "id",
    "seq",
    "run_id",
    "role_execution_id",
    "type",
    "payload",
    "created_at",
}

TEN_STATUS_VALUES = {
    "CREATED",
    "BA",
    "ARCHITECTURE",
    "DEVELOPMENT",
    "QA",
    "VERIFYING",
    "PUBLISHING",
    "COMPLETED",
    "WAITING_HUMAN",
    "FAILED",
}


def test_models_and_base_are_importable() -> None:
    from dark_factory.persistence.models import Base, RoleExecution, Run, RunEvent

    assert Base is not None
    assert Run is not None
    assert RoleExecution is not None
    assert RunEvent is not None


def test_metadata_has_exactly_the_five_owned_tables() -> None:
    from dark_factory.persistence.models import Base

    # ``human_interactions`` joins the set in revision 0003 (Phase 2);
    # ``artifacts`` joins it in revision 0004 (Phase 4).
    assert sorted(Base.metadata.tables) == [
        "artifacts",
        "human_interactions",
        "role_executions",
        "run_events",
        "runs",
    ]


def test_runs_carries_the_full_state_02_column_set() -> None:
    from dark_factory.persistence.models import Run

    assert set(Run.__table__.columns.keys()) == RUN_COLUMNS


def test_runs_iteration_counters_are_not_null() -> None:
    from dark_factory.persistence.models import Run

    assert Run.__table__.c.qa_developer_iterations.nullable is False
    assert Run.__table__.c.quality_gate_iterations.nullable is False


def test_runs_iteration_counters_default_to_zero() -> None:
    from dark_factory.persistence.models import Run

    for name in ("qa_developer_iterations", "quality_gate_iterations"):
        server_default = Run.__table__.c[name].server_default
        assert server_default is not None
        assert "0" in str(server_default.arg.text)  # type: ignore[union-attr]


def test_runs_branch_columns_are_nullable() -> None:
    from dark_factory.persistence.models import Run

    assert Run.__table__.c.base_branch.nullable is True
    assert Run.__table__.c.working_branch.nullable is True


def test_runs_status_column_is_a_non_native_enum_carrying_all_ten_values() -> None:
    import sqlalchemy as sa

    from dark_factory.persistence.models import Run

    status_type = Run.__table__.c.status.type
    assert isinstance(status_type, sa.Enum)
    assert status_type.native_enum is False
    assert set(status_type.enums) == TEN_STATUS_VALUES


def test_runs_status_column_is_not_null() -> None:
    from dark_factory.persistence.models import Run

    assert Run.__table__.c.status.nullable is False


def test_runs_timestamps_come_from_the_database_clock() -> None:
    from dark_factory.persistence.models import Run

    for name in ("created_at", "updated_at"):
        column = Run.__table__.c[name]
        assert column.server_default is not None
        assert column.type.timezone is True  # type: ignore[attr-defined]


def test_role_executions_carries_the_full_state_03_column_set() -> None:
    from dark_factory.persistence.models import RoleExecution

    assert set(RoleExecution.__table__.columns.keys()) == ROLE_EXECUTION_COLUMNS


def test_role_executions_attempt_is_not_null() -> None:
    from dark_factory.persistence.models import RoleExecution

    assert RoleExecution.__table__.c.attempt.nullable is False


def test_role_executions_has_a_foreign_key_to_runs() -> None:
    from dark_factory.persistence.models import RoleExecution

    fks = list(RoleExecution.__table__.c.run_id.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "runs"


def test_run_events_carries_the_d22_column_set_plus_seq() -> None:
    from dark_factory.persistence.models import RunEvent

    assert set(RunEvent.__table__.columns.keys()) == RUN_EVENT_COLUMNS


def test_run_events_seq_is_a_database_generated_bigint_identity() -> None:
    import sqlalchemy as sa

    from dark_factory.persistence.models import RunEvent

    seq = RunEvent.__table__.c.seq
    assert isinstance(seq.type, sa.BigInteger)
    assert seq.identity is not None
    assert seq.nullable is False


def test_run_events_role_execution_id_is_a_nullable_foreign_key() -> None:
    from dark_factory.persistence.models import RunEvent

    column = RunEvent.__table__.c.role_execution_id
    assert column.nullable is True
    fks = list(column.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "role_executions"


def test_run_events_has_a_composite_run_id_seq_index() -> None:
    from dark_factory.persistence.models import RunEvent

    composite = {
        tuple(col.name for col in index.columns) for index in RunEvent.__table__.indexes
    }
    assert ("run_id", "seq") in composite


def test_no_model_defines_an_artifact_content_column() -> None:
    from dark_factory.persistence.models import RoleExecution, Run, RunEvent

    all_columns = set()
    for model in (Run, RoleExecution, RunEvent):
        all_columns.update(model.__table__.columns.keys())
    for forbidden in ("content", "body", "blob", "artifact_content", "file_bytes"):
        assert forbidden not in all_columns


def test_build_engine_uses_nullpool_and_the_psycopg_v3_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.pool import NullPool

    from dark_factory.config.settings import get_settings
    from dark_factory.persistence.engine import build_engine

    monkeypatch.setenv("DATABASE_URL", FAKE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", FAKE_DB_URL_DIRECT)
    get_settings.cache_clear()
    try:
        engine = build_engine()
        assert isinstance(engine.pool, NullPool)
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_build_engine_reads_the_pooled_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dark_factory.config.settings import get_settings
    from dark_factory.persistence.engine import build_engine

    monkeypatch.setenv("DATABASE_URL", FAKE_DB_URL)
    monkeypatch.setenv("DATABASE_URL_DIRECT", FAKE_DB_URL_DIRECT)
    get_settings.cache_clear()
    try:
        engine = build_engine()
        # The pooled URL, not the direct one, backs the application engine.
        assert engine.url.host == "fake-host.example"
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_session_local_is_a_sessionmaker() -> None:
    from sqlalchemy.orm import sessionmaker

    from dark_factory.persistence.engine import SessionLocal

    assert isinstance(SessionLocal, sessionmaker)
