"""Unit coverage for the write-spec models in ``persistence/mutations.py``
that need no database (Phase 10, plan 10-06): ``PublishFieldsWrite`` (new)
and ``HumanInteractionWrite``'s two new comment-id fields.

``apply_transition`` itself opens a real ``session.begin()`` against a
``runs`` row and cannot be meaningfully exercised without PostgreSQL -- this
project's ``unit`` tier is "fast, pure-function tests with no database or
I/O" (see ``tests/unit/test_domain_enums.py``'s docstring) and does not fake
a ``Session``. The full ``publish_fields`` patch-semantics proof against a
real ``runs`` row lives at the db tier, in
``tests/db/test_publish_step.py`` (Task 2) -- this module covers only the
pydantic-level contract these two models make on their own.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dark_factory.persistence.mutations import HumanInteractionWrite, PublishFieldsWrite

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# PublishFieldsWrite
# --------------------------------------------------------------------------- #


def test_publish_fields_write_defaults_every_field_to_none() -> None:
    spec = PublishFieldsWrite()
    assert spec.pr_number is None
    assert spec.pr_url is None
    assert spec.published_commit_sha is None


def test_publish_fields_write_accepts_all_three_fields() -> None:
    spec = PublishFieldsWrite(
        pr_number=7,
        pr_url="https://example.invalid/pr/7",
        published_commit_sha="a" * 40,
    )
    assert spec.pr_number == 7
    assert spec.pr_url == "https://example.invalid/pr/7"
    assert spec.published_commit_sha == "a" * 40


def test_publish_fields_write_is_frozen() -> None:
    spec = PublishFieldsWrite(pr_number=7)
    with pytest.raises(ValidationError):
        spec.pr_number = 8  # type: ignore[misc]


def test_publish_fields_write_rejects_an_unknown_keyword() -> None:
    with pytest.raises(ValidationError):
        PublishFieldsWrite(pr_number=7, worker_session_id="nope")  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# HumanInteractionWrite -- the two new comment-id fields
# --------------------------------------------------------------------------- #


def test_human_interaction_write_comment_id_fields_default_to_none() -> None:
    spec = HumanInteractionWrite(mode="ask")
    assert spec.clarification_comment_id is None
    assert spec.github_comment_id is None


def test_human_interaction_write_ask_mode_accepts_clarification_comment_id() -> None:
    spec = HumanInteractionWrite(
        mode="ask",
        clarification_comment_id=4503599627370496,
    )
    assert spec.clarification_comment_id == 4503599627370496


def test_human_interaction_write_answer_mode_accepts_github_comment_id() -> None:
    spec = HumanInteractionWrite(
        mode="answer",
        answer="the answer",
        github_comment_id=4503599627370496,
    )
    assert spec.github_comment_id == 4503599627370496


def test_human_interaction_write_rejects_an_unknown_keyword() -> None:
    with pytest.raises(ValidationError):
        HumanInteractionWrite(mode="ask", worker_session_id="nope")  # type: ignore[call-arg]
