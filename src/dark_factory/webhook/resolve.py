"""Which comment answers which run -- the resolution decision (GIT-06).

``resolve_issue_comment`` is written as a pure function so every branch is
testable without a server, a socket or a signature: it takes a database
session and an already-verified, already-parsed typed event and returns
exactly one of :class:`ResolvedAnswer` / :class:`UnresolvableComment` -- never
``None``, never a raised exception for an ordinary unresolvable delivery.

This module performs no write of any kind and constructs no ORM row --
``tests/unit/test_single_mutation_path.py`` (a source-tree AST walk) does not
need to know this module exists, because it never constructs a
``RunEvent``/``RoleExecution``/``HumanInteraction`` and never assigns a
``.status`` attribute; the only database touch here is the single read in
:func:`~dark_factory.persistence.repositories.github_pending_interaction`.

**Self-comment filter (10-RESEARCH.md Pitfall 2, Assumption A4).** GitHub
fires ``issue_comment`` for *every* new comment on an issue, including the one
Dark Factory itself just posted when it asked its question. Two independent
checks guard against a naive resolver instantly answering its own question
with the question's own text: the inbound comment's id against the pending
interaction's ``clarification_comment_id``, and the inbound commenter's login
against the token's own identity. The commenter's login is read off
``comment.user.login`` on githubkit's own typed model (confirmed against the
installed ``githubkit`` 0.16.1 / ``githubkit-schemas`` 26.9.21 package by
introspection before this module was written) -- the comment's own author,
which is the more directly correct source than ``sender.login`` (the actor
who triggered the webhook delivery, not necessarily who authored the
comment). Both checks are independent and both are always evaluated: neither
filter alone should be the sole thing standing between Dark Factory and
self-answering its own question.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from uuid import UUID

from githubkit.utils import UNSET
from githubkit_schemas.latest.webhooks import IssueCommentEvent
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from dark_factory.persistence.repositories import github_pending_interaction

__all__ = [
    "IgnoreReason",
    "ResolvedAnswer",
    "UnresolvableComment",
    "resolve_issue_comment",
]


class IgnoreReason(StrEnum):
    """Every genuine reason an inbound delivery does not resolve to an
    answer. One member per outcome, not free text, so a test can assert
    *why* a delivery was ignored and an operator can read the receiver's
    logs later without re-deriving the reason from message text."""

    NOT_CREATED_ACTION = "not_created_action"
    PULL_REQUEST_THREAD = "pull_request_thread"
    EMPTY_BODY = "empty_body"
    NO_PENDING_INTERACTION = "no_pending_interaction"
    SELF_AUTHORED = "self_authored"


class ResolvedAnswer(BaseModel):
    """A delivery that resolves to an answer for a run's pending interaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    interaction_id: UUID
    github_comment_id: int
    answer: str


class UnresolvableComment(BaseModel):
    """A delivery that does not resolve to an answer, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: IgnoreReason


def resolve_issue_comment(
    event: IssueCommentEvent,
    *,
    session: Session,
    authenticated_login: Callable[[], str],
) -> ResolvedAnswer | UnresolvableComment:
    """Decide whether ``event`` (a ``githubkit.webhooks.parse``-produced typed
    ``issue_comment`` event) answers a run's pending interaction.

    ``authenticated_login`` is a zero-argument callable returning Dark
    Factory's own GitHub login, injected so the unit tier needs no GitHub
    (mirrors ``github_client_factory``'s injection style elsewhere in this
    codebase). Checks are ordered cheapest-and-most-exclusionary first, so an
    obviously irrelevant delivery costs no database round trip:

    1. Reject any ``action`` other than ``created`` -- ``edited``/``deleted``
       cannot un-answer an interaction that is already ``ANSWERED`` (D-05's
       dedup key is the comment id, so re-processing an edit would at best be
       a no-op and at worst overwrite a recorded answer with later text).
    2. Reject a payload whose issue carries a ``pull_request`` field -- Dark
       Factory only ever asks its questions on issues (GIT-05), so a
       pull-request-thread comment can never be an answer.
    3. Reject a comment whose body is empty or whitespace-only -- storing an
       empty answer would move a run out of ``WAITING_HUMAN`` having learned
       nothing.
    4. Look the run up with :func:`~dark_factory.persistence.repositories.github_pending_interaction`,
       keyed on the owner, repo and issue number read off the typed event.
       This is also the check that makes "never creates a new run"
       structural: this module has no code path that writes a ``runs`` row,
       and the lookup either finds an existing waiting run or gives up.
    5. Reject a self-authored comment two independent ways (see module
       docstring): the comment's id equalling the interaction's
       ``clarification_comment_id``, and the commenter's login equalling
       ``authenticated_login()``.
    6. Otherwise return :class:`ResolvedAnswer` with the comment body
       verbatim -- no normalization, no escaping, no truncation. The body is
       untrusted text; it is stored through the one mutation path, which
       already redacts it before it reaches Neon.
    """
    if event.action != "created":
        return UnresolvableComment(reason=IgnoreReason.NOT_CREATED_ACTION)

    pull_request = event.issue.pull_request
    if pull_request is not UNSET and pull_request is not None:
        return UnresolvableComment(reason=IgnoreReason.PULL_REQUEST_THREAD)

    body = event.comment.body
    if not body.strip():
        return UnresolvableComment(reason=IgnoreReason.EMPTY_BODY)

    pending = github_pending_interaction(
        session,
        owner=event.repository.owner.login,
        repo=event.repository.name,
        issue_number=event.issue.number,
    )
    if pending is None:
        return UnresolvableComment(reason=IgnoreReason.NO_PENDING_INTERACTION)

    comment_id = event.comment.id
    if comment_id == pending.clarification_comment_id:
        return UnresolvableComment(reason=IgnoreReason.SELF_AUTHORED)

    commenter_user = event.comment.user
    commenter_login = commenter_user.login if commenter_user is not None else None
    if commenter_login is not None and commenter_login == authenticated_login():
        return UnresolvableComment(reason=IgnoreReason.SELF_AUTHORED)

    return ResolvedAnswer(
        run_id=pending.run_id,
        interaction_id=pending.interaction_id,
        github_comment_id=comment_id,
        answer=body,
    )
