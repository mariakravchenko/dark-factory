"""Unit coverage for ``build_worker_env`` -- the TOOL-04/SEC-03 allowlist
shape, boundary and absent-name proofs (Phase 6, plan 06-02, A-06-E2).

The cross-process proof that a genuinely separate OS process sees the same
guarantees lives in ``tests/integration/test_worker_env_boundary.py``
(D-10) -- this module proves only the in-process mapping shape.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from dark_factory.tools.env import WORKER_ENV_ALLOWLIST, build_worker_env

pytestmark = pytest.mark.unit

_XDG_NAMES = {"XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"}


def _set_sensitive_parent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake-db.invalid/df")
    monkeypatch.setenv(
        "DATABASE_URL_DIRECT", "postgresql://fake@fake-direct.invalid/df"
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake0000000000000000000000000000")
    monkeypatch.setenv("MY_UNRELATED_KEY", "unrelated-value")


def test_returned_keys_are_a_subset_of_the_allowlist_plus_xdg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sensitive_parent_env(monkeypatch)
    result = build_worker_env("DEVELOPMENT")
    assert set(result) <= set(WORKER_ENV_ALLOWLIST) | _XDG_NAMES


def test_infrastructure_credentials_and_unrelated_keys_never_appear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sensitive_parent_env(monkeypatch)
    result = build_worker_env("DEVELOPMENT")
    for forbidden in (
        "DATABASE_URL",
        "DATABASE_URL_DIRECT",
        "GITHUB_TOKEN",
        "MY_UNRELATED_KEY",
    ):
        assert forbidden not in result


def test_value_none_yields_no_credential_key() -> None:
    result = build_worker_env("DEVELOPMENT", env_var_name=None, value=None)
    assert "ANTHROPIC_API_KEY" not in result


def test_supplying_name_and_value_adds_exactly_one_key_with_the_exact_value() -> None:
    base = build_worker_env("DEVELOPMENT")
    result = build_worker_env(
        "DEVELOPMENT",
        env_var_name="ANTHROPIC_API_KEY",
        value=SecretStr("sk-test-value"),
    )
    assert set(result) - set(base) == {"ANTHROPIC_API_KEY"}
    assert result["ANTHROPIC_API_KEY"] == "sk-test-value"


def test_named_credential_without_a_value_is_absent_not_empty() -> None:
    result = build_worker_env("DEVELOPMENT", env_var_name="X", value=None)
    assert "X" not in result


def test_allowlisted_name_absent_from_parent_is_absent_from_result_not_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    result = build_worker_env("DEVELOPMENT")
    assert "SSL_CERT_FILE" not in result


def test_two_roles_get_different_xdg_config_home() -> None:
    first = build_worker_env("DEVELOPMENT")
    second = build_worker_env("QA")
    assert first["XDG_CONFIG_HOME"] != second["XDG_CONFIG_HOME"]
