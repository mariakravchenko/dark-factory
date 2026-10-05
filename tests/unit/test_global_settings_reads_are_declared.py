"""G-11-3's recurrence guard (QUAL-01): a declared inventory of every
process-global ``get_settings()`` call site under ``src/dark_factory/``.

This is the runtime analogue of ``tests/unit/test_no_mcp_import_in_core.py``-
style import-graph guards: an *import-time* property cannot see a call that
only happens on a conditionally-taken branch during test EXECUTION (the
exact shape of G-11-3 -- see ``.planning/debug/ci-unit-tier-settings-
validation-g-11-3.md``). This guard instead walks the AST of every module
under the package and asserts, by bidirectional set equality, that the
declared inventory below is EXACTLY the set of call sites the walk finds --
not a superset (which would let the inventory rot into a list of historical
facts the moment a call site is removed) and not a subset (which would let a
new hidden process-global settings read land invisibly, as the
``orchestrator/publish.py`` push-token read did).

This guard asserts nothing about whether a given call site is *correct*.
Its only claim is that every one of them is declared, so adding a new one is
a deliberate act with a written reason rather than an invisible one.
Deciding whether a declared site is actually *reachable* from a unit test
with no settings override is undecidable here by construction and is
plan 11-10's child-process run's job, not this guard's.

Each discovered call is keyed as ``"<path relative to the package
root>::<dotted qualname of the enclosing function/class>#<occurrence>"``.
The qualname is tracked via an explicit scope stack over
``FunctionDef``/``AsyncFunctionDef``/``ClassDef`` nodes (a plain
``ast.walk`` has no scope awareness and would key everything to the module,
collapsing the three distinct ``orchestrator/runner.py::_run_current_role``
reads into one and destroying exactly the distinction this inventory exists
to record). A call directly at module scope keys to ``"<module>"``. The
trailing ``#<occurrence>`` is a 1-based counter scoped to each
(path, qualname) pair, in source order -- never a line number (which rots
on any unrelated edit anywhere else in the file); the occurrence counter
only shifts when a ``get_settings()`` call is added or removed inside that
*same* enclosing scope, which is exactly the deliberate edit this guard
exists to flag.

Declared inventory, by category (20 entries across 12 modules):

* **Process entry points that legitimately own settings construction** --
  the CLI's redactor (``cli.py::_redactor``), the engine factory
  (``persistence/engine.py::build_engine``), the lease configuration read
  (``orchestrator/lease.py::run_lease``), the GitHub-sourced task loader's
  client construction (``input/loaders.py::_load_github``), and the
  orchestrator's default GitHub client factory
  (``orchestrator/runner.py::default_github_client_factory``).
* **The single lifecycle mutation path's redaction read** --
  ``persistence/mutations.py::_known_secrets``.
* **The structlog processor chain's two reads** -- the level filter at
  configure time (``logging.py::_configured_level``) and the redaction
  processor per event (``logging.py::_redaction_processor``).
* **The worker adapters' credential and timeout reads** --
  ``workers/claude_code.py::_base_argv``,
  ``workers/claude_code.py::ClaudeCodeWorker._spawn_and_parse``,
  ``workers/copilot.py::_base_argv``,
  ``workers/copilot.py::CopilotWorker._spawn_and_parse``,
  ``workers/hermes.py::HermesWorker._spawn_and_parse``, and the shared
  streamed-subprocess helper ``workers/cli_runtime.py::scrub_log_in_place``.
* **The git diff layer's redaction read** --
  ``git/diff.py::push_working_branch`` (the push-failure redaction path).
* **The reads reached on conditionally-taken branches inside
  ``orchestrator/runner.py``'s ``_run_current_role``** (five entries,
  ``#1``/``#2``/``#3``/``#4``/``#5``) -- this is the gap G-11-3 names. ``#1``
  was added by plan 12-07 (T-12-24, SEC-01/SEC-02): the artifact-content
  scrub read, inserted ahead of every pre-existing read in this function
  (immediately after the ``enforce_artifact_scope`` block, before
  ``collect_role_artifacts``), which shifted the four pre-existing reads
  from ``#1``-``#4`` to ``#2``-``#5`` in source order -- a renumbering, not
  a net-new gap, since the same four branches still read settings for the
  same reasons they always did. ``#4`` (formerly ``#3``) was added by plan
  12-03 (OBS-01, T-12-08): the clarification-comment body's redaction read,
  inserted ahead of the pre-existing GitHub-failure redaction read (now
  ``#5``, formerly ``#4``, in source order) inside the same
  ``ROLE_NEEDS_INPUT`` branch. A unit test that drives one of these
  branches must supply a settings override via one of the two idioms this
  repository already uses at 14 sites: Idiom A
  (``monkeypatch.setenv("DATABASE_URL", ...)`` + ``get_settings.cache_clear()``)
  or Idiom B (``monkeypatch.setattr(<module>, "get_settings", ...)``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "dark_factory"
_ACCESSOR_NAME = "get_settings"

_DECLARED_SETTINGS_READS: frozenset[str] = frozenset(
    {
        # Process entry points that legitimately own settings construction.
        "cli.py::_redactor#1",
        "persistence/engine.py::build_engine#1",
        "orchestrator/lease.py::run_lease#1",
        "input/loaders.py::_load_github#1",
        "orchestrator/runner.py::default_github_client_factory#1",
        # The single lifecycle mutation path's redaction read.
        "persistence/mutations.py::_known_secrets#1",
        # structlog processor chain: level filter at configure time, plus
        # the redaction processor fired per log event.
        "logging.py::_configured_level#1",
        "logging.py::_redaction_processor#1",
        # Worker adapters' credential and timeout reads.
        "workers/claude_code.py::_base_argv#1",
        "workers/claude_code.py::ClaudeCodeWorker._spawn_and_parse#1",
        "workers/copilot.py::_base_argv#1",
        "workers/copilot.py::CopilotWorker._spawn_and_parse#1",
        "workers/hermes.py::HermesWorker._spawn_and_parse#1",
        "workers/cli_runtime.py::scrub_log_in_place#1",
        # The git diff layer's redaction read.
        "git/diff.py::push_working_branch#1",
        # orchestrator/runner.py::_run_current_role -- five reads on
        # conditionally-taken branches, in source order: the artifact-content
        # scrub read (plan 12-07, T-12-24, SEC-01/SEC-02), quality-gate
        # timeout/known_secrets, the terminal-role artifact-commit push
        # token, the clarification-comment body redaction (plan 12-03,
        # OBS-01), and the clarification-failure redaction. A unit test that
        # drives any of these branches must supply a settings override via
        # Idiom A or B (see module docstring).
        "orchestrator/runner.py::_run_current_role#1",
        "orchestrator/runner.py::_run_current_role#2",
        "orchestrator/runner.py::_run_current_role#3",
        "orchestrator/runner.py::_run_current_role#4",
        "orchestrator/runner.py::_run_current_role#5",
    }
)


class _SettingsCallCollector(ast.NodeVisitor):
    """Walks one module's AST, recording every call to the process-global
    settings accessor, keyed by its enclosing function/class scope.

    Maintains an explicit scope stack over
    ``FunctionDef``/``AsyncFunctionDef``/``ClassDef`` nodes so a nested
    helper or method keys to its own dotted qualname rather than collapsing
    to the module. A call directly at module scope keys to ``"<module>"``.

    Matches the accessor by *name* -- both a bare ``ast.Call`` whose
    function is an ``ast.Name`` equal to the accessor name, and an
    ``ast.Attribute`` whose attribute is the accessor name (so a
    ``module.get_settings()`` style call cannot slip past). The accessor's
    own ``def get_settings():`` in ``config/settings.py`` is structurally a
    ``FunctionDef``, never an ``ast.Call``, so it is excluded by node type
    alone -- no filename special-casing required.
    """

    def __init__(self) -> None:
        self._scope: list[str] = []
        self._occurrence: dict[str, int] = {}
        self.found: list[str] = []

    def _qualname(self) -> str:
        return ".".join(self._scope) if self._scope else "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_accessor_call = (
            isinstance(func, ast.Name) and func.id == _ACCESSOR_NAME
        ) or (isinstance(func, ast.Attribute) and func.attr == _ACCESSOR_NAME)
        if is_accessor_call:
            qualname = self._qualname()
            self._occurrence[qualname] = self._occurrence.get(qualname, 0) + 1
            self.found.append(f"{qualname}#{self._occurrence[qualname]}")
        self.generic_visit(node)


def _discover_get_settings_calls(root: Path) -> frozenset[str]:
    """Discover every ``get_settings()`` call under every ``.py`` file
    beneath ``root``, keyed as
    ``"<path relative to root>::<qualname>#<occurrence>"``.
    """
    discovered: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        collector = _SettingsCallCollector()
        collector.visit(tree)
        rel = path.relative_to(root).as_posix()
        for key in collector.found:
            discovered.add(f"{rel}::{key}")
    return frozenset(discovered)


def test_declared_settings_reads_match_discovered_calls() -> None:
    """Bidirectional set equality: an undeclared new call site fails, and a
    declared entry that no longer exists (stale) also fails. One-directional
    containment would let the inventory silently rot into a list of
    historical facts that no longer describes the tree."""
    discovered = _discover_get_settings_calls(_PACKAGE_ROOT)

    undeclared = discovered - _DECLARED_SETTINGS_READS
    assert not undeclared, (
        "undeclared get_settings() call site(s) found under "
        f"{_PACKAGE_ROOT} -- a new process-global settings read needs a "
        "declared reason in this inventory's _DECLARED_SETTINGS_READS "
        "(file::enclosing-qualname#occurrence):\n  " + "\n  ".join(sorted(undeclared))
    )

    stale = _DECLARED_SETTINGS_READS - discovered
    assert not stale, (
        "declared settings-read inventory entry no longer exists in the "
        "source tree -- remove the stale entry from _DECLARED_SETTINGS_READS "
        "in this module:\n  " + "\n  ".join(sorted(stale))
    )


def test_twenty_entries_across_twelve_modules() -> None:
    """Pins the shape of the inventory this gap-closure plan established
    (19 entries), plus plan 12-07's own artifact-content-scrub read (20), so
    a future change to the count is a deliberate, reviewed edit."""
    assert len(_DECLARED_SETTINGS_READS) == 20
    modules = {key.split("::", 1)[0] for key in _DECLARED_SETTINGS_READS}
    assert len(modules) == 12


def test_no_declared_key_names_the_publish_module() -> None:
    """The machine-checked form of this gap-closure plan's Task 1 contract:
    it holds because the AST walk no longer finds a call in
    ``orchestrator/publish.py`` (Task 1 removed it), not because anything
    here filters it out."""
    assert not any(
        key.startswith("orchestrator/publish.py::") for key in _DECLARED_SETTINGS_READS
    )
    assert not any(
        key.startswith("orchestrator/publish.py::")
        for key in _discover_get_settings_calls(_PACKAGE_ROOT)
    )


def test_collector_finds_a_call_in_a_throwaway_tree(tmp_path: Path) -> None:
    """Positive control: without this, a collector that silently matched
    nothing would make every assertion above pass for the wrong reason.

    Writes a throwaway module with a module-scope call, a call inside a
    top-level function, and two calls inside a class method (proving the
    occurrence counter and the dotted-qualname scope stack both work), then
    proves the collector reports all four."""
    module = tmp_path / "offender.py"
    module.write_text(
        "get_settings()\n"
        "\n"
        "\n"
        "def outer():\n"
        "    return get_settings()\n"
        "\n"
        "\n"
        "class Thing:\n"
        "    def method(self):\n"
        "        settings_module.get_settings()\n"
        "        return get_settings()\n",
        encoding="utf-8",
    )

    discovered = _discover_get_settings_calls(tmp_path)

    assert discovered == frozenset(
        {
            "offender.py::<module>#1",
            "offender.py::outer#1",
            "offender.py::Thing.method#1",
            "offender.py::Thing.method#2",
        }
    )


def test_collector_ignores_the_accessors_own_definition(tmp_path: Path) -> None:
    """A ``def get_settings():`` is a function definition, not a call site --
    the walk must distinguish them structurally, never by special-casing a
    filename."""
    module = tmp_path / "settings.py"
    module.write_text(
        "def get_settings():\n    return Settings()\n",
        encoding="utf-8",
    )

    discovered = _discover_get_settings_calls(tmp_path)

    assert discovered == frozenset()
