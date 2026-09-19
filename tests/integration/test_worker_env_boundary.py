"""SC2 cross-process proof: a genuinely separate OS process, spawned with
``build_worker_env()``'s output, reports no infrastructure credential about
itself (D-10, TOOL-04, SEC-03).

An in-process mapping check cannot prove what a spawned child actually
receives -- this module proves it the only honest way: build the
environment, spawn ``tests/support/env_dump.py`` as a real subprocess with
it, and assert against the JSON the child itself wrote to stdout describing
its own ``os.environ``, never against the mapping that was passed in.

D-10 scope, stated plainly: this module proves the *builder* is correct.
It does not change ``FakeWorker`` to spawn a subprocess -- that worker
stays in-process with no external call, per its existing contract, and
this module imports nothing from the workers package. Wiring the builder
to a real worker adapter is Phase 7's job.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

from dark_factory.tools.env import build_worker_env

pytestmark = pytest.mark.integration

_ENV_DUMP_SCRIPT = Path(__file__).resolve().parents[1] / "support" / "env_dump.py"


def _spawn_dump(env: dict[str, str]) -> dict[str, str]:
    result = subprocess.run(
        [sys.executable, str(_ENV_DUMP_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    child_env: dict[str, str] = json.loads(result.stdout)
    return child_env


def test_a_real_spawned_process_reports_no_infrastructure_credential_or_unrelated_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake-db.invalid/df")
    monkeypatch.setenv(
        "DATABASE_URL_DIRECT", "postgresql://fake@fake-direct.invalid/df"
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake0000000000000000000000000000")
    monkeypatch.setenv("MY_UNRELATED_KEY", "unrelated-value")

    child_env = _spawn_dump(build_worker_env("DEVELOPMENT"))

    assert "DATABASE_URL" not in child_env
    assert "DATABASE_URL_DIRECT" not in child_env
    assert "GITHUB_TOKEN" not in child_env
    assert "MY_UNRELATED_KEY" not in child_env
    assert not any(name.endswith("_API_KEY") for name in child_env)


def test_a_supplied_credential_reaches_the_child_under_its_exact_name_and_value() -> (
    None
):
    child_env = _spawn_dump(
        build_worker_env(
            "DEVELOPMENT",
            env_var_name="ANTHROPIC_API_KEY",
            value=SecretStr("sk-test-value"),
        )
    )
    assert child_env["ANTHROPIC_API_KEY"] == "sk-test-value"
    assert sum(1 for name in child_env if name.endswith("_API_KEY")) == 1


def test_the_child_environment_is_demonstrably_usable_not_merely_safe() -> None:
    child_env = _spawn_dump(build_worker_env("DEVELOPMENT"))
    assert child_env.get("PATH")
