"""GIT-04, proved against a real ``drive()`` run and real PostgreSQL (Phase
10, plan 10-02) -- ROADMAP success criterion 3: "killing the process after
the PR API call but before its identifier is committed, then resuming,
yields one PR, not two."

Follows ``tests/db/test_publish_step.py``'s idiom exactly (the same
``config_root_factory`` tree with ``repository.github_owner`` /
``repository.github_repo`` set, the same ``LazyFourRoleWorker``-backed
``WorkerRegistry``, the same ``FakeGitHubClient`` injection through the
``github_client_factory`` seam, the same ``cleanup_runs`` teardown, and the
build-then-overwrite idiom for patching a single generated config block).

The crash window is reproduced **in process** (mirrors
``tests/db/test_wip_commit_recovery.py``'s db-tier idiom): the module-level
``apply_transition`` symbol ``orchestrator/runner.py`` calls is monkeypatched
to raise, but only for the specific call that would carry a non-``None``
``publish_fields`` -- i.e. only the terminal role's own final transition,
never the BA/ARCHITECTURE/DEVELOPMENT/QA-entry transitions that precede it.
This targets exactly the window 10-RESEARCH.md Pitfall 1 names: GitHub has
already returned success for ``pulls.create``, but Neon has not yet recorded
it. The claim under test is about GitHub-side state (one pull request, not
two), not about process identity -- whether a brand-new OS process on a
different machine can pick a run up is already proven by
``tests/integration/test_fresh_process_resume.py`` (Phase 11 scope), so this
file does not add a new ``os._exit`` environment hook.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import dark_factory.orchestrator.runner as runner_module
from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.github.client import GitHubIssue, GitHubPullRequest
from dark_factory.input import loaders
from dark_factory.orchestrator.publish import run_publish_step
from dark_factory.orchestrator.runner import advance, drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.persistence.mutations import PublishFieldsWrite, apply_transition
from dark_factory.persistence.repositories import load_run_state
from dark_factory.workers.base import CodingWorker
from dark_factory.workers.fake import FakeWorker
from dark_factory.workers.registry import WorkerRegistry
from tests.support.fake_artifacts import LazyFourRoleWorker
from tests.support.fake_github import FakeGitHubClient

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]

SessionFactory = Callable[[], Session]

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 5
_ISSUE_TITLE = "Fix the flaky retry logic"
_BASE_BRANCH = "main"
_SEED_SHA = "deadbeef" * 5  # a 40-character placeholder SHA

_REPOSITORY_BLOCK = "repository:\n  base_branch: main\n"
_PUBLISHING_BLOCK = "publishing:\n  create_pr: false\n"


class _CrashSwitch:
    """A mutable flag so the crash-inducing ``apply_transition`` wrapper can
    be turned off mid-test without re-monkeypatching (which would require a
    second ``monkeypatch.setattr`` call reaching back into a module already
    unwound by the fixture's teardown ordering)."""

    def __init__(self) -> None:
        self.enabled = True


class _HeadScopedFakeGitHubClient(FakeGitHubClient):
    """A minimal double simulating GitHub's own server-side ``head=`` filter
    on ``pulls.list``: the scripted "existing" pull request is returned only
    when the requested ``head_branch`` matches ``scripted_head_branch`` -- a
    foreign branch returns ``None``, exactly as the real
    :class:`~dark_factory.github.client.GitHubClient`'s
    ``head=f"{owner}:{branch}"``-filtered call would. Kept local to this file
    (not an extension of the shared ``tests/support/fake_github.py`` fixture,
    out of this plan's ``files_modified``)."""

    def __init__(self, *, scripted_head_branch: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._scripted_head_branch = scripted_head_branch

    def find_pull_request_for_branch(
        self, owner: str, repo: str, *, head_branch: str
    ) -> GitHubPullRequest | None:
        if head_branch != self._scripted_head_branch:
            self.calls.append(
                (
                    "find_pull_request_for_branch",
                    {"owner": owner, "repo": repo, "head_branch": head_branch},
                )
            )
            self._maybe_raise("find_pull_request_for_branch")
            return None
        return super().find_pull_request_for_branch(owner, repo, head_branch=head_branch)


class _StubClientFactory:
    """Stands in for ``GitHubClient`` at the loader's own call site --
    ``.from_settings(settings)`` returns a pre-built :class:`FakeGitHubClient`,
    matching ``tests/unit/test_load_github.py``'s identical idiom."""

    def __init__(self, client: FakeGitHubClient) -> None:
        self._client = client

    def from_settings(self, settings: object) -> FakeGitHubClient:
        return self._client


def _patch_intake_client(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeGitHubClient
) -> None:
    monkeypatch.setattr(loaders, "get_settings", lambda: object())
    monkeypatch.setattr(loaders, "GitHubClient", _StubClientFactory(fake_client))


def _write_github_four_role_tree(
    config_root_factory: Callable[..., Path], *, create_pr: bool
) -> Path:
    """The same ``[BA, ARCHITECTURE, DEVELOPMENT, QA]`` config tree
    ``tests/db/test_publish_step.py``'s own helper writes -- role YAML files
    with real ``inputs:``/``outputs:`` declarations (QA's own ``verdict.json``
    output is what makes the terminal-role gate/publish block fire at all),
    with ``repository.github_owner``/``github_repo`` added and
    ``publishing.create_pr`` set explicitly."""
    root = config_root_factory(roles=("BA", "ARCHITECTURE", "DEVELOPMENT", "QA"))
    definitions = {
        "BA": ("[]", "[requirements.md, acceptance_criteria.json]"),
        "ARCHITECTURE": (
            "[acceptance_criteria.json]",
            "[design.md, constraints.json]",
        ),
        "DEVELOPMENT": (
            "[design.md, constraints.json]",
            "[implementation_summary.json]",
        ),
        "QA": (
            "[acceptance_criteria.json, implementation_summary.json]",
            "[test_report.json, verdict.json]",
        ),
    }
    tools = {
        "BA": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "ARCHITECTURE": "[repo.read, repo.search, artifacts.read, artifacts.write]",
        "DEVELOPMENT": (
            "[repo.read, repo.search, repo.write, repo.write_tests, "
            "shell.execute, artifacts.read, artifacts.write]"
        ),
        "QA": (
            "[repo.read, repo.search, repo.write_tests, shell.execute, "
            "artifacts.read, artifacts.write]"
        ),
    }
    for role, (inputs, outputs) in definitions.items():
        (root / f".dark-factory/roles/{role}.yaml").write_text(
            f"name: {role}\n"
            "worker: fake\n"
            f"instructions: ../instructions/{role.lower()}.md\n"
            f"tools: {tools[role]}\n"
            "permissions:\n  write_scope: []\n"
            "before: [prepare_role_context]\n"
            "after: [store_role_artifacts]\n"
            f"inputs: {inputs}\n"
            f"outputs: {outputs}\n"
            "examples: []\n",
            encoding="utf-8",
        )

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
    assert _PUBLISHING_BLOCK in patched, (
        "conftest.py's _write_config_tree no longer writes "
        "'publishing:\\n  create_pr: false\\n' verbatim -- update this test's "
        "overwrite string to match"
    )
    patched = patched.replace(
        _PUBLISHING_BLOCK,
        f"publishing:\n  create_pr: {'true' if create_pr else 'false'}\n",
    )
    config_path.write_text(patched, encoding="utf-8")
    return root


def _registry(worker: CodingWorker) -> WorkerRegistry:
    registry = WorkerRegistry()
    registry.register("fake", lambda: worker)
    return registry


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
            conn.execute(
                sa.delete(ArtifactReference).where(ArtifactReference.run_id.in_(ids))
            )
            conn.execute(sa.delete(RunEvent).where(RunEvent.run_id.in_(ids)))
            conn.execute(
                sa.delete(HumanInteraction).where(HumanInteraction.run_id.in_(ids))
            )
            conn.execute(sa.delete(RoleExecution).where(RoleExecution.run_id.in_(ids)))
            conn.execute(sa.delete(Run).where(Run.id.in_(ids)))


def _start_github_run(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    real_session_factory: SessionFactory,
) -> uuid.UUID:
    fake_intake_client = FakeGitHubClient(issue=_scripted_issue())
    _patch_intake_client(monkeypatch, fake_intake_client)
    snapshot = load_effective_config(root)
    return start_run(
        f"github:{_ISSUE_NUMBER}",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )


def _drive_to_crash(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    *,
    first_attempt_client: FakeGitHubClient,
) -> tuple[uuid.UUID, str, Path, _CrashSwitch, dict[str, Any], LazyFourRoleWorker]:
    """Drive a real ``github:``-sourced four-role run up to the exact crash
    window: the terminal role's own final ``apply_transition`` call -- the
    one carrying ``publish_fields`` -- raises instead of committing, after
    the fake ``create_pull_request`` call has already "succeeded" on the
    GitHub side. Returns everything a scenario needs to script and drive the
    resumed attempt.
    """
    root = _write_github_four_role_tree(config_root_factory, create_pr=True)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

    real_apply_transition = runner_module.apply_transition
    switch = _CrashSwitch()

    def _crash_before_publish_commit(*args: Any, **kwargs: Any) -> RunStatus:
        if switch.enabled and kwargs.get("publish_fields") is not None:
            raise RuntimeError(
                "simulated crash: pulls.create returned, before its "
                "identifier was committed"
            )
        result: RunStatus = real_apply_transition(*args, **kwargs)
        return result

    monkeypatch.setattr(runner_module, "apply_transition", _crash_before_publish_commit)

    client_holder: dict[str, Any] = {"client": first_attempt_client}

    with pytest.raises(RuntimeError):
        drive(
            run_id,
            session_factory=real_session_factory,
            registry=_registry(worker),
            repo_root=root,
            github_client_factory=lambda: client_holder["client"],
        )

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.pr_number is None

    create_calls = [
        c for c in first_attempt_client.calls if c[0] == "create_pull_request"
    ]
    assert len(create_calls) == 1, (
        "the crashed attempt must have called create_pull_request exactly "
        f"once before the simulated crash; calls={first_attempt_client.calls}"
    )

    return run_id, working_branch, root, switch, client_holder, worker


def test_crash_between_pull_request_creation_and_its_commit_yields_one_pull_request(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    force_lease_expiry: Callable[[uuid.UUID], None],
) -> None:
    created_pr = GitHubPullRequest(number=99, url="https://example.invalid/pr/99")
    first_client = FakeGitHubClient(pull_request=created_pr)

    run_id, working_branch, root, switch, client_holder, worker = _drive_to_crash(
        config_root_factory,
        real_session_factory,
        cleanup_runs,
        engine,
        monkeypatch,
        first_attempt_client=first_client,
    )

    # Remove the crash and let the run resume, exactly as a fresh
    # `dark-factory resume`/`drive()` call after a real process death would:
    # GitHub already has the pull request the first attempt created, so the
    # resumed attempt's existence check must find and adopt it.
    switch.enabled = False
    force_lease_expiry(run_id)
    resume_client = FakeGitHubClient(existing_pull_request=created_pr)
    client_holder["client"] = resume_client

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=lambda: client_holder["client"],
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.pr_number == 99
        assert run_row.pr_url == "https://example.invalid/pr/99"

    total_create_calls = len(
        [c for c in first_client.calls if c[0] == "create_pull_request"]
    ) + len([c for c in resume_client.calls if c[0] == "create_pull_request"])
    assert total_create_calls == 1

    find_calls = [
        c for c in resume_client.calls if c[0] == "find_pull_request_for_branch"
    ]
    assert len(find_calls) == 1
    assert find_calls[0][1]["head_branch"] == working_branch


def test_a_run_with_all_three_identifiers_recorded_reenters_with_an_empty_call_log(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
) -> None:
    """Plain retry with everything recorded (point c): re-entering the
    publish step against a real, Postgres-loaded :class:`RunState` whose
    three identifiers are all set issues zero GitHub calls and returns them
    byte for byte."""
    root = config_root_factory(roles=("QA",))
    snapshot = load_effective_config(root)
    run_id = start_run(
        "text:seed a fully-recorded publish state",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )
    cleanup_runs.append(run_id)

    # Enter QA (the pipeline's only role) without ever running its worker --
    # this test only needs the role_executions row to exist so the run's
    # `current_role`/`status` are QA; the FakeWorker script is never called.
    status = advance(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(FakeWorker([])),
        repo_root=root,
    )
    assert status is RunStatus.QA

    with real_session_factory() as session:
        seeded = load_run_state(session, run_id)
    assert seeded is not None

    seeded_pr_url = "https://example.invalid/pr/42"
    with real_session_factory() as session:
        apply_transition(
            session,
            run_id=run_id,
            expected_status=RunStatus.QA,
            next_status=RunStatus.QA,
            next_current_role="QA",
            next_current_step=seeded.current_step,
            publish_fields=PublishFieldsWrite(
                pr_number=42,
                pr_url=seeded_pr_url,
                published_commit_sha=_SEED_SHA,
            ),
        )

    with real_session_factory() as session:
        state = load_run_state(session, run_id)
    assert state is not None
    assert state.pr_number == 42
    assert state.pr_url == seeded_pr_url
    assert state.published_commit_sha == _SEED_SHA

    fake = FakeGitHubClient()
    result = run_publish_step(
        run_id=run_id,
        state=state,
        work_dir=Path("/dark-factory-test/never-touched"),
        client=fake,
        create_pr=True,
        known_secrets={},
        push_token=None,  # fast path: all three identifiers recorded, no push
    )

    assert result.pr_number == 42
    assert result.pr_url == seeded_pr_url
    assert result.published_commit_sha == _SEED_SHA
    assert result.adopted_existing_pr is True
    assert fake.calls == []


def test_adoption_is_head_branch_scoped(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    force_lease_expiry: Callable[[uuid.UUID], None],
) -> None:
    """A scripted existing pull request on a different head branch is never
    adopted -- the "MUST NOT adopt an arbitrary pre-existing pull request"
    prohibition, made mechanical: the resumed attempt calls
    ``create_pull_request`` again (total 2 across both attempts) and the
    final recorded number is never the unrelated pull request's."""
    created_pr = GitHubPullRequest(number=111, url="https://example.invalid/pr/111")
    first_client = FakeGitHubClient(pull_request=created_pr)

    run_id, _working_branch, root, switch, client_holder, worker = _drive_to_crash(
        config_root_factory,
        real_session_factory,
        cleanup_runs,
        engine,
        monkeypatch,
        first_attempt_client=first_client,
    )

    switch.enabled = False
    force_lease_expiry(run_id)
    unrelated_pr = GitHubPullRequest(number=555, url="https://example.invalid/pr/555")
    second_pr = GitHubPullRequest(number=222, url="https://example.invalid/pr/222")
    resume_client = _HeadScopedFakeGitHubClient(
        scripted_head_branch="dark-factory/run-some-other-run-entirely",
        existing_pull_request=unrelated_pr,
        pull_request=second_pr,
    )
    client_holder["client"] = resume_client

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=lambda: client_holder["client"],
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.pr_number == 222
        assert run_row.pr_number != 555

    total_create_calls = len(
        [c for c in first_client.calls if c[0] == "create_pull_request"]
    ) + len([c for c in resume_client.calls if c[0] == "create_pull_request"])
    assert total_create_calls == 2


def test_the_resumed_attempt_issues_no_pull_request_mutating_call(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    force_lease_expiry: Callable[[uuid.UUID], None],
) -> None:
    """The "MUST NOT mutate a pull request that already exists" prohibition,
    made mechanical: after adopting an existing pull request on resume, the
    injected client's call log contains no update/retitle/reopen/merge-shaped
    entry -- only the existence check (``FakeGitHubClient``, mirroring the
    real ``GitHubClient``, exposes no such method at all, so this is a
    structural guarantee this test makes explicit)."""
    created_pr = GitHubPullRequest(number=77, url="https://example.invalid/pr/77")
    first_client = FakeGitHubClient(pull_request=created_pr)

    run_id, _working_branch, root, switch, client_holder, worker = _drive_to_crash(
        config_root_factory,
        real_session_factory,
        cleanup_runs,
        engine,
        monkeypatch,
        first_attempt_client=first_client,
    )

    switch.enabled = False
    force_lease_expiry(run_id)
    resume_client = FakeGitHubClient(existing_pull_request=created_pr)
    client_holder["client"] = resume_client

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=lambda: client_holder["client"],
    )
    assert final is RunStatus.COMPLETED

    assert {name for name, _ in resume_client.calls} <= {
        "find_pull_request_for_branch",
        "create_pull_request",
    }
    assert [c for c in resume_client.calls if c[0] == "create_pull_request"] == []
