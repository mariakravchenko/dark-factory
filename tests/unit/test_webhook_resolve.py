"""Unit coverage for GIT-06's resolution decision (Phase 10, plan 10-04):
``resolve_issue_comment`` -- the pure ``(payload, run lookup) -> ResolvedAnswer
| UnresolvableComment`` decision in ``dark_factory.webhook.resolve``.

Every payload is built by constructing ``githubkit``'s own typed
``issue_comment`` models via ``tests/support/webhook_events.py`` (not a
hand-rolled dict), so a test breaks loudly if the installed package's payload
shape ever drifts.

``github_pending_interaction`` (the database read) is monkeypatched at its
call site inside ``dark_factory.webhook.resolve`` rather than exercised
against a real database -- this module's own decision logic (which branch
fires, in what order, with what ``IgnoreReason``) is what this file proves,
fast and deterministically, exactly as ``tests/unit/test_clarification_comment.py``
constructs a ``RunState`` directly rather than hitting Postgres. The lookup's
own SQL correctness (JSONB matching, the ``WAITING_HUMAN``/``WAITING``
filters, "no new run is ever created") is proved against real PostgreSQL in
``tests/db/test_webhook_resolves_answer.py`` (Task 3), which additionally
proves this module end to end through the real receiver route. Task 1
carries no PostgreSQL precondition of its own (only "plans 10-01/10-06 have
landed") -- keeping this file genuinely unit-tier (no database, no I/O)
matches both that precondition and the project's own ``unit`` marker
discipline (``pyproject.toml``: "fast, pure-function tests with no database
or I/O").

The pure-rejection cases (non-``created`` action, pull-request thread, empty
body) additionally assert no session attribute is ever touched, via a double
that raises on any access -- the mechanical proof that an obviously
irrelevant delivery costs no database round trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from githubkit.webhooks import parse

import dark_factory.webhook.resolve as resolve_module
from dark_factory.persistence.repositories import GitHubPendingInteraction
from dark_factory.webhook.resolve import (
    IgnoreReason,
    ResolvedAnswer,
    UnresolvableComment,
    resolve_issue_comment,
)
from tests.support.webhook_events import build_issue_comment_payload

pytestmark = pytest.mark.unit

_OWNER = "acme"
_REPO = "widgets"
_ISSUE_NUMBER = 5
_TOKEN_LOGIN = "dark-factory-bot"


class _ExplodingSession:
    """A ``session`` double that raises on any attribute access -- proves a
    pure-rejection branch never touches the database."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"resolve_issue_comment touched session.{name} before a "
            "pure-rejection branch should have returned"
        )


def _event(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "owner": _OWNER,
        "repo": _REPO,
        "issue_number": _ISSUE_NUMBER,
    }
    kwargs.update(overrides)
    body = build_issue_comment_payload(**kwargs)
    return parse("issue_comment", body)


def _pending(clarification_comment_id: int | None = None) -> GitHubPendingInteraction:
    return GitHubPendingInteraction(
        run_id=uuid4(),
        interaction_id=uuid4(),
        role_execution_id=uuid4(),
        clarification_comment_id=clarification_comment_id,
    )


def _stub_lookup(
    monkeypatch: pytest.MonkeyPatch, result: GitHubPendingInteraction | None
) -> None:
    monkeypatch.setattr(
        resolve_module, "github_pending_interaction", lambda *a, **k: result
    )


def _login(value: str = _TOKEN_LOGIN) -> Any:
    return lambda: value


# --------------------------------------------------------------------------- #
# Pure-rejection branches -- no session touch
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("action", ["deleted", "edited"])
def test_non_created_action_is_rejected_with_no_session_touch(action: str) -> None:
    event = _event(action=action)
    outcome = resolve_issue_comment(
        event, session=_ExplodingSession(), authenticated_login=_login()
    )
    assert outcome == UnresolvableComment(reason=IgnoreReason.NOT_CREATED_ACTION)


def test_pull_request_thread_is_rejected_with_no_session_touch() -> None:
    event = _event(is_pull_request=True)
    outcome = resolve_issue_comment(
        event, session=_ExplodingSession(), authenticated_login=_login()
    )
    assert outcome == UnresolvableComment(reason=IgnoreReason.PULL_REQUEST_THREAD)


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
def test_empty_or_whitespace_body_is_rejected_with_no_session_touch(body: str) -> None:
    event = _event(comment_body=body)
    outcome = resolve_issue_comment(
        event, session=_ExplodingSession(), authenticated_login=_login()
    )
    assert outcome == UnresolvableComment(reason=IgnoreReason.EMPTY_BODY)


# --------------------------------------------------------------------------- #
# Lookup-dependent branches -- github_pending_interaction stubbed
# --------------------------------------------------------------------------- #


def test_no_pending_interaction_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_lookup(monkeypatch, None)
    event = _event()
    outcome = resolve_issue_comment(
        event, session=object(), authenticated_login=_login()
    )
    assert outcome == UnresolvableComment(reason=IgnoreReason.NO_PENDING_INTERACTION)


def test_self_authored_by_comment_id_is_ignored_even_with_a_foreign_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = _pending(clarification_comment_id=999)
    _stub_lookup(monkeypatch, pending)
    event = _event(comment_id=999, comment_user_login="a-third-party")
    outcome = resolve_issue_comment(
        event, session=object(), authenticated_login=_login()
    )
    assert outcome == UnresolvableComment(reason=IgnoreReason.SELF_AUTHORED)


def test_self_authored_by_login_is_ignored_even_with_a_foreign_comment_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = _pending(clarification_comment_id=1)
    _stub_lookup(monkeypatch, pending)
    event = _event(comment_id=2, comment_user_login=_TOKEN_LOGIN)
    outcome = resolve_issue_comment(
        event, session=object(), authenticated_login=_login()
    )
    assert outcome == UnresolvableComment(reason=IgnoreReason.SELF_AUTHORED)


def test_a_third_party_reply_resolves_to_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = _pending(clarification_comment_id=1)
    _stub_lookup(monkeypatch, pending)
    event = _event(comment_id=2, comment_body="use staging", comment_user_login="a-human")
    outcome = resolve_issue_comment(
        event, session=object(), authenticated_login=_login()
    )
    assert outcome == ResolvedAnswer(
        run_id=pending.run_id,
        interaction_id=pending.interaction_id,
        github_comment_id=2,
        answer="use staging",
    )


def test_answer_preserves_emoji_and_markdown_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = _pending()
    _stub_lookup(monkeypatch, pending)
    body = "Use **staging** 🚀\n- primary db\n- staging cluster"
    event = _event(comment_id=3, comment_body=body, comment_user_login="a-human")
    outcome = resolve_issue_comment(
        event, session=object(), authenticated_login=_login()
    )
    assert isinstance(outcome, ResolvedAnswer)
    assert outcome.answer == body


def test_no_pending_interaction_for_a_comment_with_no_declared_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ghost/deleted commenter (``comment.user`` is ``None``) is never
    treated as self-authored -- only an explicit login match is."""
    pending = _pending(clarification_comment_id=1)
    _stub_lookup(monkeypatch, pending)
    event = _event(comment_id=2, comment_body="an answer", comment_user_login=None)
    outcome = resolve_issue_comment(
        event, session=object(), authenticated_login=_login()
    )
    assert outcome == ResolvedAnswer(
        run_id=pending.run_id,
        interaction_id=pending.interaction_id,
        github_comment_id=2,
        answer="an answer",
    )


def test_lookup_is_called_with_owner_repo_and_issue_number_read_off_the_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _capture(
        session: Any, *, owner: str, repo: str, issue_number: int
    ) -> GitHubPendingInteraction | None:
        captured.update(owner=owner, repo=repo, issue_number=issue_number)
        return None

    monkeypatch.setattr(resolve_module, "github_pending_interaction", _capture)
    event = _event(owner="foo-org", repo="bar-repo", issue_number=99)
    resolve_issue_comment(event, session=object(), authenticated_login=_login())
    assert captured == {"owner": "foo-org", "repo": "bar-repo", "issue_number": 99}


def test_every_documented_input_returns_a_typed_result_never_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_lookup(monkeypatch, None)
    outcomes = [
        resolve_issue_comment(
            _event(action="deleted"), session=_ExplodingSession(), authenticated_login=_login()
        ),
        resolve_issue_comment(
            _event(is_pull_request=True),
            session=_ExplodingSession(),
            authenticated_login=_login(),
        ),
        resolve_issue_comment(
            _event(comment_body="  "),
            session=_ExplodingSession(),
            authenticated_login=_login(),
        ),
        resolve_issue_comment(_event(), session=object(), authenticated_login=_login()),
    ]
    for outcome in outcomes:
        assert isinstance(outcome, (ResolvedAnswer, UnresolvableComment))


def test_webhook_package_never_imports_advance_or_drive() -> None:
    """The mechanical shape of the acceptance criterion "no reference to
    ``advance``/``drive``": an AST walk over every ``import`` /
    ``from ... import`` statement under ``src/dark_factory/webhook/``, not a
    naive substring search -- this package's own docstrings *discuss* the
    prohibition by name (the plan's own instruction), so a text grep would
    trip on its own documentation. Plan 10-05 adds the full mechanical
    import-closure guard for the whole ``advance``/``drive`` boundary; this
    is this plan's own narrower proof that the webhook package itself
    imports neither name."""
    import ast

    root = Path(__file__).resolve().parents[2] / "src" / "dark_factory" / "webhook"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = {alias.name for alias in node.names}
                assert "advance" not in names, f"{path} imports 'advance'"
                assert "drive" not in names, f"{path} imports 'drive'"
            elif isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
                assert not any("runner" in n for n in names), (
                    f"{path} imports the orchestrator runner module directly"
                )
