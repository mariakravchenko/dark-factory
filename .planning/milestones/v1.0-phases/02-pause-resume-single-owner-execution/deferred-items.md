# Deferred items — Phase 02

Out-of-scope discoveries logged during execution, not fixed (SCOPE BOUNDARY).

## 02-03

- **`ruff format --check .` reports 9 unformatted files**, all outside this
  plan's scope: `.claude/gsd-core/templates/*.md` (untracked GSD framework
  files) and `.planning/phases/01-*/*-SUMMARY.md` (pre-existing Phase 1 docs
  with Python code fences that `ruff format` now wants to rewrap). Zero files
  under `src/` or `tests/` are unformatted. Not caused by 02-03; left untouched.
  `ruff check .` and `ruff format --check src tests` both pass clean.
  status: acknowledged

## 02-06

- **Multi-node pipelines reuse the first node's `role_executions` row.**
  `orchestrator/runner._enter_first_role` inserts a `RUNNING` row only for the
  *first* node; `_run_current_role` on a `ROLE_COMPLETED` signal for a
  non-terminal transition returns the next role's status but inserts no new
  row, so the second node's step updates the first node's `role_executions`
  row (its `.role` stays `"BA"` while `runs.current_role` moves to the second
  node). Surfaced while building `tests/db/test_pause_mechanism_generic.py`'s
  two-node pipeline. **Out of scope for 02-06** — Phase 1's pipeline has always
  been single-node and Phase 3 makes the pipeline configuration-driven; that is
  where a per-node `RoleExecutionWrite(mode="insert")` belongs. It does **not**
  affect this plan's claim: both nodes still reach the pause through the one
  `Signal.ROLE_NEEDS_INPUT` branch with no per-role code, which is why
  `test_the_two_nodes_pause_through_structurally_identical_code` projects the
  role-execution row identity (and `.role`) out of the comparison. Not fixed;
  no production change made.

  **Resolved in Phase 4 (04-03).** `orchestrator/runner._enter_role` now
  generalises `_enter_first_role`'s insert-then-run split to every role after
  the first: entering role K+1 is its own committed step that inserts a fresh
  `RUNNING` row for role K+1 (before any worker call), so a multi-role
  pipeline gets one `role_executions` row per role, matching STATE-03. Also
  closed as WINDOWS.md ledger item #6.
  status: acknowledged
