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
# Phase 6 (plan 06-01, D-02): `tools/native.py` is the per-worker-runtime
# native-tool translation *table* -- a design contract Phase 7+ adapters
# implement against, with no runtime consumer this phase
# (`tests/unit/test_native_tool_contract.py` proves that inertness
# structurally). Its whole job is naming `claude_code`/`copilot`/`hermes` as
# translation-table keys, which is data about a worker, exactly like
# `config/`'s already-exempt `worker: fake` YAML values -- never a per-worker
# branch in orchestrator "core" code, which is what this guard actually
# protects against.
_EXEMPT_FILES = {_SRC_ROOT / "tools" / "native.py"}
_FORBIDDEN_RUNTIME_NAMES = ("claude", "copilot", "hermes")


def _strip_comment(line: str) -> str:
    marker = line.find("#")
    return line if marker == -1 else line[:marker]


def _strip_claude_md_filename(line: str) -> str:
    """Remove ``claude.md`` occurrences (case already lowered by the caller)
    before the runtime-name scan.

    ``CLAUDE.md`` is one of the three fixed D-02 baseline document filenames
    (``dark_factory.context.builder.BASELINE_DOC_FILENAMES``) -- a repo
    convention, not a reference to the Claude Code worker runtime. Stripping
    the filename pattern first keeps the guard biting on the runtime name
    itself (``claude`` anywhere else) without a blanket per-directory
    exemption that would hide a genuine leak."""
    return line.replace("claude.md", "")


def _scanned_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path in _EXEMPT_FILES:
            continue
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
            haystack = _strip_claude_md_filename(_strip_comment(raw).lower())
            for name in _FORBIDDEN_RUNTIME_NAMES:
                if name in haystack:
                    offenders.append(
                        f"{path}:{lineno}: {raw.strip()!r} mentions {name!r}"
                    )
    assert not offenders, (
        "worker-runtime name leaked outside workers/ and config/:\n"
        + "\n".join(offenders)
    )
