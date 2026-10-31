"""G-11-3 regression guard: the runtime analogue of
``test_package_import_needs_no_database.py``'s import-time sweep.

That module proves every ``dark_factory`` module *imports* with no database
URL configured and no readable ``.env``. It cannot see G-11-3's class of
defect by construction: G-11-3's twelve CI failures (recorded in
``.planning/debug/ci-unit-tier-settings-validation-g-11-3.md``) were all
runtime calls to the process-global ``get_settings()`` on branches only
*some* tests reach, surfaced while *executing* tests under ``tests/`` --
code that import sweep never touches. This module reproduces CI's own
condition -- a child process with no ``DATABASE_URL``/``DATABASE_URL_DIRECT``
and a working directory with no readable ``.env`` -- and runs the whole
selector CI runs, so this defect class fails locally instead of only in a
pushed CI run.

Why the working directory is load-bearing: ``Settings.model_config`` sets
``env_file=".env"``, resolved relative to the process CWD
(``src/dark_factory/config/settings.py``). This repository has a
git-ignored ``.env`` holding both required fields, so any child spawned
from the repository root would construct ``Settings()`` successfully and
every test below would pass vacuously, for the wrong reason. Every child
process here is launched with a working directory under ``tmp_path`` for
exactly that reason.

The child environment is built from an explicit named allowlist, never
``os.environ.copy()`` or a filtered copy of it (CLAUDE.md's credential
boundary; mirrors ``test_package_import_needs_no_database.py``'s own
``_ENV_ALLOWLIST``/``_sanitized_env`` idiom -- reused here as an idiom, not
imported, so the two guards can fail independently). ``DATABASE_URL`` and
``DATABASE_URL_DIRECT`` are *absent* from that environment, never set to an
empty string -- an empty string is still a present value and ``pydantic``
fails differently, which would make the positive control prove the wrong
thing. ``PATH`` is deliberately kept in the allowlist for Test 1: on a
developer machine with worker CLIs installed, that is the harsher condition
under which the live integration suites are imported during collection, and
it is why the latent sibling defect (Test 2) was found at all. Sanitizing
``PATH`` would make Test 1 pass for a reason the hosted runner happens to
share today and will stop sharing the moment ``ci.yml`` provisions those
CLIs.

The marker expression Test 1 runs is read out of
``.github/workflows/ci.yml``'s ``Unit and contract tiers`` step rather than
restated as a literal, so changing CI's selector changes what this guard
proves instead of silently decoupling the two. A missing step or a command
with no ``-m`` flag is a loud, named failure -- never a silent fallback to a
hardcoded default.

This module excludes itself from every child's collection via ``--ignore``
pointed at its own resolved absolute path (derived from ``__file__``, never
a name match, a marker the child deselects, or an environment sentinel a
later rename or stray variable could defeat). A child that collected this
module would spawn its own grandchild tier and never terminate.

Honest limitation: ``get_settings()`` is ``functools.lru_cache(maxsize=1)``
-- a single-entry, process-wide cache. In a child process where an
earlier-running test populates that cache with a working ``Settings``
instance before a later, broken test reaches it, the later offender could in
principle be masked. The established override idiom
(``monkeypatch.setenv`` + ``get_settings.cache_clear()``) clears that cache
in its own teardown specifically to avoid this, and CI's originally observed
failure count matched this harness's own count exactly, so ordering did not
matter in practice -- but this is a property of today's test suite, not a
guarantee this module enforces.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.support.live_runtime import LIVE_RUNTIMES

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_CI_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_THIS_FILE = Path(__file__).resolve()

_CI_STEP_NAME = "Unit and contract tiers"

# The three live-CLI integration suites -- every module that calls
# `tests.support.live_runtime.skip_reason` at import time and is therefore
# exposed to G-11-3's latent sibling (an unconstructible `Settings` raised
# at collection time rather than caught and reported as a skip).
_LIVE_SUITE_MODULES: tuple[str, ...] = (
    "tests/integration/test_claude_code_live.py",
    "tests/integration/test_copilot_live.py",
    "tests/integration/test_hermes_live.py",
)

# Only what a child interpreter needs to start up, import the installed
# package and resolve TLS roots -- deliberately no wildcard copy of the
# parent environment. `DATABASE_URL` / `DATABASE_URL_DIRECT` are never
# added. Reuses `test_package_import_needs_no_database.py`'s allowlist
# *idiom*, not its tuple by import -- the two guards must be able to fail
# independently.
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "VIRTUAL_ENV",
    "PYENV_ROOT",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUNBUFFERED",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)

# Planning measurements: 275.12s locally for the sanitized full tier, 36.81s
# on the GitHub-hosted runner for the unsanitized one. These ceilings carry
# generous margin above the local figure so a timeout is a loud, named
# failure rather than an opaque hang, never so tight it flakes on a slow
# laptop.
_FULL_TIER_TIMEOUT_SECONDS = 480
_COLLECT_ONLY_TIMEOUT_SECONDS = 90
_POSITIVE_CONTROL_TIMEOUT_SECONDS = 60


def _sanitized_env() -> dict[str, str]:
    """An explicit dict comprehension over a named allowlist tuple, never a
    copy or filter of `os.environ` -- the credential-boundary idiom this
    project's own `tests/support/subprocess_runner.py` documents."""
    return {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}


def _run_child(
    args: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"child process exceeded its {timeout}s timeout ceiling (chosen "
            "with margin above a planning measurement of 275.12s locally / "
            f"36.81s on the hosted CI runner): {exc}"
        )


def _marker_expression_from_ci_workflow() -> str:
    """Read the `-m` marker expression out of `ci.yml`'s own
    `Unit and contract tiers` step, so this guard cannot drift from the
    command CI actually runs. Fails loudly, naming what was observed,
    rather than ever falling back to a hardcoded default."""
    workflow = yaml.safe_load(_CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["quality"]["steps"]
    step = next((s for s in steps if s.get("name") == _CI_STEP_NAME), None)
    if step is None:
        step_names = [s.get("name") for s in steps]
        raise AssertionError(
            f"No step named {_CI_STEP_NAME!r} found in {_CI_WORKFLOW_PATH}; "
            f"step names observed: {step_names!r}"
        )
    run_string = step.get("run", "")
    tokens = shlex.split(run_string)
    if "-m" not in tokens:
        raise AssertionError(
            f"{_CI_STEP_NAME!r} step's run command carries no '-m' marker "
            f"flag: {run_string!r}"
        )
    idx = tokens.index("-m")
    if idx + 1 >= len(tokens):
        raise AssertionError(
            f"{_CI_STEP_NAME!r} step's '-m' flag has no following marker "
            f"expression: {run_string!r}"
        )
    return tokens[idx + 1]


def _write_stub_binaries(stub_dir: Path) -> None:
    """Write one executable stub per distinct binary name the live-runtime
    registry names -- derived from the registry rather than listed, so this
    adversary cannot silently diverge from the binaries the credential
    probe actually resolves, and covers a fourth adapter automatically.

    The stub's contents never execute -- Test 2 runs `--collect-only`, so
    only `PATH` resolution matters, never invocation."""
    stub_dir.mkdir(parents=True, exist_ok=True)
    binary_names = {runtime.binary for runtime in LIVE_RUNTIMES.values()}
    for name in sorted(binary_names):
        stub_path = stub_dir / name
        stub_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub_path.chmod(0o755)


# --------------------------------------------------------------------------- #
# Test 1: the property -- the whole `unit or contract` tier, run exactly as
# CI's own step runs it, passes with no database variables and no readable
# `.env`.
# --------------------------------------------------------------------------- #


def test_the_unit_or_contract_tier_passes_with_no_database_and_no_env_file(
    tmp_path: Path,
) -> None:
    marker_expression = _marker_expression_from_ci_workflow()
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        marker_expression,
        "-p",
        "no:cacheprovider",
        "-c",
        str(_PYPROJECT),
        "--rootdir",
        str(_REPO_ROOT),
        "--ignore",
        str(_THIS_FILE),
        str(_REPO_ROOT / "tests"),
    ]
    result = _run_child(
        args,
        cwd=tmp_path,
        env=_sanitized_env(),
        timeout=_FULL_TIER_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, (
        f"the {marker_expression!r} tier (read from {_CI_WORKFLOW_PATH}'s "
        f"{_CI_STEP_NAME!r} step) failed in a child process with no "
        f"DATABASE_URL/DATABASE_URL_DIRECT and no readable .env "
        f"(exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Test 2: the latent-sibling adversary -- the live-CLI integration modules
# collect cleanly under the same sanitized environment even when their
# binaries resolve on PATH.
# --------------------------------------------------------------------------- #


def test_live_suite_modules_collect_with_stub_binaries_on_path(
    tmp_path: Path,
) -> None:
    stub_dir = tmp_path / "stub_bin"
    _write_stub_binaries(stub_dir)
    child_cwd = tmp_path / "cwd"
    child_cwd.mkdir()

    env = _sanitized_env()
    inherited_path = env.get("PATH", os.defpath)
    env["PATH"] = os.pathsep.join([str(stub_dir), inherited_path])

    args = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "-c",
        str(_PYPROJECT),
        "--rootdir",
        str(_REPO_ROOT),
        *(str(_REPO_ROOT / module) for module in _LIVE_SUITE_MODULES),
    ]
    result = _run_child(
        args,
        cwd=child_cwd,
        env=env,
        timeout=_COLLECT_ONLY_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, (
        "collection of the live-CLI integration modules failed with stub "
        f"worker binaries on PATH and no DATABASE_URL/DATABASE_URL_DIRECT "
        f"(exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "error" not in result.stdout.lower(), (
        "collection reported error text even though the exit code was 0 -- "
        "a collection error can coexist with a surprising exit code across "
        f"pytest versions:\nstdout:\n{result.stdout}"
    )


# --------------------------------------------------------------------------- #
# Test 3: the positive control -- the harness has teeth.
# --------------------------------------------------------------------------- #


def test_the_harness_detects_an_unguarded_settings_read(tmp_path: Path) -> None:
    probe_file = tmp_path / "test_gsd_g11_3_settings_probe.py"
    probe_file.write_text(
        "from dark_factory.config.settings import get_settings\n"
        "\n"
        "\n"
        "def test_offender() -> None:\n"
        "    get_settings()\n",
        encoding="utf-8",
    )
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-c",
        str(_PYPROJECT),
        "--rootdir",
        str(_REPO_ROOT),
        str(probe_file),
    ]
    result = _run_child(
        args,
        cwd=tmp_path,
        env=_sanitized_env(),
        timeout=_POSITIVE_CONTROL_TIMEOUT_SECONDS,
    )
    assert result.returncode != 0, (
        "the positive-control probe reported a zero exit for a test that "
        "reaches get_settings() with no override -- this harness's "
        "sanitization has silently stopped working, which would let Tests "
        "1 and 2 both pass for the wrong reason:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "ValidationError" in result.stdout, (
        "expected pydantic's ValidationError to be named in the probe's "
        f"failure output:\nstdout:\n{result.stdout}"
    )
