"""HITL-06 (dispatch half), D-01/D-02/D-03 -- proved against real PostgreSQL
(Phase 11, plan 11-01):

    After a resolvable reply's ``submit_answer`` mutation has already
    committed, the webhook receiver dispatches exactly one real
    ``workflow_dispatch`` on the run's own persisted target repository,
    carrying only the run id -- and the answer stays durably recorded even
    when that dispatch call itself raises.

Sibling of ``tests/db/test_webhook_resolves_answer.py``: reuses its
``github:``-sourced setup (``config_root_factory`` + the
``repository.github_owner``/``github_repo`` overwrite, the intake-side
``FakeGitHubClient`` monkeypatched into ``dark_factory.input.loaders``, and a
second, independently scripted ``FakeGitHubClient`` injected through the
``github_client_factory`` seam for the clarification-comment post) and
``tests/db/test_resume_first_advance.py``'s real-row-count discipline. The
one divergence: ``webhook_client`` here also injects a THIRD
``FakeGitHubClient`` -- through ``build_app``'s new ``dispatch_client_factory``
keyword (Phase 11, D-01) -- and this module's own ``fake_settings`` override
carries a fake ``dispatch_github_token`` (Phase 11, D-03), since the shared
``tests/conftest.py::fake_settings`` fixture does not set one and this plan
must not edit that shared file.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from dark_factory.config.loader import load_effective_config
from dark_factory.config.settings import Settings
from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.github.client import GitHubApiError, GitHubIssue
from dark_factory.input import loaders
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.webhook.app import (
    _DISPATCH_SKIP_REASON_CREDENTIAL_NOT_CONFIGURED,
    _DISPATCH_SKIP_REASON_REPOSITORY_NOT_CONFIGURED,
    build_app,
)
from tests.support.fake_github import FakeGitHubClient
from tests.support.webhook_events import build_issue_comment_payload, sign_payload

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 11
_ISSUE_TITLE = "Fix the flaky retry logic"
_BASE_BRANCH = "main"
_QUESTIONS = ["primary or replica?"]
_TOKEN_LOGIN = "dark-factory-bot"
_WEBHOOK_PATH = "/webhooks/github"

_REPOSITORY_BLOCK = "repository:\n  base_branch: main\n"

_NEEDS_INPUT = WorkerResult(
    status=WorkerResultStatus.NEEDS_INPUT,
    summary="need a decision",
    questions=list(_QUESTIONS),
)

# Fresh, module-local fake credential values -- obviously-fake, >=8-char
# placeholders (matches `known_secret_values()`'s own minimum-length floor).
# This module overrides `tests/conftest.py::fake_settings` locally (rather
# than editing that shared fixture) solely to add `dispatch_github_token`
# (Phase 11, D-03), which the shared fixture does not set.
_FAKE_DB_URL = (
    "postgresql://df_fake_user:df_fake_pw_0123456789@fake-db.invalid:5432/df_fake_db"
)
_FAKE_DB_URL_DIRECT = "postgresql://df_fake_user:df_fake_pw_0123456789@fake-direct.invalid:5432/df_fake_db"
_FAKE_GITHUB_TOKEN = "ghp_FAKEfakeFAKEfake0000000000000000000000"
_FAKE_WEBHOOK_SECRET = "whsec_FAKEfakeFAKEfake0000000000000000"
_FAKE_DISPATCH_TOKEN = "dispatch_FAKEfakeFAKEfake00000000000000"


@pytest.fixture
def fake_settings() -> Settings:
    """Override the shared fixture to also carry a fake
    ``dispatch_github_token`` (Phase 11, D-03)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
        github_webhook_secret=_FAKE_WEBHOOK_SECRET,
        dispatch_github_token=_FAKE_DISPATCH_TOKEN,
    )


class _StubClientFactory:
    """Stands in for ``GitHubClient`` at the intake loader's own call site,
    mirroring ``tests/db/test_webhook_resolves_answer.py``."""

    def __init__(self, client: FakeGitHubClient) -> None:
        self._client = client

    def from_settings(self, settings: object) -> FakeGitHubClient:
        return self._client


def _patch_intake_client(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeGitHubClient
) -> None:
    monkeypatch.setattr(loaders, "get_settings", lambda: object())
    monkeypatch.setattr(loaders, "GitHubClient", _StubClientFactory(fake_client))


def _write_github_ba_tree(config_root_factory: Callable[..., Path]) -> Path:
    root = config_root_factory(roles=("BA",))
    config_path = root / ".dark-factory.yaml"
    original = config_path.read_text(encoding="utf-8")
    assert _REPOSITORY_BLOCK in original, (
        "config_root_factory no longer writes 'repository:\\n  base_branch: main\\n'"
        " verbatim -- update this test's overwrite string to match"
    )
    patched = original.replace(
        _REPOSITORY_BLOCK,
        f"repository:\n  base_branch: {_BASE_BRANCH}\n"
        f"  github_owner: {_OWNER}\n  github_repo: {_REPO}\n",
    )
    config_path.write_text(patched, encoding="utf-8")
    return root


def _scripted_issue() -> GitHubIssue:
    return GitHubIssue(
        number=_ISSUE_NUMBER,
        title=_ISSUE_TITLE,
        body="Retries sometimes double-fire under load.",
        labels=[],
        comments=[],
    )


@pytest.fixture
def real_session_factory(engine: Engine) -> SessionFactory:
    def factory() -> Session:
        return Session(bind=engine, expire_on_commit=False)

    return factory


@pytest.fixture
def cleanup_runs(engine: Engine) -> Iterator[list[Any]]:
    ids: list[Any] = []
    yield ids
    if ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _the_interaction(engine: Engine, run_id: UUID) -> HumanInteraction | None:
    with Session(engine) as session:
        return session.scalar(
            sa.select(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )


def _role_execution_row(engine: Engine, run_id: UUID) -> RoleExecution:
    with Session(engine) as session:
        row = session.scalar(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        )
        assert row is not None
        return row


def _role_executions_count(engine: Engine, run_id: UUID) -> int:
    with Session(engine) as session:
        return (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(RoleExecution)
                .where(RoleExecution.run_id == run_id)
            )
            or 0
        )


def _runs_count(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(sa.select(sa.func.count()).select_from(Run)) or 0


def _run_status(engine: Engine, run_id: UUID) -> RunStatus:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        return run.status


@dataclass
class WaitingRun:
    run_id: UUID
    root: Path
    clarification_comment_id: int


@pytest.fixture
def waiting_run(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
) -> WaitingRun:
    """A fresh ``github:``-sourced run, driven to ``WAITING_HUMAN`` with a
    real, committed ``clarification_comment_id`` -- the state every scenario
    in this module starts from."""
    root = _write_github_ba_tree(config_root_factory)
    fake_intake_client = FakeGitHubClient(issue=_scripted_issue())
    _patch_intake_client(monkeypatch, fake_intake_client)
    snapshot = load_effective_config(root)
    run_id = start_run(
        f"github:{_ISSUE_NUMBER}",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    fake_publish = FakeGitHubClient(issue=_scripted_issue())
    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert final is RunStatus.WAITING_HUMAN

    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert interaction.clarification_comment_id is not None
    return WaitingRun(
        run_id=run_id,
        root=root,
        clarification_comment_id=interaction.clarification_comment_id,
    )


def _build_webhook_client(
    real_session_factory: SessionFactory,
    fake_settings: Settings,
    dispatch_client: FakeGitHubClient,
) -> TestClient:
    """Build a ``TestClient`` injecting ``dispatch_client`` through
    ``build_app``'s ``dispatch_client_factory`` keyword (Phase 11, D-01) --
    independent of the intake-side and clarification-comment fakes
    ``waiting_run`` uses. A plain function, not a fixture, so each test can
    construct its own differently-scripted ``FakeGitHubClient`` (the
    happy-path fake vs. the raising fake) without mutating a shared
    instance's private state."""
    app = build_app(
        session_factory=real_session_factory,
        settings_factory=lambda: fake_settings,
        authenticated_login=lambda: _TOKEN_LOGIN,
        dispatch_client_factory=lambda: dispatch_client,
    )
    return TestClient(app)


@pytest.fixture
def webhook_secret(fake_settings: Settings) -> str:
    assert fake_settings.github_webhook_secret is not None
    return fake_settings.github_webhook_secret.get_secret_value()


def _post(
    client: TestClient,
    body: bytes,
    *,
    signature: str | None,
    event: str = "issue_comment",
    delivery_id: str = "delivery-0",
) -> Any:
    headers = {"X-GitHub-Event": event, "X-GitHub-Delivery": delivery_id}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post(_WEBHOOK_PATH, content=body, headers=headers)


# --------------------------------------------------------------------------- #
# 1. The happy path: exactly one dispatch_workflow call, exact arguments
# --------------------------------------------------------------------------- #


def test_a_resolvable_reply_dispatches_the_resume_workflow(
    waiting_run: WaitingRun,
    real_session_factory: SessionFactory,
    fake_settings: Settings,
    webhook_secret: str,
    engine: Engine,
) -> None:
    fake_dispatch_client = FakeGitHubClient()
    webhook_client = _build_webhook_client(
        real_session_factory, fake_settings, fake_dispatch_client
    )
    before_role = _role_execution_row(engine, waiting_run.run_id)

    body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 1000,
        comment_body="use the primary cluster",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    response = _post(webhook_client, body, signature=sign_payload(webhook_secret, body))
    assert response.status_code == 200

    dispatch_calls = [
        call for call in fake_dispatch_client.calls if call[0] == "dispatch_workflow"
    ]
    assert len(dispatch_calls) == 1
    _, kwargs = dispatch_calls[0]
    assert kwargs == {
        "owner": "acme",
        "repo": "widgets",
        "workflow_id": "resume.yml",
        "ref": "main",
        "run_id": str(waiting_run.run_id),
    }

    # Phase 10 behaviour is unchanged (GIT-06).
    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.ANSWERED
    after_role = _role_execution_row(engine, waiting_run.run_id)
    assert after_role.id == before_role.id
    assert _run_status(engine, waiting_run.run_id) is RunStatus.BA


# --------------------------------------------------------------------------- #
# 2. The answer is recorded even when the dispatch call raises
# --------------------------------------------------------------------------- #


def test_the_answer_is_recorded_even_when_the_dispatch_call_raises(
    waiting_run: WaitingRun,
    real_session_factory: SessionFactory,
    fake_settings: Settings,
    webhook_secret: str,
    engine: Engine,
) -> None:
    fake_dispatch_client = FakeGitHubClient(
        raises={
            "dispatch_workflow": GitHubApiError("boom", status_code=503, endpoint="x")
        }
    )
    webhook_client = _build_webhook_client(
        real_session_factory, fake_settings, fake_dispatch_client
    )

    body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 2000,
        comment_body="use staging",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    signature = sign_payload(webhook_secret, body)

    # Plan 11-02, Task 1: `_resolve_and_act` now catches the dispatch call's
    # own `GitHubError` internally (fail soft, never silent) -- this
    # delivery answers 200 rather than propagating the exception. Before
    # this plan the raise reached the caller (11-01 wired only the success
    # path); this test's own name and durable-state assertions were always
    # about the answer surviving the raise, which remains true here.
    response = _post(webhook_client, body, signature=signature)
    assert response.status_code == 200

    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.ANSWERED
    assert interaction.answer == "use staging"
    assert _run_status(engine, waiting_run.run_id) is RunStatus.BA


# --------------------------------------------------------------------------- #
# 3. A GitHub outage never costs the human their answer -- with the log
#    record and full state-invariant proof HITL-06's prohibition requires
# --------------------------------------------------------------------------- #


def test_a_dispatch_api_failure_still_answers_200_and_keeps_the_committed_answer(
    waiting_run: WaitingRun,
    real_session_factory: SessionFactory,
    fake_settings: Settings,
    webhook_secret: str,
    engine: Engine,
) -> None:
    fake_dispatch_client = FakeGitHubClient(
        raises={
            "dispatch_workflow": GitHubApiError(
                "upstream unavailable",
                status_code=503,
                endpoint="actions.create_workflow_dispatch acme/widgets/resume.yml",
            )
        }
    )
    webhook_client = _build_webhook_client(
        real_session_factory, fake_settings, fake_dispatch_client
    )
    before_role = _role_execution_row(engine, waiting_run.run_id)
    runs_before = _runs_count(engine)

    body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 3000,
        comment_body="use the read replica",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    signature = sign_payload(webhook_secret, body)

    # structlog's own capture (not the real-sink helper
    # tests/unit/test_log_redaction.py's own docstring requires for
    # redaction-processor proofs): the failure detail here is already
    # `GitHubApiError`'s own redacted message, so no processor needs to run
    # for this assertion -- only "was this event actually emitted, exactly
    # once, with these fields" matters, which is exactly what
    # `capture_logs()` proves without needing a real sink.
    with capture_logs() as captured:
        response = _post(webhook_client, body, signature=signature)

    assert response.status_code == 200

    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.ANSWERED
    assert interaction.answer == "use the read replica"
    assert _run_status(engine, waiting_run.run_id) is not RunStatus.WAITING_HUMAN
    assert _role_executions_count(engine, waiting_run.run_id) == 1
    after_role = _role_execution_row(engine, waiting_run.run_id)
    assert after_role.id == before_role.id
    assert _runs_count(engine) == runs_before

    failed_entries = [
        entry for entry in captured if entry.get("event") == "webhook.dispatch.failed"
    ]
    assert len(failed_entries) == 1
    assert failed_entries[0]["run_id"] == str(waiting_run.run_id)
    assert "upstream unavailable" in str(failed_entries[0]["detail"])


# --------------------------------------------------------------------------- #
# 4. An unconfigured repository records the answer and skips the dispatch
# --------------------------------------------------------------------------- #


def test_a_run_without_repository_config_records_the_answer_and_skips_the_dispatch(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
    fake_settings: Settings,
    webhook_secret: str,
) -> None:
    """The plan's literal recipe (build via ``config_root_factory`` with no
    ``_write_github_ba_tree`` overwrite, so `.dark-factory.yaml` never gets
    an owner/repo) cannot reach ``WAITING_HUMAN``: ``_load_github``
    (``src/dark_factory/input/loaders.py``, D-04) validates
    ``github_owner``/``github_repo`` on ``snapshot["repository"]`` -- the
    SAME mapping the run's persisted ``workflow`` column stores -- and
    raises ``UnresolvableSourceError`` before ``start_run`` ever creates a
    row. A repository config that is missing at intake time is therefore
    missing before there is a run to test against, not after.

    What HITL-06's degraded-config truth actually asserts is a property of
    the *persisted* ``workflow["repository"]`` snapshot the dispatch guard
    reads, independent of how a run came to have it -- so this test builds
    a normal ``github:``-sourced run through the intake path (owner/repo
    present, exactly like ``waiting_run``), drives it to ``WAITING_HUMAN``,
    and then directly strips ``github_owner``/``github_repo`` from the
    already-persisted ``runs.workflow`` JSONB column -- the one column the
    dispatch guard reads (``load_run_state`` inside ``_resolve_and_act``),
    never re-read from the config tree on disk. This proves the guard
    itself, rather than a scenario the intake layer already refuses to
    create.
    """
    root = _write_github_ba_tree(config_root_factory)
    fake_intake_client = FakeGitHubClient(issue=_scripted_issue())
    _patch_intake_client(monkeypatch, fake_intake_client)
    snapshot = load_effective_config(root)
    run_id = start_run(
        f"github:{_ISSUE_NUMBER}",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    fake_publish = FakeGitHubClient(issue=_scripted_issue())
    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert final is RunStatus.WAITING_HUMAN

    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert interaction.clarification_comment_id is not None

    # Strip the persisted snapshot's repository config down to the
    # unconfigured shape `tests/conftest.py::_write_config_tree` writes by
    # default (`{base_branch: main}`, no owner/repo) -- the dispatch guard's
    # own read target, not the on-disk YAML the intake layer already
    # validated and moved past.
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        workflow = dict(run.workflow)
        workflow["repository"] = {"base_branch": _BASE_BRANCH}
        run.workflow = workflow
        session.commit()

    fake_dispatch_client = FakeGitHubClient()
    webhook_client = _build_webhook_client(
        real_session_factory, fake_settings, fake_dispatch_client
    )
    body = build_issue_comment_payload(
        comment_id=interaction.clarification_comment_id + 7000,
        comment_body="use the primary cluster",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )

    with capture_logs() as captured:
        response = _post(
            webhook_client, body, signature=sign_payload(webhook_secret, body)
        )

    assert response.status_code == 200
    after = _the_interaction(engine, run_id)
    assert after is not None
    assert after.status is InteractionStatus.ANSWERED
    dispatch_calls = [
        call for call in fake_dispatch_client.calls if call[0] == "dispatch_workflow"
    ]
    assert dispatch_calls == []

    skipped_entries = [
        entry for entry in captured if entry.get("event") == "webhook.dispatch.skipped"
    ]
    assert len(skipped_entries) == 1
    assert skipped_entries[0]["reason"] == _DISPATCH_SKIP_REASON_REPOSITORY_NOT_CONFIGURED
    assert skipped_entries[0]["run_id"] == str(run_id)


# --------------------------------------------------------------------------- #
# 5. An unconfigured dispatch credential records the answer and skips the
#    dispatch -- exercising the real _dispatch_provider production path
# --------------------------------------------------------------------------- #


def test_a_receiver_without_a_dispatch_token_records_the_answer_and_skips_the_dispatch(
    waiting_run: WaitingRun,
    real_session_factory: SessionFactory,
    engine: Engine,
) -> None:
    settings_without_dispatch_token = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_FAKE_DB_URL,
        database_url_direct=_FAKE_DB_URL_DIRECT,
        github_token=_FAKE_GITHUB_TOKEN,
        github_webhook_secret=_FAKE_WEBHOOK_SECRET,
        dispatch_github_token=None,
    )
    # dispatch_client_factory=None (the default) exercises the real
    # GitHubClient.for_dispatch(settings_factory()) production path inside
    # _dispatch_provider -- the proof is that construction itself raises
    # MissingGitHubCredentialError and the guard catches it, not that an
    # injected fake was told to raise.
    app = build_app(
        session_factory=real_session_factory,
        settings_factory=lambda: settings_without_dispatch_token,
        authenticated_login=lambda: _TOKEN_LOGIN,
        dispatch_client_factory=None,
    )
    webhook_client = TestClient(app)

    body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 8000,
        comment_body="use the primary cluster",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    secret = settings_without_dispatch_token.github_webhook_secret
    assert secret is not None
    signature = sign_payload(secret.get_secret_value(), body)

    with capture_logs() as captured:
        response = _post(webhook_client, body, signature=signature)

    assert response.status_code == 200
    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.ANSWERED

    skipped_entries = [
        entry for entry in captured if entry.get("event") == "webhook.dispatch.skipped"
    ]
    assert len(skipped_entries) == 1
    assert skipped_entries[0]["reason"] == _DISPATCH_SKIP_REASON_CREDENTIAL_NOT_CONFIGURED
    assert skipped_entries[0]["run_id"] == str(waiting_run.run_id)

    # The pair is distinguishable in a log search -- Task 2's own
    # requirement, and the reason this test and the previous one each
    # assert their own named constant rather than a shared literal.
    assert (
        _DISPATCH_SKIP_REASON_CREDENTIAL_NOT_CONFIGURED
        != _DISPATCH_SKIP_REASON_REPOSITORY_NOT_CONFIGURED
    )


# --------------------------------------------------------------------------- #
# 6. D-02 (never over-dispatch): an ignored or unsigned delivery never
#    dispatches -- pins the dispatch block's placement after submit_answer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("build_body", "signed", "expected_status"),
    [
        pytest.param(
            lambda comment_id: build_issue_comment_payload(
                comment_id=comment_id,
                comment_body="a fabricated answer",
                comment_user_login=_TOKEN_LOGIN,
                issue_number=_ISSUE_NUMBER,
                owner=_OWNER,
                repo=_REPO,
            ),
            True,
            200,
            id="dark-factorys-own-comment",
        ),
        pytest.param(
            lambda comment_id: build_issue_comment_payload(
                action="edited",
                comment_id=comment_id,
                comment_body="an edit",
                comment_user_login="a-human",
                issue_number=_ISSUE_NUMBER,
                owner=_OWNER,
                repo=_REPO,
            ),
            True,
            200,
            id="ignored-action-shape",
        ),
        pytest.param(
            lambda comment_id: build_issue_comment_payload(
                comment_id=comment_id,
                comment_body="use staging",
                comment_user_login="a-human",
                issue_number=_ISSUE_NUMBER,
                owner=_OWNER,
                repo=_REPO,
            ),
            False,
            401,
            id="mis-signed",
        ),
    ],
)
def test_an_ignored_or_unsigned_delivery_never_dispatches(
    build_body: Callable[[int], bytes],
    signed: bool,
    expected_status: int,
    waiting_run: WaitingRun,
    real_session_factory: SessionFactory,
    fake_settings: Settings,
    webhook_secret: str,
) -> None:
    fake_dispatch_client = FakeGitHubClient()
    webhook_client = _build_webhook_client(
        real_session_factory, fake_settings, fake_dispatch_client
    )
    body = build_body(waiting_run.clarification_comment_id + 9000)
    signature = (
        sign_payload(webhook_secret, body)
        if signed
        else sign_payload("wrong_secret_0000000000000000000", body)
    )

    response = _post(webhook_client, body, signature=signature)

    assert response.status_code == expected_status
    dispatch_calls = [
        call for call in fake_dispatch_client.calls if call[0] == "dispatch_workflow"
    ]
    assert dispatch_calls == []
