"""GIT-03 through GIT-04, proved against a real ``drive()`` run (Phase 10,
plan 10-06, Task 2):

    Once QA's own attempt transitions with a PASS ``verdict.json`` and the
    Phase 9 quality gate independently passes, Dark Factory collects the
    final diff, commits, pushes, and opens exactly one pull request whose
    number, URL and commit SHA are persisted in the same transaction that
    completes the run; publishing is gated solely on
    ``publishing.create_pr``; a PR-creation failure leaves the run out of
    ``COMPLETED`` with a durable ``PUBLISH_FAILED`` event; and the
    configured base branch is never written to.

Follows ``tests/db/test_quality_gate_gates_the_run.py``'s idiom exactly:
``start_run`` + ``drive`` against real PostgreSQL, an injected
``WorkerRegistry`` wrapping ``tests.support.fake_artifacts.LazyFourRoleWorker``,
a ``config_root_factory``-built config tree whose ``.dark-factory.yaml`` is
overwritten with the ``repository.github_owner`` / ``repository.github_repo``
keys and a hermetic ``quality_gate.commands`` list (the shipped default,
already ``[]``), ``cleanup_runs`` teardown, and the build-then-overwrite idiom
for patching a single generated block.

Two distinct fakes are involved, mirroring ``tests/unit/test_load_github.py``'s
own monkeypatch idiom for the first: ``dark_factory.input.loaders.GitHubClient``
/ ``get_settings`` are monkeypatched so ``start_run("github:<n>", ...)``
resolves the scripted issue with no network call (INTAKE-03's own concern,
already proven at the unit tier by plan 10-01 -- this module reuses the same
patch so a `github:` locator can be driven end to end here too); the
*second* fake is injected through the ``github_client_factory`` seam
``orchestrator/runner.py`` threads through ``drive`` (GIT-03's own concern),
scripted independently per scenario.
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

from dark_factory.artifacts.paths import run_root
from dark_factory.config.loader import load_effective_config
from dark_factory.domain.status import RunStatus
from dark_factory.git.client import run_git
from dark_factory.git.worktree import ensure_worktree, working_branch_name
from dark_factory.github import GitHubApiError
from dark_factory.github.client import GitHubIssue, GitHubPullRequest
from dark_factory.input import loaders
from dark_factory.orchestrator.runner import drive, start_run
from dark_factory.persistence.models import (
    ArtifactReference,
    HumanInteraction,
    RoleExecution,
    Run,
    RunEvent,
)
from dark_factory.workers.base import CodingWorker
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

_REPOSITORY_BLOCK = "repository:\n  base_branch: main\n"
_PUBLISHING_BLOCK = "publishing:\n  create_pr: false\n"


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
    ``test_quality_gate_gates_the_run.py``'s own ``_write_four_role_tree``
    writes -- role YAML files carrying real ``inputs:``/``outputs:``
    declarations (QA's own ``verdict.json`` output is what makes the
    terminal-role gate/publish block fire at all; the shared
    ``config_root_factory`` default of ``outputs: []`` for every role would
    make ``collect_role_artifacts`` never produce a ``verdict.json``-typed
    ``ArtifactReferenceWrite``, silently skipping the whole gate/publish
    block) -- with ``repository.github_owner`` / ``github_repo`` added and
    ``publishing.create_pr`` set explicitly, the build-then-overwrite idiom
    that same module already established for its own
    ``quality_gate.commands`` / ``retry`` blocks. ``quality_gate.commands``
    stays the shipped ``[]`` default (folds to PASS with no commands, per
    ``QualityGateResult.status``)."""
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
) -> uuid.UUID:
    fake_intake_client = FakeGitHubClient(issue=_scripted_issue())
    _patch_intake_client(monkeypatch, fake_intake_client)
    snapshot = load_effective_config(root)
    return start_run(
        f"github:{_ISSUE_NUMBER}",
        session_factory=real_session_factory,
        snapshot=snapshot,
    )


def test_happy_path_completes_with_one_pull_request_and_persisted_identifiers(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_github_four_role_tree(config_root_factory, create_pr=True)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)

    # INTAKE-03 end-to-end proof: the run really was created from a
    # `github:` locator, via `start_run`'s `repository=` wiring.
    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.source_kind == "github"

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

    fake_publish_client = FakeGitHubClient(
        pull_request=GitHubPullRequest(number=99, url="https://example.invalid/pr/99")
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=lambda: fake_publish_client,
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.pr_number == 99
        assert run_row.pr_url == "https://example.invalid/pr/99"
        assert run_row.published_commit_sha is not None

    pr_calls = [c for c in fake_publish_client.calls if c[0] == "create_pull_request"]
    assert len(pr_calls) == 1
    _, kwargs = pr_calls[0]
    assert kwargs["base"] == _BASE_BRANCH
    assert kwargs["head"] == working_branch
    assert kwargs["title"] == _ISSUE_TITLE

    event_types = _event_types(engine, run_id)
    assert "PUBLISH_STARTED" in event_types
    assert "PR_CREATED" in event_types
    assert "PUBLISH_FAILED" not in event_types
    assert event_types.index("PUBLISH_STARTED") < event_types.index("PR_CREATED")


def test_create_pr_false_completes_with_no_pull_request(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_github_four_role_tree(config_root_factory, create_pr=False)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

    def _factory_must_not_be_called() -> FakeGitHubClient:
        raise AssertionError(
            "github_client_factory was called even though publishing.create_pr "
            "is false -- a run that publishes nothing must never construct a "
            "GitHub client"
        )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=_factory_must_not_be_called,
    )
    assert final is RunStatus.COMPLETED

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.pr_number is None
        assert run_row.pr_url is None
        assert run_row.published_commit_sha is None

    event_types = _event_types(engine, run_id)
    assert "PUBLISH_STARTED" not in event_types
    assert "PR_CREATED" not in event_types
    assert "PUBLISH_FAILED" not in event_types


def test_pr_creation_failure_keeps_the_run_out_of_completed(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_github_four_role_tree(config_root_factory, create_pr=True)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

    fake_publish_client = FakeGitHubClient(
        raises={
            "create_pull_request": GitHubApiError(
                "the repository is archived", status_code=422, endpoint="pulls.create"
            )
        }
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=lambda: fake_publish_client,
    )
    assert final is not RunStatus.COMPLETED

    with Session(engine) as session:
        run_row = session.get(Run, run_id)
        assert run_row is not None
        assert run_row.pr_number is None

    event_types = _event_types(engine, run_id)
    assert "PUBLISH_FAILED" in event_types
    assert "PR_CREATED" not in event_types


def test_the_base_branch_tip_is_unchanged_across_a_full_publishing_run(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_github_four_role_tree(config_root_factory, create_pr=True)
    base_tip_before = run_git(["rev-parse", _BASE_BRANCH], cwd=root).stdout.strip()

    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)

    working_branch = working_branch_name(run_id)
    work_dir = ensure_worktree(
        root, run_id, base_branch=_BASE_BRANCH, working_branch=working_branch
    )
    run_dir = run_root(work_dir, run_id)
    worker = LazyFourRoleWorker(run_dir)

    fake_publish_client = FakeGitHubClient(
        pull_request=GitHubPullRequest(number=7, url="https://example.invalid/pr/7")
    )

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=_registry(worker),
        repo_root=root,
        github_client_factory=lambda: fake_publish_client,
    )
    assert final is RunStatus.COMPLETED

    base_tip_after = run_git(["rev-parse", _BASE_BRANCH], cwd=root).stdout.strip()
    assert base_tip_after == base_tip_before

    # The run's own commits live only on its working branch -- reachable from
    # `working_branch` but not an ancestor-of-base relationship the other way
    # around, and the base branch's own log is untouched by name.
    working_branch_log = run_git(
        ["log", working_branch, "--format=%H"], cwd=root
    ).stdout.splitlines()
    assert base_tip_before in working_branch_log  # base is an ancestor
    base_branch_log = run_git(
        ["log", _BASE_BRANCH, "--format=%H"], cwd=root
    ).stdout.splitlines()
    assert base_branch_log == [base_tip_before]  # base gained nothing new
