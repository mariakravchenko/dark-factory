"""GIT-06, proved against real PostgreSQL (Phase 10, plan 10-04):

    A signed ``issue_comment`` reply resumes the same ``RoleExecution`` --
    the run's existing attempt row moves to ``RESUMING`` and its id is
    unchanged; no new ``runs`` row and no new ``role_executions`` row is
    ever created. A redelivered comment stores exactly one answer, keyed on
    the GitHub comment id rather than the ``X-GitHub-Delivery`` transport
    header (D-05). Dark Factory never answers its own clarification comment,
    on either of two independent filters. Unsigned, mis-signed and
    ignored-action-shape deliveries change nothing. The full receiver route
    is exercised in-process through Starlette's own ``TestClient``, against
    a real committed database -- not a mock, not a faked session.

Follows ``tests/db/test_ask_posts_comment.py``'s ``github:``-sourced setup
(``config_root_factory`` + the ``repository.github_owner``/``github_repo``
overwrite, the intake-side ``FakeGitHubClient`` monkeypatched into
``dark_factory.input.loaders`` so ``start_run("github:<n>", ...)`` resolves
with no network call, and a second, independently scripted
``FakeGitHubClient`` injected through the ``github_client_factory`` seam for
the clarification-comment post) and ``tests/db/test_resume_first_advance.py``'s
real-row-count discipline. Every fixture body is signed with the exact
``githubkit.webhooks.sign`` construction GitHub documents
(``tests/support/webhook_events.py``), using the ``fake_settings`` fixture's
``github_webhook_secret`` -- never a hand-rolled HMAC comparison.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from dark_factory.config.loader import load_effective_config
from dark_factory.config.settings import Settings
from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.github.client import GitHubIssue
from dark_factory.input import loaders
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.webhook.app import build_app
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


class _StubClientFactory:
    """Stands in for ``GitHubClient`` at the intake loader's own call site,
    mirroring ``tests/unit/test_load_github.py``/``tests/db/test_ask_posts_comment.py``."""

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


def _runs_count(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(Run)) or 0


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
                select(func.count())
                .select_from(RoleExecution)
                .where(RoleExecution.run_id == run_id)
            )
            or 0
        )


def _run_status(engine: Engine, run_id: UUID) -> RunStatus:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        return run.status


def _event_types(engine: Engine, run_id: UUID) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


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

    fake_publish = FakeGitHubClient()
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


@pytest.fixture
def webhook_client(
    real_session_factory: SessionFactory, fake_settings: Settings
) -> TestClient:
    app = build_app(
        session_factory=real_session_factory,
        settings_factory=lambda: fake_settings,
        authenticated_login=lambda: _TOKEN_LOGIN,
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
# 1. The resolvable reply resumes the same attempt
# --------------------------------------------------------------------------- #


def test_a_resolvable_reply_resumes_the_same_attempt(
    waiting_run: WaitingRun,
    webhook_client: TestClient,
    webhook_secret: str,
    engine: Engine,
) -> None:
    before_role = _role_execution_row(engine, waiting_run.run_id)
    before_count = _role_executions_count(engine, waiting_run.run_id)

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

    assert _run_status(engine, waiting_run.run_id) is RunStatus.BA

    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.ANSWERED
    assert interaction.answer == "use the primary cluster"
    assert interaction.github_comment_id == waiting_run.clarification_comment_id + 1000

    after_role = _role_execution_row(engine, waiting_run.run_id)
    assert after_role.id == before_role.id
    assert after_role.status == "RESUMING"
    assert _role_executions_count(engine, waiting_run.run_id) == before_count


# --------------------------------------------------------------------------- #
# 2. No new run, ever
# --------------------------------------------------------------------------- #


def test_no_new_run_is_ever_created(
    waiting_run: WaitingRun,
    webhook_client: TestClient,
    webhook_secret: str,
    engine: Engine,
) -> None:
    before = _runs_count(engine)

    resolvable_body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 2000,
        comment_body="answer for the real run",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    resolvable_response = _post(
        webhook_client, resolvable_body, signature=sign_payload(webhook_secret, resolvable_body)
    )
    assert resolvable_response.status_code == 200
    assert _runs_count(engine) == before

    unmatched_body = build_issue_comment_payload(
        comment_id=999999999,
        comment_body="hello? anyone?",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER + 12345,
        owner=_OWNER,
        repo=_REPO,
    )
    unmatched_response = _post(
        webhook_client, unmatched_body, signature=sign_payload(webhook_secret, unmatched_body)
    )
    assert unmatched_response.status_code == 200
    assert _runs_count(engine) == before

    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.ANSWERED  # from the resolvable delivery above
    assert interaction.answer == "answer for the real run"


# --------------------------------------------------------------------------- #
# 3. Redelivery stores exactly one answer
# --------------------------------------------------------------------------- #


def test_redelivery_stores_exactly_one_answer(
    waiting_run: WaitingRun,
    webhook_client: TestClient,
    webhook_secret: str,
    engine: Engine,
) -> None:
    comment_id = waiting_run.clarification_comment_id + 3000
    body = build_issue_comment_payload(
        comment_id=comment_id,
        comment_body="use staging",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    signature = sign_payload(webhook_secret, body)

    first = _post(webhook_client, body, signature=signature, delivery_id="delivery-A")
    assert first.status_code == 200

    after_first = _the_interaction(engine, waiting_run.run_id)
    assert after_first is not None
    assert after_first.answer == "use staging"
    assert after_first.github_comment_id == comment_id
    answered_at_after_first = after_first.answered_at
    events_after_first = _event_types(engine, waiting_run.run_id)
    assert events_after_first.count("HUMAN_ANSWER_RECEIVED") == 1

    # Identical redelivery under the SAME X-GitHub-Delivery header.
    second = _post(webhook_client, body, signature=signature, delivery_id="delivery-A")
    assert second.status_code == 200

    after_second = _the_interaction(engine, waiting_run.run_id)
    assert after_second is not None
    assert after_second.answer == "use staging"
    assert after_second.github_comment_id == comment_id
    assert after_second.answered_at == answered_at_after_first
    assert _event_types(engine, waiting_run.run_id).count("HUMAN_ANSWER_RECEIVED") == 1

    # The SAME logical comment, redelivered under a DIFFERENT X-GitHub-Delivery
    # header -- the dedup key is the comment id, never the transport header (D-05).
    third = _post(webhook_client, body, signature=signature, delivery_id="delivery-B-different")
    assert third.status_code == 200

    after_third = _the_interaction(engine, waiting_run.run_id)
    assert after_third is not None
    assert after_third.answer == "use staging"
    assert after_third.github_comment_id == comment_id
    assert after_third.answered_at == answered_at_after_first
    assert _event_types(engine, waiting_run.run_id).count("HUMAN_ANSWER_RECEIVED") == 1


# --------------------------------------------------------------------------- #
# 4. Dark Factory never answers itself
# --------------------------------------------------------------------------- #


def test_dark_factory_never_answers_itself(
    waiting_run: WaitingRun,
    webhook_client: TestClient,
    webhook_secret: str,
    engine: Engine,
) -> None:
    # The comment id equals the interaction's own clarification_comment_id,
    # and the body is the question text itself.
    self_id_body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id,
        comment_body="\n".join(_QUESTIONS),
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    self_id_response = _post(
        webhook_client, self_id_body, signature=sign_payload(webhook_secret, self_id_body)
    )
    assert self_id_response.status_code == 200

    interaction_after_self_id = _the_interaction(engine, waiting_run.run_id)
    assert interaction_after_self_id is not None
    assert interaction_after_self_id.status is InteractionStatus.WAITING
    assert interaction_after_self_id.answer is None

    # A different comment id, but the commenter's login equals the token's
    # own identity.
    self_login_body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 4000,
        comment_body="a fabricated answer",
        comment_user_login=_TOKEN_LOGIN,
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    self_login_response = _post(
        webhook_client, self_login_body, signature=sign_payload(webhook_secret, self_login_body)
    )
    assert self_login_response.status_code == 200

    interaction_after_self_login = _the_interaction(engine, waiting_run.run_id)
    assert interaction_after_self_login is not None
    assert interaction_after_self_login.status is InteractionStatus.WAITING
    assert interaction_after_self_login.answer is None


# --------------------------------------------------------------------------- #
# 5. Unsigned and mis-signed deliveries change nothing
# --------------------------------------------------------------------------- #


def test_unsigned_and_mis_signed_deliveries_change_nothing(
    waiting_run: WaitingRun,
    webhook_client: TestClient,
    webhook_secret: str,
    engine: Engine,
) -> None:
    runs_before = _runs_count(engine)
    role_before = _role_execution_row(engine, waiting_run.run_id)

    body = build_issue_comment_payload(
        comment_id=waiting_run.clarification_comment_id + 5000,
        comment_body="use staging",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )

    unsigned = _post(webhook_client, body, signature=None)
    assert unsigned.status_code == 401

    different_bytes_signature = sign_payload(
        webhook_secret,
        build_issue_comment_payload(
            comment_id=1,
            comment_body="an entirely different body",
            issue_number=_ISSUE_NUMBER,
            owner=_OWNER,
            repo=_REPO,
        ),
    )
    mis_signed = _post(webhook_client, body, signature=different_bytes_signature)
    assert mis_signed.status_code == 401

    assert _run_status(engine, waiting_run.run_id) is RunStatus.WAITING_HUMAN
    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.WAITING
    assert interaction.answer is None
    assert _runs_count(engine) == runs_before
    role_after = _role_execution_row(engine, waiting_run.run_id)
    assert role_after.id == role_before.id
    assert role_after.status == role_before.status
    assert role_after.updated_at == role_before.updated_at


# --------------------------------------------------------------------------- #
# 6. Ignored action shapes change nothing
# --------------------------------------------------------------------------- #


def test_ignored_action_shapes_change_nothing(
    waiting_run: WaitingRun,
    webhook_client: TestClient,
    webhook_secret: str,
    engine: Engine,
) -> None:
    runs_before = _runs_count(engine)
    role_before = _role_execution_row(engine, waiting_run.run_id)

    for action in ("edited", "deleted"):
        body = build_issue_comment_payload(
            action=action,
            comment_id=waiting_run.clarification_comment_id + 6000,
            comment_body="an edit or a deletion",
            comment_user_login="a-human",
            issue_number=_ISSUE_NUMBER,
            owner=_OWNER,
            repo=_REPO,
        )
        response = _post(webhook_client, body, signature=sign_payload(webhook_secret, body))
        assert response.status_code == 200

    pr_body = build_issue_comment_payload(
        action="created",
        is_pull_request=True,
        comment_id=waiting_run.clarification_comment_id + 6100,
        comment_body="a pull-request-thread comment",
        comment_user_login="a-human",
        issue_number=_ISSUE_NUMBER,
        owner=_OWNER,
        repo=_REPO,
    )
    pr_response = _post(webhook_client, pr_body, signature=sign_payload(webhook_secret, pr_body))
    assert pr_response.status_code == 200

    assert _runs_count(engine) == runs_before
    role_after = _role_execution_row(engine, waiting_run.run_id)
    assert role_after.id == role_before.id
    assert role_after.status == role_before.status
    assert role_after.updated_at == role_before.updated_at
    interaction = _the_interaction(engine, waiting_run.run_id)
    assert interaction is not None
    assert interaction.status is InteractionStatus.WAITING
    assert interaction.answer is None
