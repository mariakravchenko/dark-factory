"""G-11-1 regression guard: importing `dark_factory` -- and every module
beneath it, not just the one file that broke -- must never require a
reachable database (gap-closure plan 11-06), plus a pytest-collection-level
analogue of the same property against a small, named set of real test
modules (collection resolves fixtures and `conftest.py`, which a bare
import sweep never exercises).

`Settings.model_config` sets ``env_file=".env"``, resolved relative to the
process working directory (``src/dark_factory/config/settings.py``). This
repository has a git-ignored ``.env`` holding ``DATABASE_URL``, so every
ordinary ``pytest`` invocation from the repo root constructs ``Settings()``
successfully and the defect this guard exists for is invisible. The property
under test only shows up when **both** conditions hold at once: no
``DATABASE_URL``/``DATABASE_URL_DIRECT`` in the environment, **and** a
working directory with no readable ``.env``. Every child process below is
launched with ``cwd=tmp_path`` for exactly that reason -- a test that spawns
from the repo root would pass vacuously, for the wrong reason.

The child environment is built from an explicit named allowlist, never
``os.environ.copy()`` or a filtered copy of it (CLAUDE.md's credential
boundary; mirrors ``tests/support/subprocess_runner.py``'s own
``child_env``/``_ENV_ALLOWLIST`` idiom). The two database variables are
*absent* from that environment, never set to an empty string -- an empty
string is still a present value and ``pydantic`` would fail differently.

``tests/support/subprocess_runner.py``'s ``spawn``/``popen`` helpers hardcode
``python -m dark_factory <args>`` and so cannot serve this module, which
needs a bare ``-c <script>`` invocation (the package-wide import sweep) and a
``-m pytest <args>`` invocation (the collect-only check); this module reuses
the allowlist *idiom*, not those two helpers.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Only what the child interpreter needs to start up, import the installed
# package and resolve TLS roots -- deliberately no wildcard copy of the
# parent environment. `DATABASE_URL` / `DATABASE_URL_DIRECT` are never added.
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

# A small, named sample of real test modules exercising pytest collection
# itself (fixtures, conftest.py) rather than a bare import -- the mechanism
# the original G-11-1 regression modules tripped on. Deviation, documented:
# the three modules G-11-1 originally named here no longer exist (this
# removal deleted all three); this constant now points at modules that
# still exist and still import `dark_factory.config.settings` heavily at
# collection time, so the pytest-collection-specific property Test 2 proves
# keeps a non-trivial, real target.
_G11_1_MODULES = (
    "tests/unit/test_settings.py",
    "tests/unit/test_github_ownership_boundary.py",
    "tests/db/test_clarification_comment_is_redacted.py",
)

# A child-process script, filled in via a literal `__ROOT_NAME__` replacement
# (not `str.format`, to avoid escaping the script's own `{}`-using f-strings
# and dict-free string building below). Imports `__ROOT_NAME__` itself, then
# every submodule `pkgutil.walk_packages` yields beneath it, recording every
# failure as a machine-readable `FAIL\t<module>\t<exc class>\t<missing name>`
# line, terminated by a `TOTAL\t<count>` line. `onerror` is passed explicitly
# to `walk_packages`: its default silently swallows an exception raised while
# importing a *package* in order to walk it, which would make a broken
# sub-package invisible to this sweep.
_SWEEP_SCRIPT = """
import importlib
import pkgutil

root_name = "__ROOT_NAME__"
results = []


def _record(name, exc):
    results.append((name, type(exc).__name__, getattr(exc, "name", None) or ""))


def _on_walk_error(name):
    try:
        raise
    except Exception as exc:
        _record(name, exc)


try:
    root = importlib.import_module(root_name)
except Exception as exc:
    root = None
    _record(root_name, exc)

if root is not None and hasattr(root, "__path__"):
    for info in pkgutil.walk_packages(
        root.__path__, prefix=root_name + ".", onerror=_on_walk_error
    ):
        try:
            importlib.import_module(info.name)
        except Exception as exc:
            _record(info.name, exc)

for name, exc_class, missing in results:
    print("FAIL\\t" + name + "\\t" + exc_class + "\\t" + missing)
print("TOTAL\\t" + str(len(results)))
"""


def _sanitized_env() -> dict[str, str]:
    """An explicit dict comprehension over a named allowlist tuple, never a
    copy or filter of `os.environ` -- the credential-boundary idiom this
    project's own `tests/support/subprocess_runner.py` documents."""
    return {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}


def _run_sweep(
    root_name: str, *, cwd: Path, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    script = _SWEEP_SCRIPT.replace("__ROOT_NAME__", root_name)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=_sanitized_env(),
        cwd=str(cwd),  # no `.env` here -- keeps the repo's git-ignored one out of reach
        timeout=timeout,
        check=False,
    )


def _classify_sweep_output(stdout: str) -> tuple[list[str], list[str]]:
    """Split the sweep's `FAIL` lines into offenders and the one tolerated
    failure class: a `ModuleNotFoundError` whose missing module name does not
    start with `dark_factory` -- an uninstalled optional dependency extra
    (`mcp` is absent from a plain `uv sync` venv). Every other exception type,
    and in particular a `pydantic_core.ValidationError`, is an offender."""
    offenders: list[str] = []
    tolerated: list[str] = []
    for line in stdout.splitlines():
        if not line.startswith("FAIL\t"):
            continue
        _, name, exc_class, missing = line.split("\t", 3)
        if (
            exc_class == "ModuleNotFoundError"
            and missing
            and not missing.startswith("dark_factory")
        ):
            tolerated.append(f"{name} ({exc_class}: missing module {missing!r})")
        else:
            detail = f" (missing module {missing!r})" if missing else ""
            offenders.append(f"{name} raised {exc_class}{detail}")
    return offenders, tolerated


# --------------------------------------------------------------------------- #
# Test 1: the generalized property -- every dark_factory module imports with
# no database URL configured and no readable .env.
# --------------------------------------------------------------------------- #


def test_every_dark_factory_module_imports_with_no_database_configured(
    tmp_path: Path,
) -> None:
    result = _run_sweep("dark_factory", cwd=tmp_path)
    assert result.returncode == 0, (
        "the sweep subprocess itself crashed "
        f"(exit {result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    offenders, tolerated = _classify_sweep_output(result.stdout)
    assert not offenders, (
        "dark_factory module(s) failed to import with no DATABASE_URL/"
        f"DATABASE_URL_DIRECT and no readable .env: {offenders}\n"
        f"(tolerated, uninstalled-optional-extra failures: {tolerated})"
    )


# --------------------------------------------------------------------------- #
# Test 2: the pytest-collection analogue -- a small, named sample of real
# test modules collect under the same sanitized environment.
# --------------------------------------------------------------------------- #


def test_g11_1_modules_collect_with_no_database_configured(tmp_path: Path) -> None:
    args = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-c",
        str(_PYPROJECT),
        "--rootdir",
        str(_REPO_ROOT),
        *(str(_REPO_ROOT / module) for module in _G11_1_MODULES),
    ]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=_sanitized_env(),
        cwd=str(tmp_path),  # no `.env` here -- the working directory is load-bearing
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        "collection of the three G-11-1 modules failed with no DATABASE_URL/"
        f"DATABASE_URL_DIRECT and no readable .env (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Test 3: positive control -- the Test 1 harness has teeth.
# --------------------------------------------------------------------------- #


def test_the_sweep_harness_detects_a_module_that_constructs_settings_at_import_time(
    tmp_path: Path,
) -> None:
    probe_package = "gsd_g11_1_settings_probe"
    package_dir = tmp_path / probe_package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "offender.py").write_text(
        "from dark_factory.config.settings import Settings\n\nSettings()\n",
        encoding="utf-8",
    )

    # `python -c` adds the current directory to the start of `sys.path`, and
    # `cwd=tmp_path` below is that same directory -- no PYTHONPATH surgery
    # needed to make the throwaway package importable.
    result = _run_sweep(probe_package, cwd=tmp_path, timeout=60)
    assert result.returncode == 0, (
        f"positive-control subprocess crashed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    offenders, _tolerated = _classify_sweep_output(result.stdout)
    assert offenders, (
        "the sweep harness reported zero offenders for a module that "
        "constructs Settings() at import time -- without this control, "
        "Tests 1 and 2 could pass because the harness silently inherited a "
        "DATABASE_URL or resolved a .env, and nobody would know"
    )
    assert any(f"{probe_package}.offender" in offender for offender in offenders), (
        offenders
    )
    assert any("ValidationError" in offender for offender in offenders), offenders
