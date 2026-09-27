"""GIT-05, proved against a real ``drive()`` run (Phase 10, plan 10-03):

    When a role raises ``ROLE_NEEDS_INPUT`` on a run whose source is a GitHub
    issue, Dark Factory posts the question as a fresh comment on that issue,
    records the comment's id on the ``human_interactions`` row in the same
    transaction that opens the WAITING interaction, and the run still reaches
    ``RunStatus.WAITING_HUMAN``. A re-entered attempt posts nothing more; a
    non-GitHub run is untouched; a failed post still pauses with the question
    intact; and the comment body leaks no internal state.

Follows ``tests/db/test_pause_path_atomic.py``'s assertion style (a scripted
``NEEDS_INPUT`` ``FakeWorker`` result, real commits, ``cleanup_runs``
teardown) and ``tests/db/test_publish_step.py``'s ``github:``-sourced setup
(``config_root_factory`` + the ``repository.github_owner``/``github_repo``
overwrite, the intake-side ``FakeGitHubClient`` monkeypatched into
``dark_factory.input.loaders`` so ``start_run("github:<n>", ...)`` resolves
with no network call). The *second*, independently scripted
``FakeGitHubClient`` is injected through the ``github_client_factory`` seam
``orchestrator/runner.py`` threads through ``drive`` -- the one this plan's
own ``Signal.ROLE_NEEDS_INPUT`` branch calls.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import dark_factory.orchestrator.runner as runner_module
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.interaction import InteractionStatus
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.github import GitHubApiError
from dark_factory.github.client import GitHubComment, GitHubIssue
from dark_factory.input import loaders
from dark_factory.orchestrator.answers import submit_answer
from dark_factory.orchestrator.runner import (
    build_clarification_comment,
    drive,
    start_run,
)
from dark_factory.persistence.models import (
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from tests.support.fake_github import FakeGitHubClient

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 7
_ISSUE_TITLE = "Fix the flaky retry logic"
_BASE_BRANCH = "main"
_QUESTIONS = ["primary or replica?", "which environment?"]
_ANSWER = "use the primary cluster, staging environment"

_REPOSITORY_BLOCK = "repository:\n  base_branch: main\n"

_NEEDS_INPUT = WorkerResult(
    status=WorkerResultStatus.NEEDS_INPUT,
    summary="need a decision",
    questions=list(_QUESTIONS),
)
_COMPLETED = WorkerResult(status=WorkerResultStatus.COMPLETED, summary="done")


class _StubClientFactory:
    """Stands in for ``GitHubClient`` at the loader's own call site, mirroring
    ``tests/unit/test_load_github.py`` / ``tests/db/test_publish_step.py``."""

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
    """A single-role ``[BA]`` tree (the shared factory's own default) with
    ``repository.github_owner``/``github_repo`` added -- ``start_run`` refuses
    a ``github:`` locator without them (D-04)."""
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
        labels=["bug"],
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


def _event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )


def _start_github_run(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    real_session_factory: SessionFactory,
) -> UUID:
    fake_intake_client = FakeGitHubClient(issue=_scripted_issue())
    _patch_intake_client(monkeypatch, fake_intake_client)
    snapshot = load_effective_config(root)
    return start_run(
        f"github:{_ISSUE_NUMBER}",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )


def _the_interaction(engine: Engine, run_id: UUID) -> HumanInteraction | None:
    with Session(engine) as session:
        return session.scalar(
            sa.select(HumanInteraction).where(HumanInteraction.run_id == run_id)
        )


def test_the_happy_path_posts_one_comment_and_records_its_id(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
) -> None:
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    # CR-01: the existence check (fetch_issue + authenticated_login) runs
    # before create_comment, so the ask-path fake must script an issue --
    # even a comment-free one -- exactly like the intake-side fake already
    # scripts one above.
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
    assert interaction.status is InteractionStatus.WAITING
    assert interaction.question == "\n".join(_QUESTIONS)
    assert interaction.clarification_comment_id is not None

    create_calls = [c for c in fake_publish.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1
    kwargs = create_calls[0][1]
    assert kwargs["issue_number"] == _ISSUE_NUMBER
    assert kwargs["owner"] == _OWNER
    assert kwargs["repo"] == _REPO
    assert all(question in kwargs["body"] for question in _QUESTIONS)
    assert kwargs["body"] == build_clarification_comment(_QUESTIONS)

    event_types = _event_types(engine, run_id)
    assert event_types[-2:] == ["QUESTION_CREATED", "RUN_PAUSED"]


def test_re_entry_without_answering_posts_nothing_more(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
    force_lease_expiry: Callable[[UUID], None],
) -> None:
    """D-05 made mechanical: re-driving a paused run posts no second comment
    -- the run is still WAITING_HUMAN, so ``drive`` returns immediately with
    no lease claim and no step taken at all."""
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    # CR-01: the existence check (fetch_issue + authenticated_login) runs
    # before create_comment, so the ask-path fake must script an issue --
    # even a comment-free one -- exactly like the intake-side fake already
    # scripts one above.
    fake_publish = FakeGitHubClient(issue=_scripted_issue())

    first = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert first is RunStatus.WAITING_HUMAN
    before = _the_interaction(engine, run_id)
    assert before is not None

    force_lease_expiry(run_id)
    second = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert second is RunStatus.WAITING_HUMAN

    after = _the_interaction(engine, run_id)
    assert after is not None
    assert after.id == before.id
    assert after.clarification_comment_id == before.clarification_comment_id
    create_calls = [c for c in fake_publish.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1


def test_a_non_github_run_is_untouched(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    fake_worker_registry: Callable[..., Any],
) -> None:
    root = config_root_factory(roles=("BA",))
    snapshot = load_effective_config(root)
    run_id = start_run(
        "text:a plain task with no GitHub source",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    def _factory_must_not_be_called() -> FakeGitHubClient:
        raise AssertionError(
            "github_client_factory was called for a text:-sourced run"
        )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=_factory_must_not_be_called,
    )
    assert final is RunStatus.WAITING_HUMAN

    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert interaction.clarification_comment_id is None
    assert interaction.question == "\n".join(_QUESTIONS)


def test_a_failed_post_still_pauses_and_the_question_survives(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
) -> None:
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    fake_publish = FakeGitHubClient(
        issue=_scripted_issue(),
        raises={
            "create_comment": GitHubApiError(
                "service unavailable", status_code=503, endpoint="issues.create_comment"
            )
        },
    )

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
    assert interaction.status is InteractionStatus.WAITING
    assert interaction.question == "\n".join(_QUESTIONS)
    assert interaction.clarification_comment_id is None

    # The question was not lost: a subsequent answer still resumes the run.
    resumed = submit_answer(run_id, _ANSWER, session_factory=real_session_factory)
    assert resumed is RunStatus.BA
    final2 = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_COMPLETED]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert final2 is RunStatus.COMPLETED


def test_the_comment_body_carries_no_internal_state(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
) -> None:
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    # CR-01: the existence check (fetch_issue + authenticated_login) runs
    # before create_comment, so the ask-path fake must script an issue --
    # even a comment-free one -- exactly like the intake-side fake already
    # scripts one above.
    fake_publish = FakeGitHubClient(issue=_scripted_issue())

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert final is RunStatus.WAITING_HUMAN

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        working_branch = run_row.working_branch
        role_execution = session.scalar(
            sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
        )
        assert role_execution is not None
        role_execution_id = role_execution.id

    working_branch_expected = working_branch_name(run_id)
    assert working_branch == working_branch_expected
    work_dir = ensure_worktree(
        root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
    )

    create_calls = [c for c in fake_publish.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1
    body = create_calls[0][1]["body"]

    assert str(run_id) not in body
    assert str(role_execution_id) not in body
    assert working_branch not in body
    assert str(work_dir) not in body


def test_crash_between_comment_creation_and_its_commit_yields_one_comment(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
    force_lease_expiry: Callable[[UUID], None],
) -> None:
    """CR-01 (10-REVIEW.md): a process killed after ``create_comment``
    succeeds on GitHub but before ``apply_transition`` commits
    ``clarification_comment_id`` resumes to post no second comment -- the
    existence check finds and adopts the already-posted comment. Mirrors
    ``tests/db/test_publish_idempotency.py``'s identical in-process
    crash-window proof for ``create_pull_request``: the module-level
    ``apply_transition`` symbol ``orchestrator/runner.py`` calls is
    monkeypatched to raise, but only for the call carrying a
    ``human_interaction`` write whose ``mode`` is ``"ask"`` -- never the
    earlier "enter BA" transition -- so this targets exactly the window
    between GitHub returning success for ``create_comment`` and Neon
    recording it."""
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)

    real_apply_transition = runner_module.apply_transition

    class _CrashSwitch:
        def __init__(self) -> None:
            self.enabled = True

    switch = _CrashSwitch()

    def _crash_before_comment_commit(*args: Any, **kwargs: Any) -> RunStatus:
        human_interaction = kwargs.get("human_interaction")
        if (
            switch.enabled
            and human_interaction is not None
            and human_interaction.mode == "ask"
        ):
            raise RuntimeError(
                "simulated crash: create_comment returned, before its id was committed"
            )
        result: RunStatus = real_apply_transition(*args, **kwargs)
        return result

    monkeypatch.setattr(runner_module, "apply_transition", _crash_before_comment_commit)

    first_client = FakeGitHubClient(issue=_scripted_issue())

    with pytest.raises(RuntimeError):
        drive(
            run_id,
            session_factory=real_session_factory,
            registry=fake_worker_registry([_NEEDS_INPUT]),
            repo_root=root,
            github_client_factory=lambda: first_client,
        )

    # Nothing committed: the crash happened before apply_transition ran.
    assert _the_interaction(engine, run_id) is None
    create_calls = [c for c in first_client.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1, (
        "the crashed attempt must have called create_comment exactly once "
        f"before the simulated crash; calls={first_client.calls}"
    )

    # Resume, exactly as a fresh `dark-factory resume`/`drive()` call after a
    # real process death would: GitHub already has the comment the first
    # attempt posted, so the resumed attempt's existence check must find and
    # adopt it rather than posting a second one.
    switch.enabled = False
    force_lease_expiry(run_id)
    posted_body = build_clarification_comment(_QUESTIONS)
    already_posted = GitHubComment(id=321, author="dark-factory-bot", body=posted_body)
    resume_client = FakeGitHubClient(
        issue=GitHubIssue(
            number=_ISSUE_NUMBER,
            title=_ISSUE_TITLE,
            body="Retries sometimes double-fire under load.",
            labels=["bug"],
            comments=[already_posted],
        )
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_NEEDS_INPUT]),
        repo_root=root,
        github_client_factory=lambda: resume_client,
    )
    assert final is RunStatus.WAITING_HUMAN

    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert interaction.clarification_comment_id == 321

    total_create_calls = len(
        [c for c in first_client.calls if c[0] == "create_comment"]
    ) + len([c for c in resume_client.calls if c[0] == "create_comment"])
    assert total_create_calls == 1
