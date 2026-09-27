"""Unit coverage for GIT-06's receiver route (Phase 10, plan 10-04):
``dark_factory.webhook.app``'s one POST route -- verify, parse, resolve,
``submit_answer`` and stop.

Driven through Starlette's own in-process ``TestClient`` (built on ``httpx``,
already pulled in transitively by ``githubkit``, so this needs no extra test
dependency). Every fixture body is signed with the exact
``githubkit.webhooks.sign``/``verify`` construction GitHub documents
(``tests/support/webhook_events.py``), so the valid cases are genuinely
valid and the invalid case is a genuine mismatch, not a hand-rolled stand-in.

``resolve_issue_comment`` and ``submit_answer`` are monkeypatched at their
call sites inside ``dark_factory.webhook.app`` (mirrors this codebase's
``loaders.GitHubClient`` monkeypatch idiom) -- this file proves the route's
own sequencing (verify-before-anything, status-code-by-retryability, no
detail echoed), not ``resolve_issue_comment``'s decision logic (covered by
``tests/unit/test_webhook_resolve.py``) or a real database (covered by
``tests/db/test_webhook_resolves_answer.py``). A ``session_factory`` double
that raises on call proves the "no session opened" claims for every
rejection path.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

import dark_factory.webhook.app as app_module
from dark_factory.orchestrator.answers import NoPendingInteraction, NotWaitingForHuman
from dark_factory.orchestrator.lease import LeaseNotAcquired
from dark_factory.webhook.app import build_app
from dark_factory.webhook.resolve import (
    IgnoreReason,
    ResolvedAnswer,
    UnresolvableComment,
)
from tests.support.log_sink import real_log_sink
from tests.support.webhook_events import build_issue_comment_payload, sign_payload

pytestmark = pytest.mark.unit

_SECRET = "whsec_topsecretwebhook0123456789"
_PATH = "/webhooks/github"
_STUB_LOGIN = "dark-factory-bot"


class _RaisingSessionFactory:
    """A ``session_factory()`` double that raises on call -- proves a
    rejection path never opens a database session."""

    def __call__(self) -> Any:
        raise AssertionError(
            "session_factory() was called on a path that must not open a session"
        )


class _DummySession:
    def close(self) -> None:
        return None


class _RecordingSubmitAnswer:
    """A ``submit_answer`` double recording every call, optionally raising a
    scripted exception on every call."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._raises = raises

    def __call__(
        self,
        run_id: Any,
        answer: str,
        *,
        session_factory: Any,
        github_comment_id: int | None = None,
    ) -> None:
        self.calls.append(
            {"run_id": run_id, "answer": answer, "github_comment_id": github_comment_id}
        )
        if self._raises is not None:
            raise self._raises


class _FakeSecretStr:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _FakeSettings:
    def __init__(
        self,
        secret: str | None,
        *,
        github_token: str | None = "ghp_fake0000000000000000",
    ) -> None:
        self.github_webhook_secret = (
            _FakeSecretStr(secret) if secret is not None else None
        )
        # WR-02 (10-REVIEW.md): defaults to a configured value so every
        # pre-existing test -- none of which cared about github_token -- is
        # unaffected; only the new WR-02 tests below override it.
        self.github_token = (
            _FakeSecretStr(github_token) if github_token is not None else None
        )


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secret: str | None = _SECRET,
    session_factory: Any = None,
    resolve_result: ResolvedAnswer | UnresolvableComment | None = None,
    resolve_raises: Exception | None = None,
    submit_answer_double: Any = None,
) -> TestClient:
    factory = (
        session_factory if session_factory is not None else _RaisingSessionFactory()
    )
    app = build_app(
        session_factory=factory,
        settings_factory=lambda: _FakeSettings(secret),
        authenticated_login=lambda: _STUB_LOGIN,
    )
    if resolve_result is not None:
        monkeypatch.setattr(
            app_module, "resolve_issue_comment", lambda *a, **k: resolve_result
        )
    if resolve_raises is not None:

        def _raise(*_args: Any, **_kwargs: Any) -> Any:
            raise resolve_raises

        monkeypatch.setattr(app_module, "resolve_issue_comment", _raise)
    if submit_answer_double is not None:
        monkeypatch.setattr(app_module, "submit_answer", submit_answer_double)
    return TestClient(app)


def _post(
    client: TestClient,
    body: bytes,
    *,
    signature: str | None,
    event: str = "issue_comment",
) -> Any:
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post(_PATH, content=body, headers=headers)


# --------------------------------------------------------------------------- #
# Signature verification -- before anything else
# --------------------------------------------------------------------------- #


def test_missing_signature_header_is_rejected_with_no_session_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(monkeypatch)
    body = build_issue_comment_payload()
    response = _post(client, body, signature=None)
    assert response.status_code == 401


def test_mismatched_signature_is_rejected_with_no_session_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(monkeypatch)
    body = build_issue_comment_payload()
    wrong_signature = sign_payload("a-completely-different-secret", body)
    response = _post(client, body, signature=wrong_signature)
    assert response.status_code == 401


def test_body_altered_after_signing_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(monkeypatch)
    body = build_issue_comment_payload(comment_body="original")
    signature = sign_payload(_SECRET, body)
    tampered = body.replace(b"original", b"tampered!")
    assert tampered != body
    response = _post(client, tampered, signature=signature)
    assert response.status_code == 401


def test_401_body_leaks_neither_signature_nor_secret_nor_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(monkeypatch)
    body = build_issue_comment_payload(
        comment_body="a very particular secret-shaped phrase"
    )
    wrong_signature = sign_payload("another-secret-entirely", body)
    response = _post(client, body, signature=wrong_signature)
    assert response.status_code == 401
    text = response.text
    assert wrong_signature not in text
    assert _SECRET not in text
    assert "a very particular secret-shaped phrase" not in text


def test_unset_secret_refuses_every_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, secret=None)
    body = build_issue_comment_payload()
    # Even a signature computed with what would otherwise be the right
    # secret is refused -- fail closed, never "skip verification".
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Event filtering and parse failures
# --------------------------------------------------------------------------- #


def test_non_issue_comment_event_is_acknowledged_with_no_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(monkeypatch)
    body = build_issue_comment_payload()
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature, event="ping")
    assert response.status_code == 200


def test_unparseable_body_returns_bad_request_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(monkeypatch)
    body = b'{"not": "a valid issue_comment payload"}'
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Resolution outcomes -> submit_answer / status code
# --------------------------------------------------------------------------- #


def test_a_resolvable_delivery_calls_submit_answer_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    interaction_id = uuid4()
    resolved = ResolvedAnswer(
        run_id=run_id,
        interaction_id=interaction_id,
        github_comment_id=555,
        answer="use staging",
    )
    recorder = _RecordingSubmitAnswer()
    client = _make_client(
        monkeypatch,
        session_factory=lambda: _DummySession(),
        resolve_result=resolved,
        submit_answer_double=recorder,
    )
    body = build_issue_comment_payload(comment_id=555, comment_body="use staging")
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 200
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["run_id"] == run_id
    assert call["answer"] == "use staging"
    assert call["github_comment_id"] == 555


def test_an_unresolvable_delivery_calls_submit_answer_zero_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _RecordingSubmitAnswer()
    client = _make_client(
        monkeypatch,
        session_factory=lambda: _DummySession(),
        resolve_result=UnresolvableComment(reason=IgnoreReason.NO_PENDING_INTERACTION),
        submit_answer_double=recorder,
    )
    body = build_issue_comment_payload()
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 200
    assert recorder.calls == []


@pytest.mark.parametrize("exc_cls", [NotWaitingForHuman, NoPendingInteraction])
def test_a_race_lost_to_another_process_is_acknowledged_not_retried(
    monkeypatch: pytest.MonkeyPatch, exc_cls: type[Exception]
) -> None:
    resolved = ResolvedAnswer(
        run_id=uuid4(), interaction_id=uuid4(), github_comment_id=1, answer="x"
    )
    recorder = _RecordingSubmitAnswer(raises=exc_cls("already handled"))
    client = _make_client(
        monkeypatch,
        session_factory=lambda: _DummySession(),
        resolve_result=resolved,
        submit_answer_double=recorder,
    )
    body = build_issue_comment_payload()
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 200


def test_a_lost_lease_returns_a_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = ResolvedAnswer(
        run_id=uuid4(), interaction_id=uuid4(), github_comment_id=1, answer="x"
    )
    recorder = _RecordingSubmitAnswer(raises=LeaseNotAcquired(uuid4(), "BA"))
    client = _make_client(
        monkeypatch,
        session_factory=lambda: _DummySession(),
        resolve_result=resolved,
        submit_answer_double=recorder,
    )
    body = build_issue_comment_payload()
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 503


def test_an_unexpected_exception_returns_a_generic_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = ResolvedAnswer(
        run_id=uuid4(), interaction_id=uuid4(), github_comment_id=1, answer="x"
    )
    recorder = _RecordingSubmitAnswer(raises=RuntimeError("boom"))
    client = _make_client(
        monkeypatch,
        session_factory=lambda: _DummySession(),
        resolve_result=resolved,
        submit_answer_double=recorder,
    )
    body = build_issue_comment_payload()
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 500
    assert "boom" not in response.text


def test_an_unexpected_exception_from_resolve_returns_a_generic_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-02 (10-REVIEW.md): before this fix, an exception raised from
    ``resolve_issue_comment`` (most plausibly ``MissingGitHubCredentialError``
    from ``_login_provider()``'s own eager ``GitHubClient`` construction when
    ``GITHUB_TOKEN`` is unset) propagated unhandled -- bypassing this
    module's own "log + fixed 500" contract entirely. ``submit_answer`` is
    never reached: proven here with no ``submit_answer_double`` supplied at
    all, so a call would raise ``AttributeError`` from ``monkeypatch``'s own
    absence rather than silently succeed."""
    client = _make_client(
        monkeypatch,
        session_factory=lambda: _DummySession(),
        resolve_raises=RuntimeError("boom from resolve"),
    )
    body = build_issue_comment_payload()
    signature = sign_payload(_SECRET, body)
    response = _post(client, body, signature=signature)
    assert response.status_code == 500
    assert "boom from resolve" not in response.text


# --------------------------------------------------------------------------- #
# WR-02: startup validation logs loudly, never raises
# --------------------------------------------------------------------------- #


def test_missing_github_token_logs_loudly_at_construction() -> None:
    """WR-02 (10-REVIEW.md): on the production path (no injected
    ``authenticated_login``), ``build_app()`` logs a loud ``ERROR`` at
    construction time when ``GITHUB_TOKEN`` is unset -- rather than only
    discovering the gap on the first inbound request."""
    with real_log_sink() as buffer:
        build_app(
            session_factory=_RaisingSessionFactory(),
            settings_factory=lambda: _FakeSettings(_SECRET, github_token=None),
        )
    output = buffer.getvalue()
    assert "webhook.build_app.missing_github_token" in output


def test_missing_github_webhook_secret_logs_loudly_at_construction() -> None:
    with real_log_sink() as buffer:
        build_app(
            session_factory=_RaisingSessionFactory(),
            settings_factory=lambda: _FakeSettings(None),
        )
    output = buffer.getvalue()
    assert "webhook.build_app.missing_github_webhook_secret" in output


def test_fully_configured_settings_log_no_startup_warning() -> None:
    with real_log_sink() as buffer:
        build_app(
            session_factory=_RaisingSessionFactory(),
            settings_factory=lambda: _FakeSettings(_SECRET),
        )
    output = buffer.getvalue()
    assert "webhook.build_app.missing" not in output


def test_injected_authenticated_login_skips_the_startup_check() -> None:
    """The unit tier's own injection seam (``authenticated_login=``) must
    never be forced to also configure ``GITHUB_TOKEN`` -- the startup check
    only runs on the production path."""
    with real_log_sink() as buffer:
        build_app(
            session_factory=_RaisingSessionFactory(),
            settings_factory=lambda: _FakeSettings(_SECRET, github_token=None),
            authenticated_login=lambda: _STUB_LOGIN,
        )
    output = buffer.getvalue()
    assert "webhook.build_app.missing" not in output
