"""Coverage for the `dark_factory_github_token` D-15 key-name rename (quick
task 261031-lhn).

This is a sibling of ``tests/unit/test_redaction.py``, not an addition to it,
per the quick-task plan's own instruction (the plan's `files_modified` list
does not include that file). It pins the F2 finding: renaming
``Settings.github_token`` to ``Settings.dark_factory_github_token`` is a
genuine D-15 coverage regression unless ``_SENSITIVE_KEYS`` gains the new
name WITHOUT losing the old one.

Tests A and B were observed RED before the ``_SENSITIVE_KEYS`` edit (the
value survived verbatim in both the ``key=value`` and mapping-key paths);
GREEN after. Test C pins the retention half of F2 -- third-party text still
spelled the old way must still be redacted, which is what makes the
``_SENSITIVE_KEYS`` edit an ADD rather than a replace. Test D pins the
``known_secret_values()`` coupling (F2's second half) for a value carrying
no recognisable token shape.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_a_key_value_pair_with_the_new_key_name_is_redacted() -> None:
    """RED before the `_SENSITIVE_KEYS` edit: the value survived verbatim."""
    from dark_factory.events.redaction import redact

    out = redact("DARK_FACTORY_GITHUB_TOKEN=abcd1234secretvalue", known_secrets={})

    assert "abcd1234secretvalue" not in out
    assert "[redacted:dark_factory_github_token]" in out


def test_b_a_mapping_key_with_the_new_key_name_is_redacted() -> None:
    """Separate code path from Test A: `redact()` dispatches on
    `key.lower() in _SENSITIVE_KEYS` for a `Mapping`, not the `key=value`
    regex. One passing does not imply the other."""
    from dark_factory.events.redaction import redact

    out = redact({"DARK_FACTORY_GITHUB_TOKEN": "abcd1234secretvalue"}, known_secrets={})

    assert out["DARK_FACTORY_GITHUB_TOKEN"] == "[redacted:dark_factory_github_token]"


def test_c_old_spelling_in_assignment_form_is_still_redacted() -> None:
    """F2 retention half: third-party workflow text echoed into a
    WorkerResult still uses the old spelling. This is what stops the
    `_SENSITIVE_KEYS` edit from being a replace instead of an add."""
    from dark_factory.events.redaction import redact

    out = redact("GITHUB_TOKEN=abcd1234secretvalue", known_secrets={})

    assert "abcd1234secretvalue" not in out
    assert "[redacted:github_token]" in out


def test_d_a_configured_credential_with_no_token_shape_is_redacted_by_label() -> None:
    """F2's `known_secret_values()` coupling: renaming the Settings field
    changes the observable label for the exact-value substitution path."""
    from dark_factory.events.redaction import redact

    value = "this-is-not-shaped-like-any-known-token-pattern"
    out = redact(
        f"configured value: {value}",
        known_secrets={value: "dark_factory_github_token"},
    )

    assert value not in out
    assert "[redacted:dark_factory_github_token]" in out
