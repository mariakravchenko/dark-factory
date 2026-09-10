"""ORCH-03 guard: the pipeline is data from the snapshot, not code.

No string literal equal to a ``RunStatus`` role value -- ``BA``, ``ARCHITECTURE``,
``DEVELOPMENT``, ``QA``, ``VERIFYING``, ``PUBLISHING`` -- may appear anywhere
under ``src/dark_factory/orchestrator/`` or in
``src/dark_factory/workflows/pipeline.py``. A role name baked into orchestrator
code is a per-role branch by another name; the orchestrator must learn the role
sequence only from ``runs.workflow`` via ``pipeline_from_snapshot``.

Docstrings are exempt (they explain the constraint); every other ``str``
constant is in scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ROLE_VALUES = frozenset(
    {"BA", "ARCHITECTURE", "DEVELOPMENT", "QA", "VERIFYING", "PUBLISHING"}
)


def _scanned_files() -> list[Path]:
    files = sorted((_SRC_ROOT / "orchestrator").rglob("*.py"))
    files.append(_SRC_ROOT / "workflows" / "pipeline.py")
    return files


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """``id()`` of every constant that is a module/class/function docstring."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _role_literal_hits(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    exempt = _docstring_node_ids(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in _ROLE_VALUES
            and id(node) not in exempt
        ):
            hits.append(f"{filename}:{node.lineno}: {node.value!r}")
    return hits


def test_no_runstatus_role_name_literal_in_orchestrator_or_pipeline() -> None:
    offenders: list[str] = []
    scanned = _scanned_files()
    assert scanned, f"no files to scan under {_SRC_ROOT}"
    for path in scanned:
        assert path.is_file(), f"expected {path} to exist"
        offenders.extend(
            _role_literal_hits(path.read_text(encoding="utf-8"), str(path))
        )
    assert not offenders, "RunStatus role-name literal in orchestrator/pipeline:\n" + (
        "\n".join(offenders)
    )


def test_the_scan_would_catch_a_role_literal() -> None:
    """Sanity: a bare ``role = "ARCHITECTURE"`` (not a docstring) is one hit."""
    hits = _role_literal_hits('role = "ARCHITECTURE"\n', "<inline>")
    assert hits == ["<inline>:1: 'ARCHITECTURE'"]
