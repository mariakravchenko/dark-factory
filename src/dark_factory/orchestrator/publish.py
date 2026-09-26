"""The publish step (D-05, D-06, D-07, D-09, GIT-03).

Once the pipeline's terminal role's own attempt has a PASS ``verdict.json``
and the Phase 9 quality gate itself passes, ``orchestrator/runner.py`` calls
:func:`run_publish_step` directly -- a plain function call, never through
``ToolRegistry``, with no ``WorkerRegistry`` entry, no role config and no
``role_executions`` row of its own (mirroring ``orchestrator/quality_gate.py``'s
D-01 posture exactly). A crash inside this function leaves the terminal
role's ``role_executions`` row at ``RUNNING``, so the terminal role's worker
re-executes on resume -- the pre-existing, already-accepted behaviour a crash
during the Phase 9 gate has, not something this phase introduces.

The GitHub-side existing-PR check that closes the crash-between-API-call-and
-commit window is deliberately absent here and lands in plan 10-02.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from dark_factory.config.settings import get_settings
from dark_factory.events.redaction import redact
from dark_factory.git.diff import commit_run_artifacts, push_working_branch
from dark_factory.git.lifecycle import head_sha
from dark_factory.git.worktree import working_branch_name
from dark_factory.github import GitHubError
from dark_factory.github.client import GitHubClient
from dark_factory.persistence.repositories import RunState

__all__ = ["PublishResult", "run_publish_step"]

# Deliberately not one of the six RunStatus role values -- this is the `role`
# argument threaded into `commit_run_artifacts` (purely for the git commit
# message text), naming the orchestrator-only nature of the publish step's
# own commit. Never a RunStatus role literal, so
# tests/unit/test_no_role_name_literal.py stays green.
_PUBLISH_ROLE_LABEL = "publish"


class PublishResult(BaseModel):
    """The outcome of one publish attempt (GIT-03).

    Plain fields, no folded/derived success flag -- unlike
    ``QualityGateResult.status`` there is no natural boolean fold here
    (``error is None`` already says everything a caller needs), so this model
    stays four independent fields rather than introducing a ``computed_field``
    with nothing to compute.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    published_commit_sha: str | None
    pr_number: int | None
    pr_url: str | None
    error: str | None


def _pr_body(state: RunState) -> str:
    """A short PR body linking back to the source issue (D-09).

    Built from the ``owner`` / ``repo`` / ``issue_number`` metadata keys
    plan 10-01's Task 2 decision (A1) selected -- the same keys
    ``_load_github`` populates on ``NormalizedTask.metadata``. Carries no run
    id, worktree path, worker name, branch name or credential (T-10-34):
    every value here is either a Dark Factory attribution line or an
    issue-identity triple, never anything execution-scoped.
    """
    metadata: Mapping[str, Any] = state.normalized_task.metadata
    owner = metadata.get("owner")
    repo = metadata.get("repo")
    issue_number = metadata.get("issue_number")
    lines = ["Produced by Dark Factory."]
    if owner and repo and issue_number is not None:
        lines.append(f"Closes {owner}/{repo}#{issue_number}")
    return "\n\n".join(lines)


def run_publish_step(
    *,
    run_id: UUID,
    state: RunState,
    work_dir: Path,
    client: GitHubClient | None,
    create_pr: bool,
    known_secrets: Mapping[str, str],
) -> PublishResult:
    """Commit, push and open exactly one pull request (GIT-03, D-09).

    1. Returns early with everything ``None`` and ``error=None`` when
       ``create_pr`` is ``False`` -- publishing is gated on the snapshot's
       ``publishing.create_pr``, and this is the only place that gate is
       checked. ``client`` may be ``None`` on this path -- the caller never
       needs to construct one for a run that will not publish (GIT-05/GIT-06
       enabler: a run that publishes nothing and asks nothing never touches
       ``github_client_factory``).
    2. Reuses the existing git primitives verbatim -- never duplicates them:
       :func:`~dark_factory.git.diff.commit_run_artifacts` and
       :func:`~dark_factory.git.diff.push_working_branch` (the same call
       shape ``orchestrator/runner.py`` already uses for every role's own
       artifact commit, including reading the push token as
       ``settings.github_token.get_secret_value() if settings.github_token
       is not None else None``), and :func:`~dark_factory.git.lifecycle.head_sha`
       to capture the pushed SHA (D-06). This function is called from inside
       the terminal role's gate-PASS arm, before ``runner.py``'s own generic
       per-role commit runs -- so this is the commit that actually carries
       the role's own artifacts plus the just-written
       ``verification/quality_gate.json`` onto the working branch; the later
       generic call finds nothing new and safely no-ops.
    3. Resolves ``owner`` / ``repo`` / ``base`` from
       ``state.workflow["repository"]``; ``head`` is
       ``working_branch_name(run_id)`` (D-09: the base branch is the existing
       config value, not a new concept).
    4. Calls ``client.create_pull_request`` with ``title =
       state.normalized_task.title`` and a short generated body linking back
       to the source issue (:func:`_pr_body`).
    5. Catches :class:`~dark_factory.github.GitHubError` (which also covers
       :class:`~dark_factory.github.MissingGitHubCredentialError`) and returns
       a :class:`PublishResult` whose ``error`` is the redacted message and
       whose ``pr_number`` is ``None``; never re-raises, so the caller owns
       the signal decision (a run whose PR was never created must not reach
       ``COMPLETED``). A :class:`~dark_factory.git.GitError` from step 2 (the
       commit/push primitives) is deliberately **not** caught here -- it
       propagates to the caller, which already wraps every other
       ``commit_run_artifacts`` / ``push_working_branch`` call site in this
       project's terminal-role block in the identical ``GitError`` handling
       used for a role's own artifact commit, so a git-level failure here
       folds into that one existing failure vocabulary rather than a second,
       publish-specific one.

    ``client`` is ``None`` only on the ``create_pr=False`` early-return path;
    the caller's contract is to construct one (via the injected
    ``github_client_factory`` seam) whenever ``create_pr`` is ``True``.

    Constructs no ORM row and assigns no ``.status`` attribute --
    ``tests/unit/test_single_mutation_path.py`` is an AST walk over the whole
    source tree.
    """
    if not create_pr:
        return PublishResult(
            published_commit_sha=None, pr_number=None, pr_url=None, error=None
        )
    assert client is not None  # caller's contract: non-None whenever create_pr

    working_branch = working_branch_name(run_id)
    artifact_sha = commit_run_artifacts(work_dir, run_id, role=_PUBLISH_ROLE_LABEL)
    if artifact_sha is not None:
        settings = get_settings()
        push_token = (
            settings.github_token.get_secret_value()
            if settings.github_token is not None
            else None
        )
        push_working_branch(work_dir, working_branch=working_branch, token=push_token)
    published_commit_sha = head_sha(work_dir)

    repository = state.workflow.get("repository") or {}
    owner_raw = repository.get("github_owner")
    repo_raw = repository.get("github_repo")
    base_raw = repository.get("base_branch")
    # A repository config with `publishing.create_pr: true` (the default) but
    # no `github_owner` / `github_repo` / `base_branch` cannot open a pull
    # request at all -- this is a configuration gap, not a GitHub API
    # failure, but it must fold into the identical PublishResult.error shape
    # so the caller's "never reach COMPLETED without a real PR" rule (T-10-32)
    # applies here too, rather than this function raising an unhandled
    # AssertionError/TypeError into the orchestrator loop. Checked and
    # returned field-by-field (rather than collected into a list) so mypy
    # --strict narrows each ``Any | None`` to ``str`` for the call below.
    if not isinstance(owner_raw, str) or not owner_raw:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error="cannot open a pull request: repository.github_owner is not set",
        )
    if not isinstance(repo_raw, str) or not repo_raw:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error="cannot open a pull request: repository.github_repo is not set",
        )
    if not isinstance(base_raw, str) or not base_raw:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error="cannot open a pull request: repository.base_branch is not set",
        )
    owner: str = owner_raw
    repo: str = repo_raw
    base: str = base_raw

    try:
        pr = client.create_pull_request(
            owner,
            repo,
            title=state.normalized_task.title,
            head=working_branch,
            base=base,
            body=_pr_body(state),
        )
    except GitHubError as exc:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error=str(redact(str(exc), known_secrets=known_secrets)),
        )

    return PublishResult(
        published_commit_sha=published_commit_sha,
        pr_number=pr.number,
        pr_url=pr.url,
        error=None,
    )
