"""CFG-05: the full effective-config snapshot survives a ``create_run`` ->
``load_run_state`` round trip byte-for-byte.

``create_run`` redacts the ``workflow`` dict before it is written to
``runs.workflow``; ``load_run_state`` reads it straight back into
``RunState.workflow``. This module proves the two are deep-equal after applying
the *same* ``redact()`` the write applies -- including the ordered ``roles``
list, every inlined ``instruction_text``, and the ``repository`` /
``quality_gate`` / ``retry`` / ``publishing`` blocks -- so a later resume that
rebuilds the pipeline from the column gets exactly the configuration resolved at
run creation.

Every test runs inside the rolled-back ``db_session`` outer transaction;
``use_fake_secrets`` swaps ``mutations.get_settings`` for a ``Settings`` built
from obviously-fake credentials.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from dark_factory.config.settings import Settings
from dark_factory.domain.task import NormalizedTask
from dark_factory.events.redaction import redact
from dark_factory.persistence.mutations import create_run
from dark_factory.persistence.repositories import load_run_state
from dark_factory.workflows.pipeline import pipeline_from_snapshot

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]


def _task() -> NormalizedTask:
    return NormalizedTask(
        source_kind="text",
        source_ref=None,
        title="t",
        body="do the thing",
        metadata={},
    )


def test_full_effective_config_snapshot_roundtrips_deep_equal(
    db_session: Session,
    fake_settings: Settings,
    repo_config_snapshot: dict[str, object],
) -> None:
    expected = redact(
        repo_config_snapshot, known_secrets=fake_settings.known_secret_values()
    )

    run_id = create_run(db_session, task=_task(), workflow=repo_config_snapshot)
    state = load_run_state(db_session, run_id)

    assert state is not None
    assert state.workflow == expected

    written_roles = state.workflow["roles"]
    expected_roles = expected["roles"]
    assert [r["name"] for r in written_roles] == [r["name"] for r in expected_roles]
    for written, want in zip(written_roles, expected_roles, strict=True):
        assert written["instruction_text"] == want["instruction_text"]
        assert isinstance(written["instruction_text"], str)
        assert written["instruction_text"].strip() != ""
        assert written["before"] == want["before"]
        assert written["after"] == want["after"]

    for key in ("repository", "quality_gate", "retry", "publishing"):
        assert state.workflow[key] == expected[key]


def test_legacy_bare_string_snapshot_roundtrips_and_still_builds_a_pipeline(
    db_session: Session,
) -> None:
    run_id = create_run(db_session, task=_task(), workflow={"roles": ["BA"]})
    state = load_run_state(db_session, run_id)

    assert state is not None
    assert state.workflow == {"roles": ["BA"]}

    pipeline = pipeline_from_snapshot(state.workflow)
    assert [n.name for n in pipeline.nodes] == ["BA"]
    assert pipeline.nodes[0].worker == "fake"
