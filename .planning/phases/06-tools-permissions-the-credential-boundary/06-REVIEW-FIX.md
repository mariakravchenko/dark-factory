---
phase: 06-tools-permissions-the-credential-boundary
fixed_at: 2026-09-19T06:40:14Z
review_path: .planning/phases/06-tools-permissions-the-credential-boundary/06-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-09-19T06:40:14Z
**Source review:** .planning/phases/06-tools-permissions-the-credential-boundary/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (1 critical/blocker, 2 warnings; `fix_scope: critical_warning` — the 2 INFO findings, IN-01 pydantic default_factory nit and IN-02 mcp version-pin drift, are out of scope and untouched)
- Fixed: 3
- Skipped: 0

All fixes were applied inside an isolated git worktree (`gsd-reviewfix/06-86740`, based off `gsd/phase-01-walking-skeleton-one-durable-run`) and fast-forwarded back onto the branch on completion, per this agent's transactional worktree protocol.

## Fixed Issues

### CR-01: `roles_dir` is not containment-checked, letting a role definition be read from outside the repo root

**Files modified:** `src/dark_factory/config/loader.py`, `tests/unit/test_repo_config_schema.py`
**Commit:** `4790430`
**Applied fix:** Mirrored the sibling `instructions:` guard exactly. `roles_dir` is now resolved with `.resolve()` immediately after being joined to `root`, and checked with `is_relative_to(root)`, raising `ConfigError` (`"...roles_dir escapes the repo root: ..."`) if it escapes. As defense-in-depth against a future relaxation of the `workflow.roles` enum-membership validator (the only reason `role_name` is currently safe), the same `.resolve()` + `is_relative_to(root)` check was also applied to each computed `role_path` before it is opened. Added two new unit tests to `tests/unit/test_repo_config_schema.py`: `test_roles_dir_escaping_the_repo_root_is_rejected` (reproduces the reviewer's exact `roles_dir: ../outside` repro and asserts `ConfigError` is raised, matching `"roles_dir escapes the repo root"`) and `test_roles_dir_within_the_repo_root_still_loads` (sanity check that a well-behaved `roles_dir` is unaffected). Verified: `uv run pytest tests/unit/test_repo_config_schema.py -q` (13 passed) and the full `tests/unit -m unit` suite (431 passed, 1 skipped, 1 deselected at that point in the sequence). `mypy`/`ruff` clean on the changed files.

### WR-01: `shell_execute`'s timeout-kill path can raise an unhandled `ProcessLookupError`

**Files modified:** `src/dark_factory/tools/env.py`, `tests/unit/test_shell_execute.py`
**Commit:** `258f1a9`
**Applied fix:** Wrapped the `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` call in the `subprocess.TimeoutExpired` handler with `contextlib.suppress(ProcessLookupError)` (ruff's SIM105 rule, part of this project's enabled `SIM` ruleset, prefers `contextlib.suppress` over a bare `try/except/pass`, so the fix uses that form rather than the review's literal `try/except: pass` snippet). Added `test_timeout_kill_race_where_the_child_already_exited_does_not_raise` to `tests/unit/test_shell_execute.py`, which monkeypatches `dark_factory.tools.env.os.killpg` to raise `ProcessLookupError` (simulating the race) against a short-lived child (`sleep 2` past a `timeout=1`, chosen so the test doesn't leave an orphan process since the mocked `killpg` no longer actually kills anything) and asserts `shell_execute` still returns a typed `ShellResult(timed_out=True, exit_code=None)` rather than letting the exception propagate. Verified: `uv run pytest tests/unit/test_shell_execute.py -q` (9 passed) and the full `tests/unit -m unit` suite. `mypy`/`ruff` clean on the changed files (ruff initially flagged SIM105 on the first `try/except/pass` draft; fixed to `contextlib.suppress`).

### WR-02: The MCP transport reshapes `CapabilityDeniedError` but not `UnknownCapabilityError`, losing the diagnostic asymmetrically

**Files modified:** `src/dark_factory/tools/mcp_transport.py`, `tests/unit/test_mcp_adapter.py`
**Commit:** `5c87e6b`
**Applied fix:** `_tool`'s `except CapabilityDeniedError` clause now also catches `UnknownCapabilityError` (`except (CapabilityDeniedError, UnknownCapabilityError) as exc: raise ToolError(str(exc)) from exc`), imported alongside `CapabilityDeniedError` from `dark_factory.tools`. Updated the docstring to document the new reshaping and why (config-bug class must never be confused with a denial, per this package's own error-hierarchy docstring). Added two tests to `tests/unit/test_mcp_adapter.py`: `test_granted_but_unregistered_capability_is_reshaped_not_opaque` (drives a granted-but-never-registered capability through a real in-memory `Client`/`MCPServer` round trip and asserts the surfaced message is no longer the SDK's bare opaque `"Error executing tool test.missing"`) and `test_unknown_capability_error_message_shape_matches_the_mcp_surface` (sanity check mirroring the existing `CapabilityDeniedError` message-shape test). I empirically verified the *before* state by temporarily reverting `mcp_transport.py` and driving the same scenario directly against a real `mcp` install: without the fix, the surfaced message is exactly `'Error executing tool test.missing'` with zero diagnostic content; with the fix it becomes `"Error executing tool test.missing: 'test.missing'"`, i.e. `UnknownCapabilityError`'s own message is now included. The test asserts against that exact regression (`message != "Error executing tool test.missing"`) rather than a weaker "contains X" check, so it would fail again if the reshaping were removed. Required installing the optional `mcp` extra into this worktree's venv (`uv sync --extra mcp --all-groups`) since `tests/unit/test_mcp_adapter.py` otherwise auto-skips via `pytest.importorskip("mcp")` — this is a project-recognized, deliberate skip condition (A-06-08), not a gap this fix introduced. Verified: `uv run pytest tests/unit/test_mcp_adapter.py -q` (10 passed, none skipped) and the full `tests/unit -m unit` suite (442 passed once `mcp` was installed). `mypy`/`ruff` clean on the changed files.

## Skipped Issues

None — all three in-scope findings (1 critical, 2 warnings) were fixed.

## Verification Notes

- Ran, after all three fixes were committed: `uv run mypy src/dark_factory` → `Success: no issues found in 63 source files`; `uv run ruff check .` → `All checks passed!`.
- Ran the full non-`db` unit suite after all fixes: `uv run pytest -q -m unit` → `442 passed, 321 deselected`.
- Did **not** run the `db`- or `integration`-marked test suites (e.g. `tests/db/`, `tests/integration/test_config_drives_pipeline.py`, `tests/integration/test_config_error_exit_code.py`) — these require a live Postgres connection via `pg_url`/`DATABASE_URL`, and this session's secret-read-guard hook blocks sourcing `.env`. Per the established convention documented in 06-01 through 06-04's `SUMMARY.md` files, db-tier verification of these fixes (in particular CR-01's containment check, which is also exercised indirectly by `tests/db/test_bad_config_no_orphan_run.py` and `tests/integration/test_config_error_exit_code.py`) is deferred to the user to run locally against a real Neon/Postgres connection.
- No logic-bug ambiguity: all three fixes are structural/defensive (a containment check mirroring an existing pattern, an exception-suppression around a documented race, and widening an existing except clause to a sibling error class) rather than judgment calls about business logic, so none are flagged `"fixed: requires human verification"` — normal `"fixed"` status applies to all three.
- Out of scope per `fix_scope: critical_warning`: IN-01 (`RoleDefinition.permissions`'s pydantic default is a shared instance, not a `default_factory`) and IN-02 (`mcp` version-pin drift between `pyproject.toml` and `.claude/CLAUDE.md`'s stack table) were left untouched, as instructed.

---

_Fixed: 2026-09-19T06:40:14Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
