"""Unit coverage for GIT-05's clarification-comment posting (Phase 10, plan 10-03):
``build_clarification_comment``'s body template and the
``Signal.ROLE_NEEDS_INPUT`` branch inside ``orchestrator/runner.py``'s
``_run_current_role``.

This module opens no PostgreSQL connection and constructs no ``Settings``
object of its own: :class:`~dark_factory.persistence.repositories.RunState` is
a frozen pydantic model constructed directly (the same idiom
``tests/unit/test_publish_idempotency.py`` established for GIT-04),
``apply_transition`` is monkeypatched to a recording spy rather than exercised
against a real Postgres row, and ``_drive_needs_input`` supplies a
``fake_settings`` object in place of the runner module's own process-global
``get_settings`` accessor (G-11-3, plan 11-09) -- so this module needs no
database URL present in the environment. What this plan's own db-tier proof
(``tests/db/test_ask_posts_comment.py``) covers against real PostgreSQL, this
file assumes and instead proves the *decision* each branch makes, fast and
deterministically. :class:`~tests.support.fake_github.FakeGitHubClient` (built
complete by plan 10-01) stands in for GitHub itself.

A real, throwaway git repository (``tests.support.git_repo.make_git_repo``) is
still used for the worktree ``_run_current_role`` unconditionally creates
(GIT-01) -- a mock cannot reproduce ``ensure_worktree``'s real git behaviour,
and the role's declared ``inputs``/``outputs`` are both empty here, so no
database read is ever needed inside ``build_role_context`` either.

The ``monkeypatch.setattr(runner_module, "get_settings", ...)`` patch in
``_drive_needs_input`` covers *every* branch of ``_run_current_role`` that
resolves the accessor through the runner module's own global name -- the
quality-gate timeout/redaction read, the push-token read after the artifact
commit, and the clarification-failure redaction read below -- not only the one
this test exercises, because all three resolve the same patched name.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import dark_factory.orchestrator.runner as runner_module
from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.task import NormalizedTask
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.git.worktree import working_branch_name
from dark_factory.github import GitHubApiError
from dark_factory.github.client import GitHubClient, GitHubComment, GitHubIssue
from dark_factory.orchestrator.lease import LeaseHandle
from dark_factory.orchestrator.runner import (
    CLARIFICATION_COMMENT_PREFIX,
    build_clarification_comment,
)
from dark_factory.persistence.repositories import LatestExecution, RunState
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.registry import WorkerRegistry
from dark_factory.workflows.pipeline import pipeline_from_snapshot
from tests.support.fake_github import FakeGitHubClient
from tests.support.git_repo import make_git_repo

pytestmark = pytest.mark.unit

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 42
_QUESTIONS = ["why is this needed?", "which approach should I take?"]


def _scripted_issue(comments: list[GitHubComment] | None = None) -> GitHubIssue:
    """A minimal issue for the ask-path ``FakeGitHubClient`` -- CR-01's
    existence check calls ``fetch_issue`` before ever posting, so every
    scenario below that reaches the GitHub-sourced branch must script one,
    even when it carries no pre-existing comments."""
    return GitHubIssue(
        number=_ISSUE_NUMBER,
        title="issue title",
        body="issue body",
        labels=[],
        comments=comments or [],
    )


class _NoOpSession:
    """A ``session_factory()`` stand-in: the only method this branch's own
    ``session_factory()`` call sites use is ``.close()`` (``build_role_context``
    never queries anything, because this test's role declares no ``inputs``/
    ``optional_inputs``, and ``apply_transition`` itself is monkeypatched)."""

    def close(self) -> None:
        return None


def _registry_with_script(script: list[WorkerResult]) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: FakeWorker(script=list(script)))
    return registry


def _needs_input_result(questions: list[str] = _QUESTIONS) -> WorkerResult:
    return WorkerResult(status=WorkerResultStatus.NEEDS_INPUT, questions=list(questions))


def _run_state(
    run_id: UUID,
    role_execution_id: UUID,
    *,
    source_kind: str,
    metadata: dict[str, Any],
    working_branch: str,
    pending_clarification_comment_id: int | None = None,
) -> RunState:
    return RunState(
        run_id=run_id,
        status=RunStatus.BA,
        current_role="BA",
        current_step=1,
        normalized_task=NormalizedTask(
            source_kind=source_kind,
            source_ref=(
                f"{_OWNER}/{_REPO}#{_ISSUE_NUMBER}" if source_kind == "github" else None
            ),
            title="Fix the flaky retry logic",
            body="issue body",
            metadata=metadata,
        ),
        workflow={"roles": ["BA"], "repository": {"base_branch": "main"}},
        qa_developer_iterations=0,
        quality_gate_iterations=0,
        latest_execution=LatestExecution(
            id=role_execution_id,
            role="BA",
            worker="fake",
            status="RUNNING",
            attempt=1,
            worker_session_id=None,
            result=None,
            wip_commit_sha=None,
        ),
        pending_answer=None,
        base_branch="main",
        working_branch=working_branch,
        pr_number=None,
        pr_url=None,
        published_commit_sha=None,
        pending_clarification_comment_id=pending_clarification_comment_id,
    )


def _drive_needs_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_settings: Settings,
    *,
    source_kind: str,
    metadata: dict[str, Any],
    github_client_factory: runner_module.GitHubClientFactory,
    pending_clarification_comment_id: int | None = None,
    questions: list[str] = _QUESTIONS,
) -> tuple[RunStatus, list[dict[str, Any]]]:
    """Drive ``_run_current_role`` once against a scripted ``NEEDS_INPUT``
    result and return ``(new_status, apply_transition_call_kwargs)``."""
    # Patches the settings accessor the runner module itself resolves (the
    # same module-attribute override idiom tests/unit/test_load_github.py
    # already uses), covering all three of _run_current_role's conditionally
    # -taken get_settings() reads with one patch rather than one per branch.
    monkeypatch.setattr(runner_module, "get_settings", lambda: fake_settings)
    repo_root = make_git_repo(tmp_path / "repo", base_branch="main")
    run_id = uuid4()
    role_execution_id = uuid4()
    working_branch = working_branch_name(run_id)
    state = _run_state(
        run_id,
        role_execution_id,
        source_kind=source_kind,
        metadata=metadata,
        working_branch=working_branch,
        pending_clarification_comment_id=pending_clarification_comment_id,
    )
    pipeline = pipeline_from_snapshot(state.workflow)
    registry = _registry_with_script([_needs_input_result(questions)])
    lease = LeaseHandle(token=uuid4(), lease_lost=threading.Event())

    calls: list[dict[str, Any]] = []

    def _apply_transition_spy(session: object, **kwargs: Any) -> RunStatus:
        calls.append(kwargs)
        return RunStatus.WAITING_HUMAN

    monkeypatch.setattr(runner_module, "apply_transition", _apply_transition_spy)

    new_status = runner_module._run_current_role(
        run_id,
        state,
        pipeline,
        registry,
        _NoOpSession,
        lease,
        repo_root=repo_root,
        github_client_factory=github_client_factory,
    )
    return new_status, calls


# --------------------------------------------------------------------------- #
# build_clarification_comment
# --------------------------------------------------------------------------- #


def test_body_starts_with_the_fixed_prefix_and_ends_with_the_newline_join() -> None:
    body = build_clarification_comment(["a", "b"])
    assert body.startswith(CLARIFICATION_COMMENT_PREFIX)
    assert body.endswith("a\nb")


def test_body_preserves_emoji_cjk_and_markdown_verbatim() -> None:
    questions = ["你好? \U0001f600", "**bold** _and_ `code`?"]
    body = build_clarification_comment(questions)
    assert questions[0] in body
    assert questions[1] in body


def test_body_takes_only_the_question_list() -> None:
    """``build_clarification_comment`` accepts exactly one parameter -- a
    parameter it does not receive is a value it cannot leak (T-10-12)."""
    import inspect

    signature = inspect.signature(build_clarification_comment)
    assert list(signature.parameters) == ["questions"]


def test_body_never_contains_run_role_worker_worktree_or_branch_values() -> None:
    """T-10-12 made mechanical: five internal-state values that would be in
    scope at the call site are each absent from the produced body."""
    run_id = str(uuid4())
    role_execution_id = str(uuid4())
    worker_name = "claude-code"
    worktree_path = "/dark-factory-runs/deadbeef-cafe-0000-0000-000000000000"
    branch_name = "dark-factory/run-deadbeef-cafe-0000-0000-000000000000"

    body = build_clarification_comment(_QUESTIONS)

    assert run_id not in body
    assert role_execution_id not in body
    assert worker_name not in body
    assert worktree_path not in body
    assert branch_name not in body


# --------------------------------------------------------------------------- #
# The Signal.ROLE_NEEDS_INPUT branch
# --------------------------------------------------------------------------- #


def test_github_sourced_run_posts_one_comment_and_threads_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    fake = FakeGitHubClient(issue=_scripted_issue())
    new_status, calls = _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="github",
        metadata={
            "owner": _OWNER,
            "repo": _REPO,
            "issue_number": _ISSUE_NUMBER,
            "labels": [],
            "comment_count": 0,
        },
        github_client_factory=lambda: fake,
    )

    assert new_status is RunStatus.WAITING_HUMAN
    # CR-01: the existence check (fetch_issue + authenticated_login) runs
    # before create_comment -- finds nothing on this scripted, comment-free
    # issue, so exactly one create_comment call still follows.
    fetch_calls = [c for c in fake.calls if c[0] == "fetch_issue"]
    assert len(fetch_calls) == 1
    create_calls = [c for c in fake.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1
    kwargs = create_calls[0][1]
    assert kwargs["owner"] == _OWNER
    assert kwargs["repo"] == _REPO
    assert kwargs["issue_number"] == _ISSUE_NUMBER
    assert kwargs["body"] == build_clarification_comment(_QUESTIONS)

    assert len(calls) == 1
    human_interaction = calls[0]["human_interaction"]
    assert human_interaction.mode == "ask"
    assert human_interaction.question == "\n".join(_QUESTIONS)
    assert human_interaction.clarification_comment_id == 1  # FakeGitHubClient's fixed id


def test_an_already_posted_own_comment_is_adopted_without_a_second_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    """CR-01 (10-REVIEW.md): the crash-safety-net existence check finds a
    comment Dark Factory's own identity already posted, carrying the exact
    question text, and adopts it -- ``create_comment`` is never called a
    second time. This is what closes the duplicate-post window between a
    successful ``create_comment`` call and the transaction that persists
    ``clarification_comment_id``: a resumed attempt that reaches this branch
    again (because nothing was committed before the simulated crash) must
    not re-post."""
    body = build_clarification_comment(_QUESTIONS)
    already_posted = GitHubComment(id=555, author="dark-factory-bot", body=body)
    fake = FakeGitHubClient(issue=_scripted_issue(comments=[already_posted]))

    new_status, calls = _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="github",
        metadata={
            "owner": _OWNER,
            "repo": _REPO,
            "issue_number": _ISSUE_NUMBER,
            "labels": [],
            "comment_count": 0,
        },
        github_client_factory=lambda: fake,
    )

    assert new_status is RunStatus.WAITING_HUMAN
    assert {name for name, _ in fake.calls} == {"fetch_issue", "authenticated_login"}
    assert [name for name, _ in fake.calls if name == "create_comment"] == []
    human_interaction = calls[0]["human_interaction"]
    assert human_interaction.clarification_comment_id == 555


def test_a_comment_from_someone_else_with_the_same_text_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    """The existence check matches on author identity, not text alone -- a
    look-alike comment posted by a different login (e.g. a human who quoted
    the question) must never be mistaken for Dark Factory's own post."""
    body = build_clarification_comment(_QUESTIONS)
    someone_elses_comment = GitHubComment(id=777, author="a-human", body=body)
    fake = FakeGitHubClient(issue=_scripted_issue(comments=[someone_elses_comment]))

    new_status, calls = _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="github",
        metadata={
            "owner": _OWNER,
            "repo": _REPO,
            "issue_number": _ISSUE_NUMBER,
            "labels": [],
            "comment_count": 0,
        },
        github_client_factory=lambda: fake,
    )

    assert new_status is RunStatus.WAITING_HUMAN
    create_calls = [c for c in fake.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1
    human_interaction = calls[0]["human_interaction"]
    assert human_interaction.clarification_comment_id == 1  # the newly created comment


def test_pending_comment_id_already_set_skips_the_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    """D-05: a pending interaction that already carries a
    ``clarification_comment_id`` is never re-posted -- an empty client call log."""
    fake = FakeGitHubClient()
    new_status, calls = _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="github",
        metadata={
            "owner": _OWNER,
            "repo": _REPO,
            "issue_number": _ISSUE_NUMBER,
            "labels": [],
            "comment_count": 0,
        },
        github_client_factory=lambda: fake,
        pending_clarification_comment_id=999,
    )

    assert new_status is RunStatus.WAITING_HUMAN
    assert fake.calls == []
    human_interaction = calls[0]["human_interaction"]
    assert human_interaction.clarification_comment_id == 999


def test_text_sourced_run_never_calls_the_client_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    def _raising_factory() -> GitHubClient:
        raise AssertionError("github_client_factory must not be called for a text: run")

    new_status, calls = _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="text",
        metadata={},
        github_client_factory=_raising_factory,
    )

    assert new_status is RunStatus.WAITING_HUMAN
    human_interaction = calls[0]["human_interaction"]
    assert human_interaction.clarification_comment_id is None
    assert human_interaction.mode == "ask"
    assert human_interaction.question == "\n".join(_QUESTIONS)


def test_raising_create_comment_still_pauses_with_no_id_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    fake = FakeGitHubClient(
        issue=_scripted_issue(),
        raises={
            "create_comment": GitHubApiError(
                "service unavailable", status_code=503, endpoint="issues.create_comment"
            )
        },
    )

    new_status, calls = _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="github",
        metadata={
            "owner": _OWNER,
            "repo": _REPO,
            "issue_number": _ISSUE_NUMBER,
            "labels": [],
            "comment_count": 0,
        },
        github_client_factory=lambda: fake,
    )

    assert new_status is RunStatus.WAITING_HUMAN
    assert len(calls) == 1
    kwargs = calls[0]
    human_interaction = kwargs["human_interaction"]
    assert human_interaction.mode == "ask"
    assert human_interaction.question == "\n".join(_QUESTIONS)
    assert human_interaction.clarification_comment_id is None
    # The pause events are unchanged -- QUESTION_CREATED and RUN_PAUSED still
    # both fire, and the failure text rides QUESTION_CREATED's own payload
    # rather than a new event type.
    event_types = [event.type.value for event in kwargs["events"]]
    assert event_types == ["QUESTION_CREATED", "RUN_PAUSED"]
    question_event = kwargs["events"][0]
    assert "clarification_comment_error" in question_event.payload
    assert "service unavailable" in question_event.payload["clarification_comment_error"]


def test_no_scenario_ever_calls_a_comment_update_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_settings: Settings
) -> None:
    """D-08: each ``ROLE_NEEDS_INPUT`` posts a fresh comment and never edits a
    prior one. ``GitHubClient`` (and its fake) expose no update/edit method at
    all, so this is proven structurally: the call log contains only the CR-01
    existence-check reads (``fetch_issue``, ``authenticated_login``) plus
    ``create_comment`` -- never an update/edit-shaped call."""
    fake = FakeGitHubClient(issue=_scripted_issue())
    _drive_needs_input(
        tmp_path,
        monkeypatch,
        fake_settings,
        source_kind="github",
        metadata={
            "owner": _OWNER,
            "repo": _REPO,
            "issue_number": _ISSUE_NUMBER,
            "labels": [],
            "comment_count": 0,
        },
        github_client_factory=lambda: fake,
    )
    assert {name for name, _ in fake.calls} == {
        "fetch_issue",
        "authenticated_login",
        "create_comment",
    }
    assert not hasattr(GitHubClient, "update_comment")
    assert not hasattr(GitHubClient, "edit_comment")
