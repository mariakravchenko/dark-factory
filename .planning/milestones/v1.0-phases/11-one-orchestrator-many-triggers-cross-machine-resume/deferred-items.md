## 11-07: Pre-existing environment-dependent test failure (out of scope)

- **Test:** `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder`
- **Observed:** Fails in this sandbox because a live `ANTHROPIC_API_KEY` and `claude` CLI binary are both present/configured, so `ClaudeCodeWorker.execute({})` makes a real call and returns `COMPLETED` instead of the test's expected `FAILED` (the test assumes no credential is configured in the test environment).
- **Scope:** Plan 11-07 touches only `README.md` and `tests/unit/test_resume_workflow_reference_doc.py`. This failure is unrelated to those files and pre-exists this plan's changes.
- **Action:** Not fixed (scope boundary). Deferred for a future plan/environment-hygiene pass to either mock the credential gate or isolate `ANTHROPIC_API_KEY` from this test's environment.
  status: acknowledged

## 11-10: Pre-existing `ruff format` drift across 19 files (out of scope)

- **Observed:** `uv run ruff format --check .` reports 19 files would be reformatted (e.g. `tests/unit/test_write_scope_guard_covers_bounce.py`, a webhook test file). This plan's own new file, `tests/unit/test_unit_tier_needs_no_database.py`, is independently confirmed already formatted (`ruff format --check tests/unit/test_unit_tier_needs_no_database.py` -> "1 file already formatted").
- **Scope:** Plan 11-10 touches only `tests/unit/test_unit_tier_needs_no_database.py`. The 19 drifted files predate this plan (e.g. `tests/unit/test_write_scope_guard_covers_bounce.py` traces to commit `932a278`, phase 9) and are unrelated to this plan's change.
- **Action:** Not fixed (scope boundary). The plan's project-wide `<verify>` command (`ruff format --check .`) will report non-zero for reasons entirely outside this plan's file; recorded here rather than silently reformatting 19 files this plan did not touch.
  status: acknowledged
