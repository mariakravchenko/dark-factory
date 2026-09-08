"""Guard (WORK-03 / T-01-06): no real agent-runtime name outside ``workers/`` and ``config/``.

The three lowercase runtime identifiers from the ``.claude/CLAUDE.md`` "Invoking
the agent CLIs" table must never appear in orchestrator or workflow code. The
registry factory lookup plus ``WorkerCapabilities`` are the only ways the core
learns anything about a worker.
"""

import pathlib

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_EXEMPT_TOP_LEVEL = {"workers", "config"}
_FORBIDDEN_RUNTIME_NAMES = ("claude", "copilot", "hermes")


def _strip_comment(line: str) -> str:
    marker = line.find("#")
    return line if marker == -1 else line[:marker]


def _scanned_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(_SRC_ROOT)
        if relative.parts and relative.parts[0] in _EXEMPT_TOP_LEVEL:
            continue
        files.append(path)
    return files


def test_source_tree_has_files_to_scan() -> None:
    assert _scanned_files(), f"expected .py files under {_SRC_ROOT}"


def test_no_real_worker_runtime_name_leaks_into_the_core() -> None:
    offenders: list[str] = []
    for path in _scanned_files():
        for lineno, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            haystack = _strip_comment(raw).lower()
            for name in _FORBIDDEN_RUNTIME_NAMES:
                if name in haystack:
                    offenders.append(
                        f"{path}:{lineno}: {raw.strip()!r} mentions {name!r}"
                    )
    assert not offenders, (
        "worker-runtime name leaked outside workers/ and config/:\n"
        + "\n".join(offenders)
    )
