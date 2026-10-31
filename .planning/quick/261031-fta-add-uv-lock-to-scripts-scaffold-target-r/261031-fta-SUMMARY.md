---
phase: quick
plan: 261031-fta
subsystem: scripts/scaffold
tags: [scaffold, gitignore, uv, write-scope, app-int-live-failure]
status: complete
dependency-graph:
  requires:
    - GITIGNORE_CONTENT (scripts/scaffold_target_repo.py)
    - build_contents (scripts/scaffold_target_repo.py)
    - DEFAULT_QUALITY_GATE_COMMANDS (scripts/scaffold_target_repo.py, 261031-cp4)
  provides:
    - "uv.lock entry in the generated .gitignore template"
    - "two new regression tests in tests/unit/test_scaffold_target_repo.py"
  affects:
    - any future scaffold run against a target repository whose QA role (write_scope ['tests/**']) must survive a uv run quality-gate command
tech-stack:
  added: []
  patterns:
    - "exact-membership .gitignore entry assertion (never substring search), proven both on the raw template constant and through the build_contents wiring"
    - "shared _gitignore_entries(text) helper reused by both new tests, so there is a single definition of what counts as an entry"
key-files:
  created: []
  modified:
    - scripts/scaffold_target_repo.py
    - tests/unit/test_scaffold_target_repo.py
decisions:
  - "The entry is a bare `uv.lock` line with no explanatory comment -- `_gitignore_missing_entries()` prints every non-empty template line to a deployer under its NOTE message, and a prose comment there would misread as a path"
  - "Pattern is `uv.lock`, not `*.lock` and not `/uv.lock` -- a bare filename matches at any depth, which is correct for a target repo with nested packages, without over-ignoring unrelated lockfiles"
  - "Position (immediately after `.venv/`) is not asserted by the tests -- only membership is, since git pattern order only matters for negation patterns and this template has none"
actuals:
  tokens: 4200
  tasks: 2
  commits: 1
  plan_head_before: "faf67db933147bdbcea311b2ccec517dc41fd000"
metrics:
  duration: "~20min"
  completed: "2026-10-31"
---

# Quick Task 261031-fta: Add uv.lock to scripts/scaffold_target_repo.py's scaffold target repo's generated .gitignore Summary

`scripts/scaffold_target_repo.py`'s generated `.gitignore` now ignores `uv.lock`, closing a live `app-int` CI failure where QA (`write_scope: ['tests/**']`) failed with `wrote outside its configured write_scope ... ['uv.lock']` even after QA's own agent deleted the file, because every default `uv run` quality-gate command regenerates it in the worktree root and the generated `.gitignore` never listed it.

## What Was Built

**Task 1 (tracer, TDD).** Extended `tests/unit/test_scaffold_target_repo.py` (the module `261031-cp4` created) with a shared `_gitignore_entries(text)` helper and two new tests, written first and confirmed RED (both failed with `uv.lock` absent from the parsed entry set), then added the fix and confirmed GREEN:

- `test_gitignore_content_ignores_uv_lock`: asserts the parsed entry set of `GITIGNORE_CONTENT` contains the exact entry `uv.lock` -- exact-line membership, so a `*.lock` or `nested/uv.lock` variant would not satisfy it.
- `test_build_contents_gitignore_entry_carries_uv_lock`: calls `build_contents(...)` with this repository's own defaults and asserts the returned `GITIGNORE_RELATIVE_PATH` mapping value's parsed entries also contain `uv.lock` -- proving the constant actually reaches the emitted file content, not just the template source.

The fix itself: one line added to `GITIGNORE_CONTENT` in `scripts/scaffold_target_repo.py`, inserted immediately after `.venv/`:

```
.env
.venv/
uv.lock
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.dark-factory/runs/
.DS_Store
```

No comment line was added (decision 1), no existing entry was reordered or removed, and `src/dark_factory/git/scope.py` was not touched -- confirmed by `git diff --name-only HEAD -- src/` returning empty both before and after the commit. All five pre-existing tests in the module, plus `261031-cp4`'s `Install uv` step and its three guards, are byte-identical.

**Task 2 (verification only, no code or test change).** Ran the real scaffold script as a subprocess into a throwaway directory (`--target ... --github-owner example-org --github-repo example-repo --yes`); it exited zero and wrote a `.gitignore` that, read back from disk, contains both `uv.lock` and `.dark-factory/runs/` among its nine entries. Then ran the repository's lint/format/test gates:

- `uv run ruff check .` -- clean (`All checks passed!`).
- `uv run ruff format --check scripts/scaffold_target_repo.py tests/unit/test_scaffold_target_repo.py` -- clean (`2 files already formatted`).
- `uv run pytest -q -m "unit or contract"` -- **891 passed, 430 deselected, 0 failed**. (One-time environment step, not a code fix: `uv sync --all-extras --dev` was run first to install the optional `webhook` extra (`starlette`/`uvicorn`), which this sandbox's prior `uv run` invocations had not yet synced -- without it, three webhook test modules fail to import. This mirrors the identical environment note recorded in `261031-cp4-SUMMARY.md`.)

`mypy` was deliberately not run -- CI's `Types (mypy)` step targets `src/dark_factory` only, and no file under `src/` is in this plan's scope.

## Deviations from Plan

None. The plan's three decisions (no comment, bare `uv.lock` filename, no position assertion) were implemented exactly as specified. No file under `src/` was modified. `261031-cp4`'s workflow-template work (`RESUME_WORKFLOW_TEMPLATE`, `RUN_WORKFLOW_TEMPLATE`, their three tests) was not touched.

## Verification Results

- `uv run pytest tests/unit/test_scaffold_target_repo.py -q` → **7 passed** (5 pre-existing from `261031-cp4`, 2 new), 0 failed.
- `uv run python -c "from scripts.scaffold_target_repo import GITIGNORE_CONTENT; ..."` → `GITIGNORE_OK ['.env', '.venv/', 'uv.lock', '__pycache__/', '*.pyc', '.pytest_cache/', '.ruff_cache/', '.dark-factory/runs/', '.DS_Store']` (nine entries, `uv.lock` present, all eight prior entries intact).
- `git diff --name-only HEAD -- src/` → empty.
- A real `scripts/scaffold_target_repo.py --target <tmpdir> --github-owner example-org --github-repo example-repo --yes` invocation exited zero and wrote all 13 scaffold files; the `.gitignore` read back from disk contains `uv.lock` and `.dark-factory/runs/`.
- `uv run ruff check .` → `All checks passed!`.
- `uv run ruff format --check scripts/scaffold_target_repo.py tests/unit/test_scaffold_target_repo.py` → `2 files already formatted`.
- `uv run pytest -q -m "unit or contract"` → `891 passed, 430 deselected, 0 failed`.
- `git status --porcelain` → empty (changes confined to the two files already committed in Task 1; this task made none).
- <human-check>The real proof is a live CI run: re-scaffold (or hand-add the `uv.lock` line to) a target repository's `.gitignore`, dispatch a run, and confirm QA (`write_scope: ['tests/**']`) reaches its verdict instead of failing with `wrote outside its configured write_scope ... ['uv.lock']`. Record the run URL and QA's real outcome. `app-int` itself was already fixed directly in that repository (per `STATE.md`'s Blockers/Concerns entry for `261030-o5x`/`261030-op0`/`261031-c01`), so this check needs either a fresh scaffold or a different target repo. Deferred to `/gsd-verify-work`.</human-check>

## Known Stubs

None — no stub patterns, placeholder text, or unwired data sources were introduced by this change.

## Threat Flags

None — the added entry was already fully assessed in the plan's own `<threat_model>` (T-FTA-01 through T-FTA-05, T-FTA-SC), all dispositioned `accept` or `mitigate` with no open gaps; nothing in this plan's implementation diverged from what the threat model covers. In particular T-FTA-04 (scope creep into enforcement code) is closed: `git diff --name-only HEAD -- src/` is empty both before and after the commit.

## Self-Check: PASSED

- `scripts/scaffold_target_repo.py` — FOUND
- `tests/unit/test_scaffold_target_repo.py` — FOUND
- Commit `92948c6` (Task 1: feat, template edit + two new tests) — FOUND in `git log --all --oneline`
- `plan_head_before` (`faf67db933147bdbcea311b2ccec517dc41fd000`) to `HEAD` → `git rev-list --count` reports `1`, matching the single task commit (Task 2 made no code or test change).
