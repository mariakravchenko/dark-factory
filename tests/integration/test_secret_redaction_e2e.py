"""SC5 end-to-end: a real run seeded with credential-shaped task text and a
credential in the worker's own output reaches ``COMPLETED``, leaves at least one
``[redacted:`` token in its persisted payloads, and leaves *zero* occurrences of
any seeded or configured secret across every ``run_events.payload``, every
``role_executions.result`` / ``error``, a whole-table sweep of all three tables,
and a real structlog sink.

Plan 03 unit-tested ``redact()`` and its log wiring; Plan 05 asserted the JSONB
writes at the db tier. This is the thing SC5 actually says: seed a run with a
credential-bearing task, let the whole system run, then go and look in every
place a secret could have landed.

The proof is **presence-then-absence**. An absence-only test goes green on a
build where the payload was never written at all, or where the run failed before
reaching the worker -- the exact false green most likely to be discovered only
after a real leak (threat T-01-35). So the run is asserted ``COMPLETED`` and at
least one ``[redacted:`` token is asserted present in the persisted payloads
*before* any absence assertion runs.

Log assertions run through :func:`tests.support.log_sink.real_log_sink` -- the
real configured processor chain. ``structlog.testing.capture_logs`` bypasses the
chain, so a suite built on it passes while the real log file leaks
(01-RESEARCH.md Pitfall 5, threat T-01-17); this module never imports it.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import pytest
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import RoleExecution, Run, RunEvent
from tests.support.log_sink import real_log_sink

pytestmark = pytest.mark.integration

# --------------------------------------------------------------------------- #
# Distinctive fake "live" configured secrets -- long enough to clear the
# eight-character floor in known_secret_values(), distinctive enough to grep for
# unambiguously. No real credential enters this test process.
# --------------------------------------------------------------------------- #

_LIVE_DB_PASSWORD = "sc5SUPERSECRETpw012345"
_FAKE_DB_URL = (
    f"postgresql+psycopg://sc5user:{_LIVE_DB_PASSWORD}"
    "@sc5-fake-db.invalid:5432/sc5factory"
)
_FAKE_DB_URL_DIRECT = (
    f"postgresql+psycopg://sc5user:{_LIVE_DB_PASSWORD}"
    "@sc5-fake-direct.invalid:5432/sc5factory"
)
_FAKE_GITHUB_TOKEN = "ghp_LIVEsc5github000000000000000000000000000"

# --------------------------------------------------------------------------- #
# Seeded credential shapes in the *task text* (the task-input path).
#   1. a PostgreSQL URI with an embedded password
#   2. a ghp_-prefixed GitHub token shape
#   3. a `password=` key-value pair
#   4. the live configured DATABASE_URL value itself
# The first line holds the URI + token and is <=120 chars so the derived title
# is not truncated mid-credential.
# --------------------------------------------------------------------------- #

_SEEDED_PASSWORD = "hunter2correct"
_SEEDED_TASK_URI = (
    f"postgresql+psycopg://dfuser:{_SEEDED_PASSWORD}@db.example.com:5432/factory"
)
_SEEDED_GHP = "ghp_abcdefghij0123456789ABCDEFGHIJ0123456789"
_SEEDED_KV = f"password={_SEEDED_PASSWORD}"

_TASK_LINE1 = f"{_SEEDED_TASK_URI} {_SEEDED_GHP}"
_TASK_BODY = (
    f"{_TASK_LINE1}\n{_SEEDED_KV}\nlive={_FAKE_DB_URL}\nghtok={_FAKE_GITHUB_TOKEN}"
)
_TASK_SOURCE = "text:" + _TASK_BODY

# The worker's own summary carries a credential too, so the worker-output path is
# exercised and not only the task-input path.
_WORKER_SUMMARY = (
    "analysis complete. embedded "
    f"{_SEEDED_TASK_URI} and {_SEEDED_KV} and creds {_FAKE_DB_URL} "
    f"plus {_FAKE_GITHUB_TOKEN}"
)

# A documentation-style connection-string example -- pattern-shaped but not a
# configured live value.
_DOC_STYLE_URI = _SEEDED_TASK_URI

_CREDENTIALLED_URI = re.compile(
    r"(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s:/@]+:[^\s:/@]+@\S+"
)

# Every secret literal that must never survive into a redacting sink.
_FORBIDDEN_LITERALS = (
    _SEEDED_PASSWORD,
    _SEEDED_TASK_URI,
    _SEEDED_GHP,
    _FAKE_DB_URL,
    _FAKE_DB_URL_DIRECT,
    _FAKE_GITHUB_TOKEN,
    _LIVE_DB_PASSWORD,
)


class SeededRun(NamedTuple):
    """The artefacts of one seeded, driven-to-COMPLETED run."""

    run_id: UUID
    final_status: RunStatus
    event_payloads_text: str
    role_exec_blob_text: str
    normalized_task: dict[str, object]
    log_text: str
    whole_table_sweep_text: str


@pytest.fixture
def sc5_secrets(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point every ``get_settings`` consumer on the run + log path at a Settings
    built from the distinctive fake live values above."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
    )
    from dark_factory import logging as df_logging
    from dark_factory.persistence import mutations

    monkeypatch.setattr(mutations, "get_settings", lambda: settings)
    monkeypatch.setattr(df_logging, "get_settings", lambda: settings)
    return settings


def _sweep_all_three_tables(session: Session) -> str:
    """Serialise every text-bearing column of ``runs`` / ``role_executions`` /
    ``run_events`` -- the whole tables, not just this run's rows."""
    chunks: list[str] = []
    for run in session.scalars(select(Run)):
        chunks.append(json.dumps(run.normalized_task))
        chunks.append(run.source_ref or "")
        chunks.append(json.dumps(run.workflow))
    for row in session.scalars(select(RoleExecution)):
        chunks.append(json.dumps(row.result))
        chunks.append(json.dumps(row.error))
        chunks.append(row.worker_session_id or "")
    for event in session.scalars(select(RunEvent)):
        chunks.append(json.dumps(event.payload))
        chunks.append(event.type)
    return "\n".join(chunks)


@pytest.fixture
def seeded_run(
    advance_session_factory: Callable[[], Session],
    fake_worker_registry: Callable[[list[WorkerResult]], object],
    sc5_secrets: Settings,
) -> SeededRun:
    registry = fake_worker_registry(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary=_WORKER_SUMMARY,
                worker_session_id="fake-sc5-0001",
            )
        ]
    )

    with real_log_sink() as buffer:
        run_id = start_run(_TASK_SOURCE, session_factory=advance_session_factory)
        final = drive(
            run_id,
            session_factory=advance_session_factory,
            registry=registry,  # type: ignore[arg-type]
        )
        # Actively exercise the log-redaction path with a line that carries every
        # seeded and configured secret at once.
        structlog.get_logger("sc5").info(
            "sc5-audit",
            task=_TASK_BODY,
            summary=_WORKER_SUMMARY,
            db=_FAKE_DB_URL,
            gh=_FAKE_GITHUB_TOKEN,
        )
        log_text = buffer.getvalue()

    session = advance_session_factory()
    try:
        events = list(
            session.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            )
        )
        payloads_text = "\n".join(json.dumps(e.payload) for e in events)

        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        blob_text = "\n".join(
            json.dumps(x.result) + "\n" + json.dumps(x.error) for x in execs
        )

        run = session.get(Run, run_id)
        assert run is not None
        normalized_task = dict(run.normalized_task)

        sweep_text = _sweep_all_three_tables(session)
    finally:
        session.close()

    return SeededRun(
        run_id=run_id,
        final_status=final,
        event_payloads_text=payloads_text,
        role_exec_blob_text=blob_text,
        normalized_task=normalized_task,
        log_text=log_text,
        whole_table_sweep_text=sweep_text,
    )


# --------------------------------------------------------------------------- #
# Case 1 -- presence, then absence, across every per-run sink.
# --------------------------------------------------------------------------- #


def test_seeded_run_reaches_completed_then_redaction_is_proven_presence_then_absence(
    seeded_run: SeededRun,
) -> None:
    # -- the run completed: assert it before any redaction assertion (T-01-35) --
    assert seeded_run.final_status is RunStatus.COMPLETED

    per_run_sinks = {
        "run_events.payload": seeded_run.event_payloads_text,
        "role_executions.result/error": seeded_run.role_exec_blob_text,
        "captured log buffer": seeded_run.log_text,
    }

    # -- PRESENCE: redaction demonstrably ran (not "the secret merely never
    #    arrived") -- at least one [redacted: token in the persisted payloads --
    assert "[redacted:" in seeded_run.event_payloads_text, (
        "no [redacted: token in any run_events.payload -- an absence-only pass "
        "here would be a false green on a build where nothing was written"
    )

    # -- ABSENCE: no seeded or configured secret survives into any sink --
    for name, text in per_run_sinks.items():
        for literal in _FORBIDDEN_LITERALS:
            assert literal not in text, f"{literal!r} survived into {name}"
        assert _CREDENTIALLED_URI.search(text) is None, (
            f"a credentialled PostgreSQL URI survived into {name}"
        )


# --------------------------------------------------------------------------- #
# Case 2 -- whole-table sweep for the live configured values (Phases 6 & 12
# will run the same shape across artifacts, prompts, comments and reports).
# --------------------------------------------------------------------------- #


def test_whole_table_sweep_finds_no_live_configured_secret_values(
    seeded_run: SeededRun,
) -> None:
    sweep = seeded_run.whole_table_sweep_text
    assert sweep, "the sweep found no rows at all -- the run did not persist"
    for literal in (
        _FAKE_DB_URL,
        _FAKE_DB_URL_DIRECT,
        _FAKE_GITHUB_TOKEN,
        _LIVE_DB_PASSWORD,
    ):
        assert sweep.count(literal) == 0, (
            f"{literal!r} occurs in runs / role_executions / run_events after the run"
        )


# --------------------------------------------------------------------------- #
# Case 3 -- the runs.normalized_task scope split (Plan 03 checkpoint:
# known-values-only, D-18). The persisted task text keeps a documentation-style
# connection-string example but still has the live configured values scrubbed;
# every other sink redacts the doc URI regardless.
# --------------------------------------------------------------------------- #


def test_normalized_task_scope_split_keeps_doc_uri_but_scrubs_live_values(
    seeded_run: SeededRun,
) -> None:
    task_text = json.dumps(seeded_run.normalized_task)

    # known-values-only: a doc-style URI that is not a configured live value
    # persists in the task body as written.
    assert _DOC_STYLE_URI in seeded_run.normalized_task["body"]  # type: ignore[operator]
    assert _DOC_STYLE_URI in task_text

    # ... but the live configured values are removed even from the task text.
    assert _FAKE_DB_URL not in task_text
    assert _FAKE_GITHUB_TOKEN not in task_text
    assert _LIVE_DB_PASSWORD not in task_text

    # ... and every other sink redacts the doc URI unconditionally.
    assert _DOC_STYLE_URI not in seeded_run.event_payloads_text
    assert _DOC_STYLE_URI not in seeded_run.role_exec_blob_text
    assert _DOC_STYLE_URI not in seeded_run.log_text
    assert _CREDENTIALLED_URI.search(seeded_run.event_payloads_text) is None
    assert _CREDENTIALLED_URI.search(seeded_run.log_text) is None


# --------------------------------------------------------------------------- #
# Case 4 -- the ghp_ token seeded in the task text reaches no redacting sink,
# and this module proves its log assertions on the real sink, not on
# structlog.testing.
# --------------------------------------------------------------------------- #


def test_seeded_ghp_token_reaches_no_event_payload_or_log_line(
    seeded_run: SeededRun,
) -> None:
    assert _SEEDED_GHP not in seeded_run.event_payloads_text
    assert _SEEDED_GHP not in seeded_run.role_exec_blob_text
    assert _SEEDED_GHP not in seeded_run.log_text
    # the log line we emitted carried every secret -- redaction must have fired
    assert "[redacted:github_token]" in seeded_run.log_text
    assert "[redacted:database_url]" in seeded_run.log_text


def test_this_module_uses_the_real_sink_and_not_structlog_testing() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "from tests.support.log_sink import real_log_sink" in source

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "structlog.testing" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "structlog.testing"
        if isinstance(node, ast.Attribute) and node.attr == "testing":
            value = node.value
            assert not (isinstance(value, ast.Name) and value.id == "structlog")
