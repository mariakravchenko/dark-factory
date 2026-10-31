"""T-12-08 (OBS-01, SEC-01/SEC-02), proved against a *recorded* GitHub call,
not against ``redact()`` in isolation (plan 12-03, Task 2).

The gap this closes: ``orchestrator/runner.py``'s ``Signal.ROLE_NEEDS_INPUT``
branch built the GitHub clarification-comment body straight from the raw
``WorkerResult.questions`` and handed it to ``create_comment`` with no
``redact()`` call anywhere on that value -- while the sibling write,
``human_interactions.question``, was already scrubbed inside
``_write_human_interaction`` (``persistence/mutations.py``). A GitHub issue
comment is an external, public, permanent, non-revocable sink: redaction
belongs before the API call, not only before the database write.

Follows ``tests/db/test_ask_posts_comment.py``'s scaffolding exactly
(``_write_github_ba_tree``/``_patch_intake_client``/``_scripted_issue``/
``real_session_factory``/``cleanup_runs``, a ``github:``-sourced single-role
``[BA]`` tree, ``drive()`` against real PostgreSQL with an injected
``FakeGitHubClient``) and ``tests/unit/test_clarification_comment.py``'s
``runner_module.get_settings`` monkeypatch idiom -- ``use_fake_secrets`` alone
only patches ``persistence.mutations.get_settings``; the body-redaction read
this plan adds lives inside ``orchestrator/runner.py`` and resolves the
module's own ``get_settings`` name, so it needs its own patch to
``fake_settings`` for the exact-value substitution path to be exercised at
all.

No test in this module calls ``redact()`` directly: a unit test of ``redact``
proves ``redact`` works and proves nothing about whether this call site calls
it -- precisely the gap that let this bug exist for two phases (12-RESEARCH.md).
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
from dark_factory.config.settings import Settings
from dark_factory.domain.status import RunStatus
from dark_factory.domain.worker import WorkerResult, WorkerResultStatus
from dark_factory.github.client import GitHubComment, GitHubIssue
from dark_factory.input import loaders
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
_ISSUE_NUMBER = 91
_ISSUE_TITLE = "Rotate the deploy credentials"
_BASE_BRANCH = "main"

_REPOSITORY_BLOCK = "repository:\n  base_branch: main\n"

# --------------------------------------------------------------------------- #
# Two distinct planted credential shapes, exercising ``redact()``'s two modes.
# --------------------------------------------------------------------------- #

# The exact-value substitution path (D-18): this literal MUST equal
# tests/conftest.py's ``fake_settings`` fixture's configured
# ``anthropic_api_key`` -- a sanity assertion below pins that equality.
# ``sk-ant-``-prefixed text matches none of the compiled D-15 patterns, so
# redact() can only catch it here via known-value substitution, never by shape.
_CONFIGURED_KNOWN_VALUE_SECRET = "sk-ant-FAKEfakeFAKEfake0000000000000000"

# The compiled-pattern-table path (D-15): a ``ghp_``-shaped literal configured
# in no Settings field at all -- redact() can only catch this one by shape,
# never by known-value lookup.
_PATTERN_ONLY_TOKEN = "ghp_" + "PLANTEDtoken".ljust(40, "0")

_NON_SECRET_WORDING = "Should the worker credential be rotated, or the deploy token"

_QUESTIONS = [
    f"{_NON_SECRET_WORDING} {_CONFIGURED_KNOWN_VALUE_SECRET} / {_PATTERN_ONLY_TOKEN}?",
    "Either way, please decide before the next release window.",
]


class _StubClientFactory:
    """Stands in for ``GitHubClient`` at the loader's own call site, mirroring
    ``tests/unit/test_load_github.py`` / ``tests/db/test_ask_posts_comment.py``."""

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


def _scripted_issue(comments: list[GitHubComment] | None = None) -> GitHubIssue:
    return GitHubIssue(
        number=_ISSUE_NUMBER,
        title=_ISSUE_TITLE,
        body="The deploy credentials need to be rotated before the audit.",
        labels=["security"],
        comments=comments or [],
    )


def _needs_input_result() -> WorkerResult:
    return WorkerResult(
        status=WorkerResultStatus.NEEDS_INPUT,
        summary="need a credential-rotation decision",
        questions=list(_QUESTIONS),
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


def _role_execution_and_event_blob(engine: Engine, run_id: UUID) -> str:
    """Every ``role_executions.result``/``error`` and ``run_events.payload``
    value for this run, flattened to one greppable string -- the regression
    anchor for the third test below."""
    with Session(engine) as session:
        execs = list(
            session.scalars(
                sa.select(RoleExecution).where(RoleExecution.run_id == run_id)
            )
        )
        events = list(
            session.scalars(
                sa.select(RunEvent)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            )
        )
    return "\n".join(
        [str(x.result) for x in execs]
        + [str(x.error) for x in execs]
        + [str(e.payload) for e in events]
    )


def test_the_posted_comment_body_is_scrubbed_and_matches_the_persisted_question(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
    fake_settings: Settings,
) -> None:
    # Sanity: the exact-value literal above must actually BE the fixture's
    # configured value, or the exact-value-substitution assertion below would
    # prove nothing (it would only ever be caught by the pattern table, which
    # is not what this half of the test claims to prove).
    assert fake_settings.anthropic_api_key is not None
    assert (
        fake_settings.anthropic_api_key.get_secret_value()
        == _CONFIGURED_KNOWN_VALUE_SECRET
    )

    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    # use_fake_secrets (pytestmark, above) only patches
    # persistence.mutations.get_settings -- the new body-redaction read lives
    # in orchestrator/runner.py and resolves that module's own name.
    monkeypatch.setattr(runner_module, "get_settings", lambda: fake_settings)

    # CR-01: the existence check (fetch_issue + authenticated_login) runs
    # before create_comment, so the ask-path fake must script an issue --
    # even a comment-free one.
    fake_publish = FakeGitHubClient(issue=_scripted_issue())

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_needs_input_result()]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert final is RunStatus.WAITING_HUMAN

    create_calls = [c for c in fake_publish.calls if c[0] == "create_comment"]
    assert len(create_calls) == 1
    body = create_calls[0][1]["body"]

    # ABSENCE: neither planted literal reaches the recorded comment body.
    assert _CONFIGURED_KNOWN_VALUE_SECRET not in body
    assert _PATTERN_ONLY_TOKEN not in body
    # PRESENCE: the redaction marker really fired -- a body that merely lost
    # the secret by accident (e.g. an empty question list) must not pass.
    assert "[redacted:" in body
    # Scrub, don't blank: the non-credential wording survives.
    assert _NON_SECRET_WORDING in body

    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert _CONFIGURED_KNOWN_VALUE_SECRET not in interaction.question
    assert _PATTERN_ONLY_TOKEN not in interaction.question
    assert "[redacted:" in interaction.question

    # The posted comment and the persisted question cannot disagree: the
    # comment body's question section IS the persisted, scrubbed question
    # text (the fixed prefix plus a blank line is the only other content).
    assert interaction.question in body


def test_a_crashed_attempt_resumes_without_a_second_post_or_a_text_mismatch(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
    fake_settings: Settings,
    force_lease_expiry: Callable[[UUID], None],
) -> None:
    """D-05's crash-safety net, catching the wrong fix: if the production
    code redacted only at the ``create_comment`` call and not before the
    ``_find_own_clarification_comment`` existence-check lookup, a resumed
    attempt would build its own fresh, unredacted clarification text, compare
    it against the already-posted *scrubbed* body on GitHub, never match, and
    post a duplicate comment to a real, non-revocable issue. One
    ``FakeGitHubClient`` is used across BOTH drives below, so its ``.calls``
    log is the single, shared source of truth this test checks -- mirroring
    ``tests/db/test_ask_posts_comment.py``'s identical crash-window proof for
    the benign-text case, here with credential-bearing questions."""
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    monkeypatch.setattr(runner_module, "get_settings", lambda: fake_settings)

    real_apply_transition = runner_module.apply_transition

    class _CrashSwitch:
        enabled = True

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

    shared_client = FakeGitHubClient(issue=_scripted_issue())

    with pytest.raises(RuntimeError):
        drive(
            run_id,
            session_factory=real_session_factory,
            registry=fake_worker_registry([_needs_input_result()]),
            repo_root=root,
            github_client_factory=lambda: shared_client,
        )

    # Nothing committed: the crash happened before apply_transition ran.
    assert _the_interaction(engine, run_id) is None
    first_attempt_creates = [c for c in shared_client.calls if c[0] == "create_comment"]
    assert len(first_attempt_creates) == 1, (
        "the crashed attempt must have called create_comment exactly once "
        f"before the simulated crash; calls={shared_client.calls}"
    )
    posted_body = first_attempt_creates[0][1]["body"]
    assert _CONFIGURED_KNOWN_VALUE_SECRET not in posted_body
    assert _PATTERN_ONLY_TOKEN not in posted_body
    assert "[redacted:" in posted_body

    # Resume, exactly as a fresh `dark-factory resume`/`drive()` call after a
    # real process death would: GitHub already has the comment the first
    # attempt actually posted (the SCRUBBED body above -- never recomputed by
    # calling redact() in this test), so script the SAME client's next
    # fetch_issue to return it. The resumed attempt's own existence check
    # must find and adopt it rather than posting a second one.
    switch.enabled = False
    force_lease_expiry(run_id)
    already_posted = GitHubComment(id=4242, author="dark-factory-bot", body=posted_body)
    shared_client._issues.append(_scripted_issue(comments=[already_posted]))

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_needs_input_result()]),
        repo_root=root,
        github_client_factory=lambda: shared_client,
    )
    assert final is RunStatus.WAITING_HUMAN

    interaction = _the_interaction(engine, run_id)
    assert interaction is not None
    assert interaction.clarification_comment_id == 4242

    assert len([c for c in shared_client.calls if c[0] == "create_comment"]) == 1


def test_the_planted_literals_never_reach_an_event_payload_or_role_execution_column(
    config_root_factory: Callable[..., Path],
    real_session_factory: SessionFactory,
    cleanup_runs: list[Any],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    fake_worker_registry: Callable[..., Any],
    fake_settings: Settings,
) -> None:
    """A cheap regression anchor, not a new claim: `run_events.payload` and
    `role_executions.result`/`error` are already scrubbed by
    `apply_transition` (via `persistence.mutations.get_settings`, patched by
    `use_fake_secrets`) regardless of this plan's fix -- this pins that the
    fix did not somehow move the leak from the comment into one of those
    columns instead."""
    root = _write_github_ba_tree(config_root_factory)
    run_id = _start_github_run(monkeypatch, root, real_session_factory)
    cleanup_runs.append(run_id)
    monkeypatch.setattr(runner_module, "get_settings", lambda: fake_settings)

    fake_publish = FakeGitHubClient(issue=_scripted_issue())

    final = drive(
        run_id,
        session_factory=real_session_factory,
        registry=fake_worker_registry([_needs_input_result()]),
        repo_root=root,
        github_client_factory=lambda: fake_publish,
    )
    assert final is RunStatus.WAITING_HUMAN

    blob = _role_execution_and_event_blob(engine, run_id)
    assert _CONFIGURED_KNOWN_VALUE_SECRET not in blob
    assert _PATTERN_ONLY_TOKEN not in blob


# Sanity check that build_clarification_comment (unchanged by this plan) is
# what actually assembles the pre-redaction text these tests reason about.
def test_build_clarification_comment_still_contains_both_planted_literals() -> None:
    """Self-detection: proves the fixture above would actually leak both
    planted literals if `redact()` were never called at all -- without this,
    the ABSENCE assertions in the tests above would be meaningless if
    `build_clarification_comment` itself happened to already strip them."""
    raw = build_clarification_comment(_QUESTIONS)
    assert _CONFIGURED_KNOWN_VALUE_SECRET in raw
    assert _PATTERN_ONLY_TOKEN in raw
