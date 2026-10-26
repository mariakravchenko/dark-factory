## 12-02: Pre-existing `mcp_transport.py` mypy import-not-found error (out of scope)

- **Observed:** `uv run mypy src/dark_factory` reports two `import-not-found` errors in `src/dark_factory/tools/mcp_transport.py` (`mcp.server`, `mcp.server.mcpserver.exceptions`).
- **Root cause:** the optional `mcp` extra (`pyproject.toml`'s `mcp = ["mcp>=2.2,<3"]`, Phase 6) is not installed in this execution sandbox (`uv pip show mcp` -> "Package(s) not found for: mcp") -- an environment/dependency-installation gap, not a code defect.
- **Scope:** Plan 12-02 touches `domain/views.py`, `events/reader.py` (unchanged), `observability/run_detail.py`, `observability/render.py`, `cli.py`, and three test files. None of those is `tools/mcp_transport.py`. All five files this plan modified pass `mypy` cleanly in isolation (`uv run mypy <files>` -> "Success: no issues found in 5 source files").
- **Action:** Not fixed (scope boundary). Deferred for a future environment-hygiene pass (`uv sync --all-extras --dev` in whatever runs this gate) or a `[[tool.mypy.overrides]]` entry scoping `module = "mcp.*"` to `ignore_missing_imports = true` if the extra is deliberately excluded from the default sync group.
  status: acknowledged

## 12-02: Pre-existing `ruff format` drift across 19 files (out of scope, carried from 11-10)

- **Observed:** `uv run ruff format --check .` reports 19 files would be reformatted (same files Phase 11's `11-10` deferred-items.md entry already named, e.g. `tests/unit/test_write_scope_guard_covers_bounce.py`, `tests/unit/test_webhook_resolve.py`, `tests/unit/test_trigger_carries_no_lifecycle_logic.py`). This plan's new file, `tests/db/test_events_reader_sees_every_bounce.py`, is independently confirmed already formatted after a local `ruff format` pass (`ruff format --check` on all eight of this plan's touched files -> "8 files already formatted").
- **Scope:** Plan 12-02 touches none of the 19 drifted files. They predate this plan (several trace to Phase 9/11) and are unrelated to this plan's change.
- **Action:** Not fixed (scope boundary), same disposition as `11-10`. Recorded here rather than silently reformatting 19 files this plan did not touch.
  status: acknowledged
