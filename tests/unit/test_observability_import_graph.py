"""The ``observability`` package-wide events-free sweep (Plan 12-01, Task 3,
OBS-03 / STATE-06).

``tests/unit/test_status_import_graph.py`` roots its walk at the single
module ``dark_factory.observability.status``. This module widens that to
**every** ``*.py`` module under ``src/dark_factory/observability/`` --
load-bearing because this phase adds sibling modules to that package
(``render.py`` already; ``run_detail.py`` in a later plan), and a guard
that names one module by hand silently stops covering the package the
moment a new file lands. A directory sweep covers them on arrival with no
edit.

``dark_factory.events.reader`` is architecturally **permitted** to read
``run_events`` while nothing under ``observability/`` is: the status read
path is the one that decides whether an operator should resume a run, and a
read path that *can* fold the append-only log will eventually be asked to,
at which point the log has silently become the control state. A renderer
that formats rows someone else already read cannot do that; a reader that
never feeds the status path cannot either -- which is exactly why
``events/reader.py`` lives outside this package and outside this sweep.

Reuses ``test_status_import_graph.py``'s closure-walk helpers verbatim
(imported, not copied) so there is only one import-closure walker in the
test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_status_import_graph import (
    _dark_factory_imports,
    _events_hits,
    _module_to_path,
    _transitive_closure,
)

pytestmark = pytest.mark.unit

_OBSERVABILITY_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "dark_factory" / "observability"
)


def _discover_observability_modules() -> list[str]:
    """Every ``dark_factory.observability.<name>`` module on disk, sorted."""
    return sorted(
        f"dark_factory.observability.{path.stem}"
        for path in _OBSERVABILITY_DIR.glob("*.py")
        if path.stem != "__init__"
    )


def test_every_observability_module_is_swept_and_none_reaches_events() -> None:
    modules = _discover_observability_modules()

    # Non-vacuity: a broken glob that discovers nothing must fail loudly,
    # not pass trivially.
    assert len(modules) >= 2, (
        f"expected at least 2 modules under {_OBSERVABILITY_DIR}, found {modules}"
    )

    offenders: dict[str, list[str]] = {}
    for module in modules:
        assert _module_to_path(module) is not None, f"{module} does not exist on disk"
        hits = _events_hits(_transitive_closure(module))
        if hits:
            offenders[module] = hits

    assert not offenders, (
        f"the following dark_factory.observability modules transitively import "
        f"dark_factory.events: {offenders}"
    )


def test_the_discovered_module_set_matches_the_package_directory_listing() -> None:
    modules = _discover_observability_modules()
    on_disk = sorted(
        f"dark_factory.observability.{p.stem}"
        for p in _OBSERVABILITY_DIR.glob("*.py")
        if p.stem != "__init__"
    )
    assert modules == on_disk
    names = {m.rsplit(".", 1)[-1] for m in modules}
    assert {"render", "status"} <= names


def test_the_walk_actually_resolves_transitive_imports() -> None:
    """Sanity: the closure walk really follows imports -- the identical
    non-vacuity device ``test_status_import_graph.py`` uses, re-run here so
    this module's own use of the imported helpers is proven, not assumed.
    ``dark_factory.persistence.mutations`` provably reaches the events
    module, so the guard would catch a regression."""
    closure = _transitive_closure("dark_factory.persistence.mutations")
    assert _events_hits(closure), (
        "the transitive walk failed to reach dark_factory.events from a module "
        "that provably imports it"
    )


def test_events_reader_is_outside_the_swept_package() -> None:
    """``dark_factory.events.reader`` is the one new module that deliberately
    imports the events table's model -- it must live outside
    ``dark_factory.observability`` (and therefore outside this sweep's
    discovered set), never inside it."""
    assert "dark_factory.events.reader" not in _discover_observability_modules()
    reader_path = _module_to_path("dark_factory.events.reader")
    assert reader_path is not None
    assert _OBSERVABILITY_DIR not in reader_path.parents


def test_the_import_helper_genuinely_parses_imports() -> None:
    """Sanity companion to the closure walk: ``_dark_factory_imports`` on the
    render module's own file must be non-trivial (it imports at least the
    domain views module), confirming the reused helper is wired correctly
    here, not just in its origin module."""
    render_path = _module_to_path("dark_factory.observability.render")
    assert render_path is not None
    found = _dark_factory_imports(render_path)
    assert any(m.startswith("dark_factory.domain.views") for m in found)
