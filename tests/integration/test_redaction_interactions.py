"""SEC-01 / SEC-02 for the two text fields Phase 2 newly persists:
``human_interactions.question`` and ``human_interactions.answer``.

A sibling of ``tests/integration/test_secret_redaction_e2e.py`` -- the same
seed-then-sweep shape, the same ``real_log_sink`` (the production processor
chain, never ``structlog.testing``), the same presence-then-absence discipline
so a test that scrubbed nothing because nothing was written cannot pass.

The two seeded surfaces are new in Phase 2:

1. a worker's ``NEEDS_INPUT`` question text carrying a connection-string-shaped
   value and a token-shaped value;
2. the operator's answer string -- the value ``dark-factory resume --answer``
   forwards verbatim to :func:`submit_answer` -- carrying the configured
   infrastructure credential's literal value.

The redaction is *inherited, not added*: ``question`` and ``answer`` reach
``redact()`` through ``_write_human_interaction`` in the one mutation path
(``persistence/mutations.py``) -- the single call site that
``tests/unit/test_single_mutation_path.py`` (the AST guard over the source tree)
pins as the only writer of ``human_interactions``. No new scrubbing call was
added on the pause path in the runner; the last test in this module asserts
exactly that.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

import dark_factory.orchestrator.runner as runner_mod
import dark_factory.persistence.mutations as mutations_mod
from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.orchestrator.answers import submit_answer
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import HumanInteraction, RoleExecution, RunEvent
from tests.support.config import DEFAULT_TEST_SNAPSHOT
from tests.support.log_sink import real_log_sink

pytestmark = pytest.mark.integration

# --------------------------------------------------------------------------- #
# Distinctive fake "live" configured secrets. Long enough to clear the
# eight-character floor in known_secret_values(), distinctive enough to grep
# for. No real credential enters this test process.
# --------------------------------------------------------------------------- #

_LIVE_DB_PASSWORD = "int06SUPERSECRETpw012345"
_FAKE_DB_URL = (
    f"postgresql+psycopg://int06user:{_LIVE_DB_PASSWORD}"
    "@int06-fake-db.invalid:5432/int06factory"
)
_FAKE_DB_URL_DIRECT = (
    f"postgresql+psycopg://int06user:{_LIVE_DB_PASSWORD}"
    "@int06-fake-direct.invalid:5432/int06factory"
)
_FAKE_GITHUB_TOKEN = "ghp_LIVEint06github00000000000000000000000000"

# --------------------------------------------------------------------------- #
# Credential shapes seeded into the worker's QUESTION text: a connection-string
# with an embedded password, and a ghp_-prefixed token. Neither is a configured
# live value -- they are caught by the D-15 pattern table, not by known-value
# substitution, which is the point for question text written by a worker.
# --------------------------------------------------------------------------- #

_Q_URI = "postgresql+psycopg://quser:qPASSWORDsecret99@q-host.invalid:5432/qdb"
_Q_TOKEN = "ghp_" + "QUESTIONtoken".ljust(40, "0")
_QUESTION_BODY = (
    f"Should I connect to {_Q_URI} using {_Q_TOKEN}, or wait for a decision?"
)

# The operator's answer embeds the configured infrastructure credential's literal
# value (``settings.database_url`` -- the whole connection string, which is the
# configured secret), plus a token shape and a sensitive ``key=value`` pair so
# the answer exercises pattern redaction as well as known-value substitution.
_A_TOKEN = "ghp_" + "ANSWERtoken".ljust(40, "0")
_A_KV_PW = "answerKVpw7788"
_ANSWER_BODY = (
    f"Use the primary cluster. The connection string is {_FAKE_DB_URL} and the "
    f"deploy token is {_A_TOKEN} and password={_A_KV_PW} so please delete this line."
)

_SESSION_ID = "fake-int06-redaction-001"

_CREDENTIALLED_URI = re.compile(
    r"(?i)\bpostgres(?:ql)?(?:\+\w+)?://[^\s:/@]+:[^\s:/@]+@\S+"
)

_FORBIDDEN = (
    _LIVE_DB_PASSWORD,
    _FAKE_DB_URL,
    _FAKE_DB_URL_DIRECT,
    _FAKE_GITHUB_TOKEN,
    _Q_URI,
    _Q_TOKEN,
    _A_TOKEN,
    _A_KV_PW,
)


class _Swept(NamedTuple):
    final_status: RunStatus
    question: str
    answer: str
    interaction_sweep: str
    event_payloads: str
    role_exec_blob: str
    log_text: str


@pytest.fixture
def interaction_secrets(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point every ``get_settings`` consumer on the run + log path at a Settings
    built from the distinctive fake live values above."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
    )
    from dark_factory import logging as df_logging

    monkeypatch.setattr(mutations_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(df_logging, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def swept(
    advance_session_factory: Callable[[], Session],
    fake_worker_registry: Callable[..., object],
    interaction_secrets: Settings,
    git_repo_root: Path,
) -> _Swept:
    pause_registry = fake_worker_registry(
        [
            WorkerResult(
                status=WorkerResultStatus.NEEDS_INPUT,
                summary="need a human decision",
                questions=[_QUESTION_BODY],
                worker_session_id=_SESSION_ID,
            )
        ]
    )
    resume_registry = fake_worker_registry(
        [
            WorkerResult(
                status=WorkerResultStatus.COMPLETED,
                summary="resumed and finished",
                worker_session_id=_SESSION_ID,
            )
        ]
    )

    with real_log_sink() as buffer:
        run_id = start_run(
            "text:pause for a human decision",
            session_factory=advance_session_factory,
            snapshot=DEFAULT_TEST_SNAPSHOT,
        )
        paused = drive(
            run_id,
            session_factory=advance_session_factory,
            registry=pause_registry,  # type: ignore[arg-type]
            repo_root=git_repo_root,
        )
        assert paused is RunStatus.WAITING_HUMAN
        submit_answer(run_id, _ANSWER_BODY, session_factory=advance_session_factory)
        final = drive(
            run_id,
            session_factory=advance_session_factory,
            registry=resume_registry,  # type: ignore[arg-type]
            repo_root=git_repo_root,
        )
        # Actively exercise the log-redaction path with a line carrying every
        # seeded and configured secret at once.
        structlog.get_logger("int06").info(
            "int06-audit",
            question=_QUESTION_BODY,
            answer=_ANSWER_BODY,
            db=_FAKE_DB_URL,
            gh=_FAKE_GITHUB_TOKEN,
        )
        log_text = buffer.getvalue()

    session = advance_session_factory()
    try:
        interactions = list(
            session.scalars(
                select(HumanInteraction).where(HumanInteraction.run_id == run_id)
            )
        )
        assert len(interactions) == 1
        interaction = interactions[0]
        interaction_sweep = "\n".join(
            [
                interaction.question,
                interaction.answer or "",
                interaction.status.value,
                str(interaction.role_execution_id),
            ]
        )

        events = list(
            session.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            )
        )
        event_payloads = "\n".join(json.dumps(e.payload) for e in events)

        execs = list(
            session.scalars(select(RoleExecution).where(RoleExecution.run_id == run_id))
        )
        role_exec_blob = "\n".join(
            json.dumps(x.result) + "\n" + json.dumps(x.error) for x in execs
        )

        return _Swept(
            final_status=final,
            question=interaction.question,
            answer=interaction.answer or "",
            interaction_sweep=interaction_sweep,
            event_payloads=event_payloads,
            role_exec_blob=role_exec_blob,
            log_text=log_text,
        )
    finally:
        session.close()


def test_the_cycle_completed_and_redaction_is_proven_presence_then_absence(
    swept: _Swept,
) -> None:
    # -- the cycle completed: assert it before any redaction assertion --
    assert swept.final_status is RunStatus.COMPLETED

    # -- PRESENCE: the fields were written, and carry the scrubbing marker --
    assert swept.question.strip() != ""
    assert swept.answer.strip() != ""
    assert "[redacted:" in swept.question
    assert "[redacted:" in swept.answer

    # -- PRESENCE on the log sink: lines for this run actually arrived --
    assert "int06-audit" in swept.log_text
    assert "[redacted:" in swept.log_text

    sinks = {
        "human_interactions (every column)": swept.interaction_sweep,
        "run_events.payload": swept.event_payloads,
        "role_executions.result/error": swept.role_exec_blob,
        "captured log buffer": swept.log_text,
    }

    # -- ABSENCE: no seeded or configured secret survives into any sink --
    for name, text in sinks.items():
        for literal in _FORBIDDEN:
            assert literal not in text, f"{literal!r} survived into {name}"
        assert _CREDENTIALLED_URI.search(text) is None, (
            f"a credentialled URI survived into {name}"
        )


def test_the_stored_question_and_answer_are_markers_not_dropped_fields(
    swept: _Swept,
) -> None:
    # the question embedded a URI and a token -> both replaced, wording kept
    assert _Q_URI not in swept.question
    assert _Q_TOKEN not in swept.question
    assert "[redacted:database_url]" in swept.question
    assert "[redacted:github_token]" in swept.question
    assert "wait for a decision" in swept.question  # non-credential wording stays

    # the answer embedded the configured connection string, a token and a
    # password= pair -> all three replaced, non-credential wording kept
    assert _FAKE_DB_URL not in swept.answer
    assert _LIVE_DB_PASSWORD not in swept.answer  # a substring of the URL, also gone
    assert _A_TOKEN not in swept.answer
    assert _A_KV_PW not in swept.answer
    assert "[redacted:database_url]" in swept.answer
    assert "[redacted:github_token]" in swept.answer
    assert "[redacted:password]" in swept.answer
    assert "please delete this line" in swept.answer


def test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site() -> None:
    """The structural half of the argument: the question and the answer are
    redacted inside ``_write_human_interaction`` -- the same call site
    ``_write_role_execution`` uses -- and the runner never scrubs on the pause
    path. ``tests/unit/test_single_mutation_path.py`` guards that this is the
    only writer of the table."""
    mutations_src = Path(mutations_mod.__file__).read_text(encoding="utf-8")
    assert "redact(spec.question, known_secrets=known)" in mutations_src
    assert "redact(spec.answer, known_secrets=known)" in mutations_src

    runner_src = Path(runner_mod.__file__).read_text(encoding="utf-8")
    assert "redact(" not in runner_src
