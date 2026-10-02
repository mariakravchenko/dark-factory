"""The publish step (D-05, D-06, D-07, D-09, GIT-03, GIT-04).

Once the pipeline's terminal role's own attempt has a PASS ``verdict.json``
and the Phase 9 quality gate itself passes, ``orchestrator/runner.py`` calls
:func:`run_publish_step` directly -- a plain function call, never through
``ToolRegistry``, with no ``WorkerRegistry`` entry, no role config and no
``role_executions`` row of its own (mirroring ``orchestrator/quality_gate.py``'s
D-01 posture exactly). A crash inside this function leaves the terminal
role's ``role_executions`` row at ``RUNNING``, so the terminal role's worker
re-executes on resume -- the pre-existing, already-accepted behaviour a crash
during the Phase 9 gate has, not something this phase introduces.

**Idempotency (Phase 10, plan 10-02, GIT-04, D-06).** A database flag alone
cannot prove an external side effect did or did not happen -- a ``NULL``
``pr_number`` means "not recorded", never "not created". ``run_publish_step``
therefore checks two complementary things, in order, each covering a
distinct partial-completion point:

1. **The fast path -- three persisted identifiers together.** When
   ``state.published_commit_sha`` and ``state.pr_number`` are both already
   set, the run has a pull request on record; return it verbatim with
   ``adopted_existing_pr=True`` and issue **no git command and no GitHub API
   call at all**. This is the common case on every retry.
2. **The crash-safety net -- GitHub's own state.** Otherwise, commit and
   push only what has not yet been pushed (``published_commit_sha`` already
   set means that half already happened), then ask GitHub itself --
   :meth:`~dark_factory.github.client.GitHubClient.find_pull_request_for_branch`,
   a pure read matched on head-branch equality only -- whether a pull
   request already exists for this run's deterministic working branch
   *before* creating one. This is the only way to distinguish "never
   attempted" from "attempted, succeeded on GitHub, crashed before the
   commit" (10-RESEARCH.md Pitfall 1): a resumed process's own Neon row is
   silent about an API call that already succeeded.

The three partial-completion points this covers: (a) nothing pushed yet --
commit, push, existence check, then create; (b) pushed and
``published_commit_sha`` set but ``pr_number`` NULL -- no second commit, the
existence check runs, create only if it found nothing; (c) all three set --
no git command and no GitHub call at all. The fast path and the safety net
are complementary, not redundant: the fast path is what makes every ordinary
retry free, and the safety net is what makes the one narrow "Neon says no PR
yet" branch safe.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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
    """The outcome of one publish attempt (GIT-03, GIT-04).

    Plain fields, no folded/derived success flag -- unlike
    ``QualityGateResult.status`` there is no natural boolean fold here
    (``error is None`` already says everything a caller needs), so this model
    stays independent fields rather than introducing a ``computed_field``
    with nothing to compute.

    ``adopted_existing_pr`` (D-06) records whether the returned pull request
    was created by this attempt or found already existing on GitHub -- the
    fact the caller's ``PR_CREATED`` event payload needs to distinguish
    "opened now" from "already open", and the fact a reader of Neon needs to
    answer "did this run open two pull requests?" without querying GitHub. A
    plain declared field, not a derived one: it is an observation about what
    happened, not a fold over the other fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    published_commit_sha: str | None
    pr_number: int | None
    pr_url: str | None
    error: str | None
    adopted_existing_pr: bool = False


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
    push_token: str | None,
) -> PublishResult:
    """Commit, push and open exactly one pull request -- at most once ever,
    even across a crash (GIT-03, GIT-04, D-06, D-09).

    **Stage 1 -- the ``create_pr`` gate.** Returns early with everything
    ``None`` and ``error=None`` when ``create_pr`` is ``False`` -- publishing
    is gated on the snapshot's ``publishing.create_pr``, and this is the only
    place that gate is checked, before any check and before any call.
    ``client`` may be ``None`` on this path -- the caller never needs to
    construct one for a run that will not publish (GIT-05/GIT-06 enabler: a
    run that publishes nothing and asks nothing never touches
    ``github_client_factory``).

    **Stage 2 -- the fast path over persisted identifiers (D-06).** Reads
    ``state.published_commit_sha`` / ``state.pr_number`` / ``state.pr_url``.
    Also confirms ``state.working_branch`` is exactly
    ``working_branch_name(run_id)`` -- a mismatch is a programming error, not
    a recoverable state, so this raises ``RuntimeError`` (WR-01, 10-REVIEW.md
    -- an explicit raise survives ``-O``/``PYTHONOPTIMIZE=1``, unlike a plain
    ``assert``) rather than silently re-publishing onto a different branch.
    When both ``published_commit_sha`` and
    ``pr_number`` are set, returns them verbatim with
    ``adopted_existing_pr=True`` and issues **no git command and no GitHub
    API call at all** -- the common case on every retry, made free.

    **Stage 3 -- act, with GitHub's own state as the safety net.**
    Otherwise:

    1. When ``published_commit_sha`` is ``None``, reuses the existing git
       primitives verbatim -- never duplicates them:
       :func:`~dark_factory.git.diff.commit_run_artifacts` and
       :func:`~dark_factory.git.diff.push_working_branch` (passing this
       function's own ``push_token`` parameter straight through as the
       ``token`` argument -- this function must be callable in a process
       that has no database configured at all, because the unit tier calls
       it directly, so the token arrives as a parameter rather than a
       process-global settings read), and
       :func:`~dark_factory.git.lifecycle.head_sha` to capture the pushed
       SHA. This function is called from inside the
       terminal role's gate-PASS arm, before ``runner.py``'s own generic
       per-role commit runs -- so this is the commit that actually carries
       the role's own artifacts plus the just-written
       ``verification/quality_gate.json`` onto the working branch; the later
       generic call finds nothing new and safely no-ops. When
       ``published_commit_sha`` is already set, both are skipped -- the
       commit and push already happened, and re-running them would be a
       second side effect for the same logical step.
    2. Resolves ``owner`` / ``repo`` / ``base`` from
       ``state.workflow["repository"]``; ``head`` is
       ``working_branch_name(run_id)`` (D-09: the base branch is the existing
       config value, not a new concept). A repository config with
       ``publishing.create_pr: true`` but no ``github_owner`` /
       ``github_repo`` / ``base_branch`` cannot open a pull request at all --
       this is a configuration gap, not a GitHub API failure, but it must
       fold into the identical ``PublishResult.error`` shape so the caller's
       "never reach ``COMPLETED`` without a real PR" rule (T-10-32) applies
       here too, rather than this function raising an unhandled
       ``AssertionError``/``TypeError`` into the orchestrator loop.
    3. Calls ``client.find_pull_request_for_branch(owner, repo,
       head_branch=working_branch)`` -- the crash-safety net 10-RESEARCH.md
       Pitfall 1 names, and the only thing that distinguishes "never
       attempted" from "attempted, succeeded on GitHub, crashed before the
       commit". A pure read; matches on head-branch equality only, because
       GitHub's own server-side ``head=owner:branch`` filter is what
       guarantees a returned pull request really targets this run's branch
       -- never title, author, base branch or recency (T-10-09: adopting an
       unrelated pull request would silently tie this run to someone else's
       work).
    4. When it returns a pull request, adopts it: returns its number and URL
       with ``adopted_existing_pr=True``, and issues no
       ``create_pull_request`` call -- no retitle, no body rewrite, no base
       change, no reopen (T-10-10): a human may have edited the title or
       body since the interrupted attempt, and a resumed publish step must
       not revert that.
    5. When it returns ``None``, calls ``client.create_pull_request`` with
       ``title = state.normalized_task.title`` and a short generated body
       linking back to the source issue (:func:`_pr_body`), and returns the
       new pull request with ``adopted_existing_pr=False``.
    6. Catches :class:`~dark_factory.github.GitHubError` (which also covers
       :class:`~dark_factory.github.MissingGitHubCredentialError`) from
       *either* GitHub call and returns a :class:`PublishResult` whose
       ``error`` is the redacted message and whose ``pr_number`` is ``None``;
       never re-raises, so the caller owns the signal decision (a run whose
       PR was never created must not reach ``COMPLETED``), and never falls
       through from a failed existence check into a create (T-10-11): an
       unreadable GitHub state is not evidence that no pull request exists.
       A :class:`~dark_factory.git.GitError` from step 1 (the commit/push
       primitives) is deliberately **not** caught here -- it propagates to
       the caller, which already wraps every other ``commit_run_artifacts``
       / ``push_working_branch`` call site in this project's terminal-role
       block in the identical ``GitError`` handling used for a role's own
       artifact commit, so a git-level failure here folds into that one
       existing failure vocabulary rather than a second, publish-specific
       one.

    ``client`` is ``None`` only on the ``create_pr=False`` early-return path;
    the caller's contract is to construct one (via the injected
    ``github_client_factory`` seam) whenever ``create_pr`` is ``True``.

    Constructs no ORM row and assigns no ``.status`` attribute --
    ``tests/unit/test_single_mutation_path.py`` is an AST walk over the whole
    source tree.
    """
    if not create_pr:
        return PublishResult(
            published_commit_sha=None,
            pr_number=None,
            pr_url=None,
            error=None,
            adopted_existing_pr=False,
        )
    # WR-01 (10-REVIEW.md): explicit ``raise``, not ``assert`` -- Python's
    # ``assert`` statement compiles to a no-op under ``-O``/
    # ``PYTHONOPTIMIZE=1``, which would silently disable both of these
    # deliberate runtime safety nets (a mismatch is a programming error, not
    # a recoverable state) in any deployment packaged with optimizations on.
    if client is None:
        raise RuntimeError(
            "run_publish_step: client is None but create_pr is True -- "
            "caller's contract is to construct a client whenever create_pr "
            "is True"
        )

    working_branch = working_branch_name(run_id)
    if state.working_branch != working_branch:
        raise RuntimeError(
            f"run {run_id}: persisted working_branch {state.working_branch!r} does "
            f"not match the deterministic working_branch_name {working_branch!r} -- "
            "refusing to publish onto a mismatched branch"
        )

    # Stage 2: the fast path over persisted identifiers (D-06). Free on every
    # ordinary retry -- no git command, no GitHub API call.
    if state.published_commit_sha is not None and state.pr_number is not None:
        return PublishResult(
            published_commit_sha=state.published_commit_sha,
            pr_number=state.pr_number,
            pr_url=state.pr_url,
            error=None,
            adopted_existing_pr=True,
        )

    # Stage 3: act, with GitHub's own state as the safety net.
    if state.published_commit_sha is None:
        artifact_sha = commit_run_artifacts(work_dir, run_id, role=_PUBLISH_ROLE_LABEL)
        if artifact_sha is not None:
            push_working_branch(
                work_dir, working_branch=working_branch, token=push_token
            )
        published_commit_sha = head_sha(work_dir)
    else:
        # Already committed and pushed by an earlier attempt -- re-running
        # either would be a second side effect for the same logical step.
        published_commit_sha = state.published_commit_sha

    repository = state.workflow.get("repository") or {}
    owner_raw = repository.get("github_owner")
    repo_raw = repository.get("github_repo")
    base_raw = repository.get("base_branch")
    # Checked and returned field-by-field (rather than collected into a
    # list) so mypy --strict narrows each ``Any | None`` to ``str`` for the
    # calls below.
    if not isinstance(owner_raw, str) or not owner_raw:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error="cannot open a pull request: repository.github_owner is not set",
            adopted_existing_pr=False,
        )
    if not isinstance(repo_raw, str) or not repo_raw:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error="cannot open a pull request: repository.github_repo is not set",
            adopted_existing_pr=False,
        )
    if not isinstance(base_raw, str) or not base_raw:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error="cannot open a pull request: repository.base_branch is not set",
            adopted_existing_pr=False,
        )
    owner: str = owner_raw
    repo: str = repo_raw
    base: str = base_raw

    try:
        existing_pr = client.find_pull_request_for_branch(
            owner, repo, head_branch=working_branch
        )
    except GitHubError as exc:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=None,
            pr_url=None,
            error=str(redact(str(exc), known_secrets=known_secrets)),
            adopted_existing_pr=False,
        )

    if existing_pr is not None:
        return PublishResult(
            published_commit_sha=published_commit_sha,
            pr_number=existing_pr.number,
            pr_url=existing_pr.url,
            error=None,
            adopted_existing_pr=True,
        )

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
            adopted_existing_pr=False,
        )

    return PublishResult(
        published_commit_sha=published_commit_sha,
        pr_number=pr.number,
        pr_url=pr.url,
        error=None,
        adopted_existing_pr=False,
    )
