"""Structural guard (T-11-02, 11-CONTEXT.md D-03): ``dispatch_github_token``
is absent from every worker-facing environment builder, and is read by only
a named, deliberately small set of modules.

Mirrors ``tests/unit/test_no_environ_copy.py``'s idiom: walk the tree,
collect offenders into a list, assert an empty list with a message naming
file and line so a failure is actionable rather than a bare ``False``.

Two assertions:

1. **The allowlist is untouched by this credential.** ``WORKER_ENV_ALLOWLIST``
   (``dark_factory.tools.env``) -- imported and inspected as a real value,
   not grepped -- contains no member named ``DISPATCH_GITHUB_TOKEN``, and
   that module's own source contains no occurrence of the identifier
   ``dispatch_github_token`` at all. Importing the tuple and checking
   membership is the primary, stronger assertion; the source scan is the
   secondary belt.

2. **A named, exact reader set.** Every module under ``src/dark_factory/``
   whose AST contains an attribute access named ``dispatch_github_token`` is
   collected into a set of module paths, asserted equal to
   ``_EXPECTED_READERS`` below -- not a subset check, not a superset check,
   an exact-set equality, so a future module quietly starting to read the
   field is a loud, actionable test failure rather than a silent widening.

   ``_EXPECTED_READERS`` has **two** entries, not the single
   ``dark_factory/github/client.py`` entry a narrower reading of this guard
   might expect:

   * ``dark_factory/github/client.py`` -- ``GitHubClient.for_dispatch`` is
     the single frame that unwraps the credential from ``SecretStr`` to
     build a real dispatch-scoped client (D-03's core invariant).
   * ``dark_factory/webhook/app.py`` -- ``build_app``'s own startup
     diagnostic (Phase 11, Task 1) reads
     ``_startup_settings.dispatch_github_token`` purely to decide whether to
     log ``webhook.build_app.missing_dispatch_github_token`` at process
     startup, mirroring the pre-existing ``github_token`` /
     ``github_webhook_secret`` startup checks in the same block. This is a
     legitimate second reader: the receiver process's own diagnostic, not a
     worker-facing surface, and not the credential-unwrapping frame D-03
     cares about (that frame stays exactly ``for_dispatch``). A future phase
     that legitimately adds a *third* reader must update this constant
     deliberately, per this guard's own design intent, rather than deleting
     the test.

   ``src/dark_factory/config/settings.py``'s own *declaration* of the field
   (``dispatch_github_token: SecretStr | None = None``) is an
   ``ast.AnnAssign`` target, not an attribute access, and so does not appear
   in the reader set -- this is stated explicitly so a future reader does
   not "fix" a non-bug by trying to add ``settings.py`` here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dark_factory.tools.env import WORKER_ENV_ALLOWLIST

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ATTR_NAME = "dispatch_github_token"

# See the module docstring, assertion 2, for why this set has two entries.
_EXPECTED_READERS: frozenset[str] = frozenset(
    {
        "dark_factory/github/client.py",
        "dark_factory/webhook/app.py",
    }
)


def test_worker_env_allowlist_has_no_dispatch_github_token_member() -> None:
    assert "DISPATCH_GITHUB_TOKEN" not in WORKER_ENV_ALLOWLIST, (
        "WORKER_ENV_ALLOWLIST gained a DISPATCH_GITHUB_TOKEN entry -- this "
        "credential must never reach a worker subprocess (T-11-02, D-03)"
    )


def test_tools_env_module_source_never_names_the_dispatch_credential() -> None:
    env_module_path = _SRC_ROOT / "tools" / "env.py"
    assert env_module_path.is_file(), f"{env_module_path} not on disk"
    source = env_module_path.read_text(encoding="utf-8")
    assert _ATTR_NAME not in source, (
        f"{env_module_path} contains the identifier {_ATTR_NAME!r} -- this "
        "module builds worker-facing environments and must never reference "
        "the dispatch-only credential (T-11-02, D-03)"
    )


def _attribute_access_readers() -> set[str]:
    readers: set[str] = set()
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == _ATTR_NAME:
                readers.add(str(path.relative_to(_SRC_ROOT.parent)))
                break
    return readers


def test_exactly_the_named_modules_read_dispatch_github_token() -> None:
    readers = _attribute_access_readers()
    assert readers == set(_EXPECTED_READERS), (
        f"the set of modules reading .{_ATTR_NAME} changed: "
        f"expected {sorted(_EXPECTED_READERS)}, found {sorted(readers)} -- "
        "if a new reader is legitimate, update _EXPECTED_READERS "
        "deliberately; if not, this is the credential-boundary violation "
        "T-11-02 guards against"
    )


def test_settings_declaration_is_an_annassign_not_an_attribute_access() -> None:
    """Sanity for the module docstring's own claim: `settings.py`'s field
    declaration must not appear in the reader set because it is an
    `ast.AnnAssign` target, not an `ast.Attribute` access."""
    settings_path = _SRC_ROOT / "config" / "settings.py"
    tree = ast.parse(
        settings_path.read_text(encoding="utf-8"), filename=str(settings_path)
    )
    annassign_targets = {
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert _ATTR_NAME in annassign_targets, (
        f"expected {settings_path} to declare {_ATTR_NAME!r} as an "
        "AnnAssign target -- if the field was refactored, update this "
        "sanity check and re-verify the reader-set claim above"
    )
    attribute_accesses = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert _ATTR_NAME not in attribute_accesses, (
        f"{settings_path} now contains an attribute access named "
        f"{_ATTR_NAME!r}, not just the AnnAssign declaration -- this "
        "module would need to join _EXPECTED_READERS"
    )
