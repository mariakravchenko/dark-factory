"""GIT-03: ``githubkit`` is reachable only from a small, explicitly named and
reasoned set of modules under ``src/dark_factory/`` -- turning plan 10-01's
module-docstring promise into a mechanical, self-sanity-tested guard
(Phase 10, plan 10-05, T-10-26/T-10-29/T-10-30).

Mirrors ``tests/unit/test_git_ownership_boundary.py``'s AST-walk idiom
exactly: a module-level ``_ALLOWED`` set, a ``_modules()`` generator skipping
it, a ``_violations(path)`` function returning ``"file:line reason"`` strings
so a failure names the offending file and line, and a companion sanity test
proving the guard would trip on a synthetic violation -- a guard that cannot
detect a violation proves nothing (T-10-29).

The allowed set has one entry:

* ``src/dark_factory/github/client.py`` -- the one wrapper (D-03). Owns
  every outbound GitHub REST call, the single ``SecretStr`` token unwrap
  frame, and redact-before-raise error handling.

Reading the AST rather than the raw text is load-bearing here exactly as it
is in the git precedent: ``github/client.py``'s own module docstring names
``githubkit`` repeatedly, and a text-based guard would either trip on that
or have to be weakened to accommodate it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ALLOWED = {
    _SRC_ROOT / "github" / "client.py",
}


def _modules(allowed: set[Path] = _ALLOWED) -> Iterator[Path]:
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path in allowed:
            continue
        yield path


def _detect_violations(source: str, filename: str) -> list[str]:
    """The reusable detector: every ``githubkit`` / ``githubkit.*`` import in
    ``source`` (module-level or function-scoped -- ``ast.walk`` visits every
    node regardless of nesting, so a deferred import is still caught), never
    a string that merely mentions the name inside a docstring or a comment
    (the AST holds no node for those)."""
    tree = ast.parse(source, filename=filename)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "githubkit" or alias.name.startswith("githubkit."):
                    out.append(f"{filename}:{node.lineno} imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "githubkit" or module.startswith("githubkit."):
                out.append(f"{filename}:{node.lineno} imports from {module}")
    return out


def _violations(path: Path) -> list[str]:
    rel = str(path.relative_to(_SRC_ROOT))
    return _detect_violations(path.read_text(encoding="utf-8"), rel)


def test_githubkit_is_imported_only_from_the_named_allowed_modules() -> None:
    offenders: list[str] = []
    for path in _modules():
        offenders.extend(_violations(path))
    assert not offenders, (
        "githubkit imports found outside the named allowed set "
        f"({sorted(p.relative_to(_SRC_ROOT).as_posix() for p in _ALLOWED)}):\n  "
        + "\n  ".join(offenders)
    )


def test_every_allowed_module_would_itself_trip_the_walk() -> None:
    # Sanity: each allowed entry is meaningful only if it actually imports
    # githubkit -- an allowlist entry that doesn't need to be there would
    # silently widen the guard to nothing.
    for path in sorted(_ALLOWED):
        assert _violations(path), (
            f"{path} is in the allowed set but the walk found no githubkit "
            "import there -- this entry does not need to exist"
        )


def test_every_allowed_path_exists_on_disk() -> None:
    # A guard whose allowlist points at a renamed file silently stops
    # constraining that file (T-10-30).
    assert _ALLOWED, "the allowed set must not be empty"
    for path in sorted(_ALLOWED):
        assert path.is_file(), f"allowed-set entry does not exist on disk: {path}"


def test_running_the_walk_with_an_emptied_allowlist_finds_violations() -> None:
    # T-10-29: a walk that matches nothing when the allowlist is emptied is
    # not a walk at all -- it must be proven capable of failing.
    offenders: list[str] = []
    for path in _modules(allowed=set()):
        offenders.extend(_violations(path))
    assert offenders, (
        "emptying the allowed set produced zero violations -- the walk is "
        "not actually detecting githubkit imports"
    )


@pytest.mark.parametrize(
    ("source", "expected_lineno"),
    [
        pytest.param("import githubkit\n", 1, id="module-level-import"),
        pytest.param("from githubkit import GitHub\n", 1, id="from-import"),
        pytest.param(
            "from githubkit.webhooks import verify\n", 1, id="from-submodule-import"
        ),
        pytest.param(
            "def f() -> None:\n    import githubkit\n",
            2,
            id="function-scoped-import",
        ),
    ],
)
def test_synthetic_violating_forms_are_detected_with_the_right_line(
    source: str, expected_lineno: int
) -> None:
    violations = _detect_violations(source, "synthetic.py")
    assert violations, f"expected a violation for: {source!r}"
    assert any(f":{expected_lineno} " in v for v in violations), (
        f"violation line number mismatch: {violations}"
    )


def test_a_docstring_or_comment_mention_is_not_a_violation() -> None:
    source = (
        '"""This module wraps githubkit -- see githubkit.exception for errors."""\n'
        "\n"
        "# import githubkit would go here if we needed it\n"
        "x = 1\n"
    )
    assert _detect_violations(source, "synthetic.py") == []
