"""GIT-06: the orchestrator core and the webhook receiver cannot reach each
other -- turning plan 10-04's module-docstring promises (D-01/D-02) into a
mechanical, self-sanity-tested guard (Phase 10, plan 10-05, T-10-27/T-10-28/
T-10-29).

Three directions, three guards:

* **D-01 (this module never reached BY the core).** The transitive
  ``dark_factory.*`` import closure of five core roots --
  ``orchestrator.runner``, ``orchestrator.answers``, ``orchestrator.lifecycle``,
  ``workflows.pipeline`` and ``cli`` (the composition root) -- must never
  contain ``dark_factory.webhook`` or any submodule of it. The closure walk
  (``_module_to_path`` / ``_dark_factory_imports`` / ``_transitive_closure``)
  is reused, not reinvented, from ``tests/unit/test_orchestrator_no_live_config_read.py``
  and ``tests/unit/test_status_import_graph.py``, which already establish
  this exact idiom in this codebase.

* **D-02 (the receiver can never REACH the pipeline).** Phrased on names, not
  on the closure: ``answers.py`` legitimately imports ``RunNotFoundError``
  from ``orchestrator.runner``, so the webhook package's *transitive* closure
  does contain ``runner`` -- a closure-exclusion assertion here would be false
  on landing. The real invariant is that no module under
  ``src/dark_factory/webhook/`` ever imports or calls the two names that
  actually run the pipeline, ``advance``/``drive``, plus a narrow allowlist of
  the webhook package's own *direct* ``dark_factory.*`` imports so a future
  module reaching further into the orchestrator is a visible, deliberate
  widening rather than a silent one.

* **Genuinely optional.** Mirrors ``tests/unit/test_no_mcp_import_in_core.py``'s
  own mechanism exactly (that file's docstring is explicit it carries no
  subprocess or skip-marked check, only the import-graph proof) -- rather
  than inventing a second mechanism, this module reuses the same
  structural argument: none of the five core roots' closures reach a module
  that itself imports the third-party ``starlette``/``uvicorn`` packages the
  ``webhook`` extra installs, so uninstalling that extra cannot break any of
  them.

Every guard below ships with the self-sanity tests this codebase's guard
idiom requires (T-10-29): a positive control proving the closure walk
resolves real imports, synthetic violating/non-violating sources fed to the
name-level detector, and a synthetic module proven to fail the direct-import
allowlist check.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PKG = "dark_factory"
_WEBHOOK_ROOT = _SRC_ROOT / _PKG / "webhook"
_FORBIDDEN_WEBHOOK = f"{_PKG}.webhook"
_CORE_ROOT_MODULES = (
    "dark_factory.orchestrator.runner",
    "dark_factory.orchestrator.answers",
    "dark_factory.orchestrator.lifecycle",
    "dark_factory.workflows.pipeline",
    "dark_factory.cli",
)
# A module every core root's closure genuinely reaches (via `cli.py`'s own
# direct import) -- the positive control proving the walk resolves real
# imports rather than always returning an empty set.
_KNOWN_PRESENT_IN_CLOSURE = "dark_factory.persistence.mutations"

_PIPELINE_NAMES = {"advance", "drive"}

# The webhook package's own direct (non-transitive) dark_factory.* imports,
# read from the actual Phase 10 source (plans 10-01/10-04): the answer
# submission path, the lease it takes around that submission, the two reads
# `resolve_issue_comment`/`github_pending_interaction` need, the GitHub
# client used only for `authenticated_login` (the self-comment filter, never
# a write), and settings. Anything beyond this set is a deliberate widening
# someone must add here in a reviewable diff.
_WEBHOOK_DIRECT_ALLOWED = {
    "dark_factory.config.settings",
    "dark_factory.github.client",
    "dark_factory.orchestrator.answers",
    "dark_factory.orchestrator.lease",
    "dark_factory.persistence.engine",
    "dark_factory.persistence.repositories",
}
_THIRD_PARTY_EXTRA_NAMES = ("starlette", "uvicorn")


# --------------------------------------------------------------------------- #
# Shared closure-walk idiom (reused verbatim from
# test_orchestrator_no_live_config_read.py / test_status_import_graph.py)
# --------------------------------------------------------------------------- #


def _module_to_path(mod: str) -> Path | None:
    rel = mod.replace(".", "/")
    for candidate in (_SRC_ROOT / f"{rel}.py", _SRC_ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _dark_factory_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _PKG or alias.name.startswith(_PKG + "."):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue  # this codebase uses no relative imports
            module = node.module or ""
            if module == _PKG or module.startswith(_PKG + "."):
                found.add(module)
                for alias in node.names:
                    found.add(f"{module}.{alias.name}")
    return found


def _transitive_closure(root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_to_path(module)
        if path is None:
            continue  # a `from pkg.mod import name` symbol, not a module
        stack.extend(_dark_factory_imports(path) - seen)
    return seen


def _webhook_hits(closure: set[str]) -> list[str]:
    return sorted(
        m
        for m in closure
        if m == _FORBIDDEN_WEBHOOK or m.startswith(_FORBIDDEN_WEBHOOK + ".")
    )


# --------------------------------------------------------------------------- #
# D-01: the core's transitive closure never reaches dark_factory.webhook
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("root_module", _CORE_ROOT_MODULES)
def test_core_closure_never_reaches_the_webhook_package(root_module: str) -> None:
    assert _module_to_path(root_module) is not None, f"{root_module} not on disk"
    offenders = _webhook_hits(_transitive_closure(root_module))
    assert not offenders, (
        f"{root_module}'s transitive dark_factory import closure reaches the "
        f"webhook package: {offenders}"
    )


def test_the_closure_walk_resolves_real_imports() -> None:
    # Sanity: dark_factory.cli (the composition root) provably imports
    # persistence.mutations -- if this failed, the walk above would be
    # silently resolving nothing and every root's "no webhook" result would
    # be meaningless.
    closure = _transitive_closure("dark_factory.cli")
    assert _KNOWN_PRESENT_IN_CLOSURE in closure, (
        f"the transitive walk failed to reach {_KNOWN_PRESENT_IN_CLOSURE} from "
        "dark_factory.cli, which provably imports it -- the walk is not "
        "resolving real imports"
    )


# --------------------------------------------------------------------------- #
# D-02: the webhook package never imports or calls advance/drive, and its
# direct dark_factory.* imports stay inside a narrow named allowlist
# --------------------------------------------------------------------------- #


def _name_level_violations(source: str, filename: str) -> list[str]:
    """Every import of, or call to, the bare names ``advance``/``drive`` in
    ``source`` -- the mechanical shape of "can this module start the
    pipeline", regardless of where the name ultimately resolves. An alias
    (``import ... as go``) does not launder the import: what is checked is
    the *imported* name, before any ``as``."""
    tree = ast.parse(source, filename=filename)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom | ast.Import):
            for alias in node.names:
                if alias.name in _PIPELINE_NAMES:
                    out.append(f"{filename}:{node.lineno} imports {alias.name}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _PIPELINE_NAMES
        ):
            out.append(f"{filename}:{node.lineno} calls {node.func.id}(...)")
    return out


def _webhook_modules() -> list[Path]:
    return sorted(_WEBHOOK_ROOT.rglob("*.py"))


def test_no_webhook_module_imports_or_calls_advance_or_drive() -> None:
    offenders: list[str] = []
    for path in _webhook_modules():
        rel = str(path.relative_to(_SRC_ROOT / _PKG))
        offenders.extend(
            _name_level_violations(path.read_text(encoding="utf-8"), rel)
        )
    assert not offenders, (
        "advance/drive import or call found under src/dark_factory/webhook/:\n  "
        + "\n  ".join(offenders)
    )


def _direct_dark_factory_modules(path: Path) -> set[str]:
    """Only the *module* dotted paths a file directly imports (never the
    compound ``module.symbol`` strings ``_dark_factory_imports`` above also
    collects for closure-walking purposes) -- what the direct-import
    allowlist actually constrains."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _PKG or alias.name.startswith(_PKG + "."):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue
            module = node.module or ""
            if module == _PKG or module.startswith(_PKG + "."):
                found.add(module)
    return found


def _is_allowed_webhook_direct_import(module: str) -> bool:
    if module == _FORBIDDEN_WEBHOOK or module.startswith(_FORBIDDEN_WEBHOOK + "."):
        return True  # the package's own internal structure
    return module in _WEBHOOK_DIRECT_ALLOWED


def test_webhook_packages_direct_imports_stay_inside_the_named_allowlist() -> None:
    offenders: list[str] = []
    for path in _webhook_modules():
        rel = str(path.relative_to(_SRC_ROOT / _PKG))
        for module in sorted(_direct_dark_factory_modules(path)):
            if not _is_allowed_webhook_direct_import(module):
                offenders.append(f"{rel} imports {module}")
    assert not offenders, (
        "src/dark_factory/webhook/ reaches beyond its named direct-import "
        f"allowlist ({sorted(_WEBHOOK_DIRECT_ALLOWED)}):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    ("source", "expected_lineno"),
    [
        pytest.param(
            "from dark_factory.orchestrator.runner import drive\n",
            1,
            id="plain-drive-import",
        ),
        pytest.param(
            "from dark_factory.orchestrator.runner import advance as go\n",
            1,
            id="aliased-advance-import-does-not-launder",
        ),
    ],
)
def test_synthetic_violating_imports_are_detected_with_the_right_line(
    source: str, expected_lineno: int
) -> None:
    violations = _name_level_violations(source, "synthetic.py")
    assert violations, f"expected a violation for: {source!r}"
    assert any(f":{expected_lineno} " in v for v in violations), (
        f"violation line number mismatch: {violations}"
    )


def test_synthetic_bare_call_to_drive_is_detected() -> None:
    source = "def handler():\n    return drive(run_id)\n"
    violations = _name_level_violations(source, "synthetic.py")
    assert violations, f"expected a violation for: {source!r}"
    assert ":2 " in violations[0]


def test_a_docstring_mention_of_drive_is_not_a_violation() -> None:
    source = (
        '"""This module must never import advance or drive."""\n' "x = 1\n"
    )
    assert _name_level_violations(source, "synthetic.py") == []


def test_the_direct_import_allowlist_check_fails_on_a_synthetic_widening() -> None:
    assert not _is_allowed_webhook_direct_import("dark_factory.orchestrator.runner"), (
        "the allowlist check passed a synthetic direct import of "
        "dark_factory.orchestrator.runner -- the guard cannot detect a "
        "future widening"
    )


# --------------------------------------------------------------------------- #
# Genuinely optional: no core root's closure reaches a module importing the
# webhook extra's third-party packages (mirrors test_no_mcp_import_in_core.py)
# --------------------------------------------------------------------------- #


def _is_third_party_extra_name(name: str) -> bool:
    return name in _THIRD_PARTY_EXTRA_NAMES or any(
        name.startswith(f"{prefix}.") for prefix in _THIRD_PARTY_EXTRA_NAMES
    )


def _third_party_extra_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_third_party_extra_name(alias.name):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue
            module = node.module or ""
            if _is_third_party_extra_name(module):
                found.add(module)
    return found


@pytest.mark.parametrize("root_module", _CORE_ROOT_MODULES)
def test_core_closure_never_imports_starlette_or_uvicorn(root_module: str) -> None:
    closure = _transitive_closure(root_module)
    offenders: list[str] = []
    for module in sorted(closure):
        path = _module_to_path(module)
        if path is None:
            continue
        hits = _third_party_extra_imports(path)
        if hits:
            offenders.append(f"{module} imports {sorted(hits)}")
    assert not offenders, (
        f"{root_module}'s transitive dark_factory import closure reaches a "
        f"starlette/uvicorn import, so the webhook extra is not genuinely "
        f"optional: {offenders}"
    )


def test_the_detector_would_catch_webhook_app_importing_starlette() -> None:
    # Positive control (T-10-29): webhook/app.py genuinely imports starlette
    # -- if this detector found nothing there, it would be broken.
    path = _module_to_path("dark_factory.webhook.app")
    assert path is not None, "dark_factory.webhook.app is absent from disk"
    hits = _third_party_extra_imports(path)
    assert hits, (
        "dark_factory.webhook.app provably imports starlette, but "
        "_third_party_extra_imports found nothing -- the detector is broken "
        "and this guard would pass over a real violation"
    )
