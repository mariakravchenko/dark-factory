"""Build real ``githubkit`` ``issue_comment`` webhook payloads for tests
(Phase 10, plan 10-04).

Shared by ``tests/unit/test_webhook_resolve.py``, ``tests/unit/test_webhook_signature.py``
and ``tests/db/test_webhook_resolves_answer.py``. Every fixture is built by
filling in ``githubkit``'s own generated pydantic models (via ``polyfactory``,
already a dev dependency) rather than a hand-rolled dict -- the plan's own
instruction -- so a test breaks loudly if the installed package's payload
shape ever drifts from what this module assumes. ``githubkit.webhooks.parse``
/``verify``/``sign`` are the exact same functions the production receiver
calls, so a fixture that round-trips through ``parse`` here is proof the
receiver can parse it too.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from githubkit.webhooks import sign
from githubkit_schemas.v2026_03_10.models.group_0704 import WebhookIssueCommentCreated
from githubkit_schemas.v2026_03_10.models.group_0716 import WebhookIssueCommentDeleted
from githubkit_schemas.v2026_03_10.models.group_0727 import WebhookIssueCommentEdited
from polyfactory.factories.pydantic_factory import ModelFactory

__all__ = ["build_issue_comment_payload", "sign_payload"]

_ACTION_MODELS: Mapping[str, type[Any]] = {
    "created": WebhookIssueCommentCreated,
    "deleted": WebhookIssueCommentDeleted,
    "edited": WebhookIssueCommentEdited,
}

# githubkit's own JSON encoding of an unset optional field -- real GitHub
# payloads represent "this field was not supplied" by omitting the key
# entirely, never by sending this literal string, so every fixture built here
# scrubs it back out before serialising.
_UNSET_SENTINEL = "<UNSET>"


def _scrub_unset(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _scrub_unset(v) for k, v in value.items() if v != _UNSET_SENTINEL}
    if isinstance(value, list):
        return [_scrub_unset(v) for v in value]
    return value


def build_issue_comment_payload(
    *,
    action: str = "created",
    comment_id: int = 1001,
    comment_body: str = "an answer",
    comment_user_login: str | None = "a-human",
    issue_number: int = 5,
    is_pull_request: bool = False,
    owner: str = "acme",
    repo: str = "widgets",
) -> bytes:
    """A signable, parseable raw JSON body for one ``issue_comment`` webhook
    delivery.

    Built from ``githubkit``'s own typed model for ``action`` (``"created"``
    / ``"deleted"`` / ``"edited"``), filled with realistic-shaped random data
    via ``polyfactory`` and then overridden at exactly the fields a test
    cares about, so an installed-package field-shape change breaks this
    builder loudly (a ``KeyError``/``AttributeError`` here) rather than
    silently producing a payload the real receiver could never see.

    ``comment_user_login=None`` omits ``comment.user`` entirely (GitHub
    reports a deleted/ghost commenter this way). ``is_pull_request=True``
    fills ``issue.pull_request`` with a minimal object, simulating a
    pull-request-thread comment; the default omits the key entirely, exactly
    as a genuine issue comment's payload does.
    """
    model = _ACTION_MODELS[action]

    class _Factory(ModelFactory):  # type: ignore[type-arg]
        __model__ = model
        __allow_none_optionals__ = 0.0

    instance = _Factory.build()
    payload: dict[str, Any] = _scrub_unset(instance.model_dump(mode="json", by_alias=True))

    payload["action"] = action
    payload["comment"]["id"] = comment_id
    payload["comment"]["body"] = comment_body
    if comment_user_login is None:
        # ``comment.user`` is required-but-nullable (a JSON ``null``, not an
        # absent key) -- this is how GitHub reports a deleted/ghost commenter.
        payload["comment"]["user"] = None
    else:
        payload["comment"]["user"] = {
            **(payload["comment"].get("user") or {}),
            "login": comment_user_login,
        }
    payload["issue"]["number"] = issue_number
    if is_pull_request:
        payload["issue"]["pull_request"] = {}
    else:
        payload["issue"].pop("pull_request", None)
    payload["repository"]["owner"]["login"] = owner
    payload["repository"]["name"] = repo

    return json.dumps(payload).encode("utf-8")


def sign_payload(secret: str, body: bytes) -> str:
    """The ``X-Hub-Signature-256`` value GitHub would send for ``body``,
    via the same ``githubkit.webhooks.sign`` 10-RESEARCH.md cites as the
    non-hand-rolled construction (mirrors ``verify``'s own provenance)."""
    return sign(secret, body)
