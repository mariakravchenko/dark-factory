"""``dark_factory.webhook`` -- the inbound half of the resume loop (GIT-06).

This package is a *separate deployable* (D-01): it shares only the database
with the orchestrator core, is run as its own ASGI process (``uvicorn
dark_factory.webhook.app:build_app --factory``, see ``app.py``'s module
docstring for the exact command and required environment), and lives behind the
optional ``webhook`` dependency extra (``uv sync --extra webhook``) --
uninstalling that extra must leave the orchestrator core fully functional, mirroring the
``mcp`` extra's isolation rule (TOOL-05, D-13).

Its only mutation is a call to :func:`dark_factory.orchestrator.answers.submit_answer`
(D-02). It must never import or call ``advance`` or ``drive`` -- running pipeline
work at an unauthenticated network edge is precisely what this boundary exists
to prevent: a request to this receiver can never hold a lease for the
duration of a role, spawn a worker subprocess or consume agent budget. Plan
10-05 turns that sentence into a mechanical import-closure guard; until then,
``src/dark_factory/webhook/`` containing no reference to ``advance``/``drive``
is this plan's own acceptance criterion.

Error hierarchy:

* :class:`WebhookError` -- the base class for every failure this package
  raises.
* :class:`InvalidSignature` -- raised when a delivery's ``X-Hub-Signature-256``
  does not verify (reserved for internal use; the route itself returns a
  fixed 401 response rather than letting this propagate, so a non-echoing
  rejection is the only thing an unauthenticated caller ever observes).
"""

from __future__ import annotations

__all__ = ["InvalidSignature", "WebhookError"]


class WebhookError(RuntimeError):
    """Base class for every ``dark_factory.webhook`` failure."""


class InvalidSignature(WebhookError):
    """A delivery's ``X-Hub-Signature-256`` did not verify against the
    configured ``Settings.github_webhook_secret``."""
