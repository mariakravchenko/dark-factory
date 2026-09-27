"""The receiver's single POST route -- verify, parse, resolve, submit_answer
and stop (GIT-06, D-01/D-02).

**How this process is run.** ``dark_factory.webhook.app:app`` is the ASGI
application object an ASGI server points at, e.g.::

    uv sync --extra webhook
    uv run uvicorn dark_factory.webhook.app:app --host 0.0.0.0 --port 8000

It needs ``DATABASE_URL``, ``DATABASE_URL_DIRECT`` (``Settings`` requires
both -- the direct URL is unused by this process but is still a required
field), ``GITHUB_TOKEN`` (to construct the ``GitHubClient`` that reads the
token's own identity for the self-comment filter) and
``GITHUB_WEBHOOK_SECRET`` (the shared secret GitHub signs every delivery
with) in the environment / ``.env``. A GitHub repository webhook, configured
per this plan's ``user_setup``, must point its Payload URL at this process's
``/webhooks/github`` route with content type ``application/json`` and only
the "Issue comments" event subscribed.

**The route body is a strict sequence, and its ordering is the security
control** (T-10-18):

1. Read the raw request body as bytes -- never a parsed-then-re-serialized
   form, because the signature covers the exact bytes GitHub sent.
2. Verify, before anything else, via ``githubkit.webhooks.verify`` (never a
   hand-rolled HMAC comparison -- 10-RESEARCH.md "Don't Hand-Roll"). A
   missing signature header, a verification failure, or an unset
   ``github_webhook_secret`` (fail closed) all return a fixed, non-echoing
   401 with no database session opened and no parse attempted.
3. Parse with ``githubkit.webhooks.parse``, keyed on ``X-GitHub-Event``. A
   non-``issue_comment`` event is acknowledged (200) and dropped without
   further work. A body that fails the typed parse returns a fixed 400 --
   the pydantic validation failure never travels back to the caller.
4. Resolve with :func:`~dark_factory.webhook.resolve.resolve_issue_comment`,
   opening one short-lived session for that call.
5. Act (:func:`~dark_factory.orchestrator.answers.submit_answer`, in-process,
   directly -- D-02) or acknowledge (an ``UnresolvableComment`` logs its
   ``IgnoreReason`` server-side and returns 200 with no detail in the
   response, so the endpoint cannot become an existence oracle -- T-10-22).
6. Map the outcome to a status code by retryability: ``NotWaitingForHuman``/
   ``NoPendingInteraction`` mean another process already handled it or the
   run moved on -- 200, a redelivery will never do better.
   ``LeaseNotAcquired`` means right now is a bad moment -- a retryable 503.
   Any unexpected exception is logged with the exception and returns a fixed
   500, never echoed.

This module -- and everything it imports -- must never reference ``advance``
or ``drive``: the receiver's only mutation is ``submit_answer`` (D-02, T-10-21).
It performs one short synchronous database transaction per request
(``session_factory``/``submit_answer`` are the orchestrator's own synchronous
primitives) dispatched off the event loop via ``run_in_threadpool``, and has
no concurrency story worth an async rewrite of the orchestrator core.
"""

from __future__ import annotations

from collections.abc import Callable

import structlog
from githubkit.webhooks import parse, verify
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from dark_factory.config.settings import Settings, get_settings
from dark_factory.github.client import GitHubClient
from dark_factory.orchestrator.answers import (
    NoPendingInteraction,
    NotWaitingForHuman,
    submit_answer,
)
from dark_factory.orchestrator.lease import LeaseNotAcquired
from dark_factory.persistence.engine import new_session
from dark_factory.webhook.resolve import ResolvedAnswer, resolve_issue_comment

__all__ = ["app", "build_app"]

_log = structlog.get_logger(__name__)

_SIGNATURE_HEADER = "X-Hub-Signature-256"
_EVENT_HEADER = "X-GitHub-Event"
_ISSUE_COMMENT_EVENT = "issue_comment"

# Fixed, non-echoing response bodies (T-10-22): never the received/computed
# signature, the secret, a payload fragment, a validation-error detail, a run
# id or an interaction id.
_REJECTED = PlainTextResponse("rejected", status_code=401)
_BAD_REQUEST = PlainTextResponse("bad request", status_code=400)
_OK = PlainTextResponse("ok", status_code=200)
_RETRY_LATER = PlainTextResponse("try again", status_code=503)
_SERVER_ERROR = PlainTextResponse("server error", status_code=500)


def build_app(
    *,
    session_factory: Callable[[], Session] = new_session,
    settings_factory: Callable[[], Settings] = get_settings,
    authenticated_login: Callable[[], str] | None = None,
) -> Starlette:
    """Build the receiver's one POST route.

    The three keyword parameters are the test-injection seam (mirrors this
    codebase's ``session_factory``/``github_client_factory`` idiom
    elsewhere): the production default (``app`` below, ``build_app()`` with
    no arguments) reads real settings, opens real sessions and lazily
    constructs one real :class:`GitHubClient` per built app instance (never
    per request) via ``GitHubClient.from_settings(settings_factory())``.

    ``authenticated_login``, when supplied, replaces that lazy
    :class:`GitHubClient` construction entirely -- the unit tier injects a
    stub callable and never constructs a real client or needs
    ``GITHUB_TOKEN``.

    WR-02 (10-REVIEW.md): on the production path (``authenticated_login`` is
    ``None``), logs a loud ``ERROR`` -- but does not raise -- when
    ``GITHUB_TOKEN`` and/or ``GITHUB_WEBHOOK_SECRET`` are unconfigured, so a
    misconfigured deployment is visible in this process's own startup logs
    rather than only discoverable per-request (and, before CR-02, not even
    logged then). Deliberately does not raise: ``GITHUB_TOKEN`` stays
    legitimately unset in environments that never run this receiver
    (10-02-SUMMARY.md), so refusing to construct the Starlette app at all
    would be a bigger behaviour change than this fix is scoped to make.
    """
    # A one-element list, not a bare ``nonlocal``-mutated variable: closed
    # over by ``_login_provider`` below and scoped to *this* ``build_app()``
    # call, so two independently built apps (e.g. two tests) never share a
    # cached client -- the exact reason ``GitHubClient.authenticated_login``
    # itself caches on the instance rather than a module global.
    _client_cache: list[GitHubClient] = []

    if authenticated_login is None:
        _startup_settings = settings_factory()
        if _startup_settings.github_token is None:
            _log.error(
                "webhook.build_app.missing_github_token",
                detail=(
                    "GITHUB_TOKEN is not configured -- every inbound "
                    "issue_comment delivery will fail once this process "
                    "tries to construct a GitHubClient"
                ),
            )
        if _startup_settings.github_webhook_secret is None:
            _log.error(
                "webhook.build_app.missing_github_webhook_secret",
                detail=(
                    "GITHUB_WEBHOOK_SECRET is not configured -- every "
                    "inbound delivery will be rejected with 401"
                ),
            )

    def _login_provider() -> Callable[[], str]:
        if authenticated_login is not None:
            return authenticated_login
        if not _client_cache:
            _client_cache.append(GitHubClient.from_settings(settings_factory()))
        return _client_cache[0].authenticated_login

    def _resolve_and_act(raw_body: bytes) -> Response:
        """Everything after signature verification. Runs off the event loop
        via ``run_in_threadpool`` -- every call in here is a blocking
        SQLAlchemy / ``orchestrator.answers`` call."""
        try:
            # A literal string, not the ``_ISSUE_COMMENT_EVENT`` constant used
            # everywhere else in this module: ``parse``'s typed overloads key
            # on ``Literal["issue_comment"]`` to return the narrow
            # ``IssueCommentEvent`` union ``resolve_issue_comment`` expects --
            # a module-level ``str`` constant loses that literal type.
            event = parse("issue_comment", raw_body)
        except ValidationError:
            return _BAD_REQUEST

        session = session_factory()
        try:
            outcome = resolve_issue_comment(
                event, session=session, authenticated_login=_login_provider()
            )
        except Exception:
            # CR-02 (10-REVIEW.md): this used to be only a ``finally`` --
            # any exception raised while resolving (including
            # ``_login_provider()``'s own eager ``GitHubClient`` construction,
            # which raises ``MissingGitHubCredentialError`` whenever
            # ``GITHUB_TOKEN`` is unset) propagated unhandled, bypassing this
            # module's own docstring promise ("any unexpected exception is
            # logged ... and returns a fixed 500, never echoed") and this
            # project's "durability and observability are the same
            # requirement" posture. Mirrors the ``except Exception`` arm
            # below, verbatim in shape, for the resolve-time half of this
            # route.
            _log.exception("webhook.issue_comment.unexpected_error")
            return _SERVER_ERROR
        finally:
            session.close()

        if not isinstance(outcome, ResolvedAnswer):
            _log.info("webhook.issue_comment.ignored", reason=outcome.reason.value)
            return _OK

        try:
            submit_answer(
                outcome.run_id,
                outcome.answer,
                session_factory=session_factory,
                github_comment_id=outcome.github_comment_id,
            )
        except (NotWaitingForHuman, NoPendingInteraction) as exc:
            _log.info(
                "webhook.issue_comment.already_resolved",
                run_id=str(outcome.run_id),
                reason=type(exc).__name__,
            )
            return _OK
        except LeaseNotAcquired:
            return _RETRY_LATER
        except Exception:
            _log.exception(
                "webhook.issue_comment.unexpected_error", run_id=str(outcome.run_id)
            )
            return _SERVER_ERROR
        return _OK

    async def _handle_issue_comment(request: Request) -> Response:
        raw_body = await request.body()
        signature = request.headers.get(_SIGNATURE_HEADER)
        secret = settings_factory().github_webhook_secret
        if secret is None or not signature:
            return _REJECTED
        if not verify(secret.get_secret_value(), raw_body, signature):
            return _REJECTED

        event_name = request.headers.get(_EVENT_HEADER, "")
        if event_name != _ISSUE_COMMENT_EVENT:
            return _OK

        return await run_in_threadpool(_resolve_and_act, raw_body)

    return Starlette(
        routes=[Route("/webhooks/github", _handle_issue_comment, methods=["POST"])]
    )


app = build_app()
