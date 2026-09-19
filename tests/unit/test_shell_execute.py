"""Unit coverage for ``shell_execute`` -- the D-11 credential-boundary
proofs through the ``shell.execute`` capability's first production call
site (Phase 6, plan 06-02, Task 2).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from pydantic import SecretStr

from dark_factory.config.loader import load_effective_config
from dark_factory.tools import CapabilityDeniedError
from dark_factory.tools.env import InvalidShellCommandError, ShellResult, shell_execute
from dark_factory.tools.registry import default_registry

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _shipped_role_tools() -> dict[str, list[str]]:
    """The shipped per-role ``tools:`` grants, resolved through
    ``load_effective_config`` against the real repo root, so this test
    cannot drift from the shipped YAML."""
    snapshot = load_effective_config(_REPO_ROOT)
    return {role["name"]: list(role["tools"]) for role in snapshot["roles"]}


def test_happy_path_returns_exit_code_zero_and_expected_stdout(
    tmp_path: Path,
) -> None:
    result = shell_execute(
        command=[sys.executable, "-c", "print(1)"],
        cwd=tmp_path,
        role="DEVELOPMENT",
    )
    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert "1" in result.stdout
    assert result.timed_out is False


def test_a_bare_string_command_raises_a_typed_error_and_spawns_nothing(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvalidShellCommandError):
        shell_execute(
            command="echo hi",  # type: ignore[arg-type]
            cwd=tmp_path,
            role="DEVELOPMENT",
        )


def test_shell_metacharacters_reach_the_child_verbatim_as_a_single_argument(
    tmp_path: Path,
) -> None:
    metachar_arg = "hello; rm -rf /tmp/should-not-run | cat > /tmp/should-not-run"
    result = shell_execute(
        command=[
            sys.executable,
            "-c",
            "import sys; print(sys.argv[1])",
            metachar_arg,
        ],
        cwd=tmp_path,
        role="DEVELOPMENT",
    )
    assert result.stdout.strip() == metachar_arg


def test_the_credential_boundary_holds_through_the_real_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake-db.invalid/df")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake0000000000000000000000000000")
    result = shell_execute(
        command=[
            sys.executable,
            "-c",
            "import os, json, sys; json.dump(list(os.environ), sys.stdout)",
        ],
        cwd=tmp_path,
        role="DEVELOPMENT",
    )
    assert "DATABASE_URL" not in result.stdout
    assert "GITHUB_TOKEN" not in result.stdout


def test_a_supplied_credential_reaches_the_child_under_its_name(
    tmp_path: Path,
) -> None:
    result = shell_execute(
        command=[
            sys.executable,
            "-c",
            "import os; print(os.environ.get('ANTHROPIC_API_KEY', ''))",
        ],
        cwd=tmp_path,
        role="DEVELOPMENT",
        env_var_name="ANTHROPIC_API_KEY",
        value=SecretStr("sk-test-value"),
    )
    assert result.stdout.strip() == "sk-test-value"


def test_a_sleeping_command_exceeding_the_timeout_times_out_and_is_reaped(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    result = shell_execute(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        role="DEVELOPMENT",
        timeout=1,
    )
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert result.exit_code is None
    assert elapsed < 10


def test_denied_by_default_through_the_registry_for_ba_and_granted_for_development(
    tmp_path: Path,
) -> None:
    shipped = _shipped_role_tools()
    with pytest.raises(CapabilityDeniedError):
        default_registry.invoke(
            "BA",
            "shell.execute",
            shipped["BA"],
            command=[sys.executable, "-c", "print(1)"],
            cwd=tmp_path,
            role="BA",
        )
    result = default_registry.invoke(
        "DEVELOPMENT",
        "shell.execute",
        shipped["DEVELOPMENT"],
        command=[sys.executable, "-c", "print(1)"],
        cwd=tmp_path,
        role="DEVELOPMENT",
    )
    assert isinstance(result, ShellResult)
    assert result.exit_code == 0


def test_shell_execute_itself_performs_no_permission_check(tmp_path: Path) -> None:
    """Invoking ``shell_execute`` directly (bypassing the registry) runs
    the command regardless of role -- exactly why every caller must go
    through ``ToolRegistry.invoke()``."""
    result = shell_execute(
        command=[sys.executable, "-c", "print(1)"],
        cwd=tmp_path,
        role="BA",
    )
    assert result.exit_code == 0
