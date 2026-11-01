---
phase: quick
plan: 261101-ngp
subsystem: git, github
tags: [dead-code, security-hygiene, vulture, ruff]
status: complete
dependency-graph:
  requires: []
  provides: []
  affects:
    - src/dark_factory/git/__init__.py
    - src/dark_factory/github/client.py
tech-stack:
  added: []
  patterns:
    - "F401 is a whole-tree opt-in gate (--select F401), not covered by the project's [I, UP, B, SIM, RUF] ruff select list"
key-files:
  created: []
  modified:
    - src/dark_factory/git/__init__.py
    - src/dark_factory/github/client.py
decisions:
  - "Removed the dead `self._token`/`self._timeout` instance attributes on GitHubClient rather than keeping them for a future reader -- nothing reads them today and the stored token copy widened the credential's in-process inspection surface for zero benefit"
  - "Fixed an I001 isort violation (two blank lines instead of one) left by the Path-import deletion as a Rule 1 deviation, in its own atomic commit, after Task 2's whole-tree `ruff check .` gate caught it -- Task 1's own verify command only ran `ruff format --check`, which is blind to this lint rule"
metrics:
  duration: ~25min
  completed: 2026-11-01
actuals:
  tokens: 225
  tasks: 2
  commits: 3
  plan_head_before: 0f313c846959af228c5dfdcaa47e0df4eb28c519
---

# Quick Task 261101-ngp: Fix two dead-code findings from a vulture scan Summary

Removed an unused `pathlib.Path` import from `dark_factory.git`'s package `__init__.py`,
and deleted two dead constructor-assignment lines on `GitHubClient` that copied the
`token`/`timeout` parameters onto never-read private instance attributes -- one of
which held the raw, unwrapped GitHub credential for the client's entire lifetime.

## What Was Built

1. **`src/dark_factory/git/__init__.py`** -- deleted the unused `from pathlib import
   Path` import (line 58). The project's `[tool.ruff.lint] select` list
   (`["I", "UP", "B", "SIM", "RUF"]`) overrides ruff's default `F` rule set, which is
   why routine `ruff check .` never caught this and an explicit `--select F401` run
   was needed to surface it. `Path` was not in the package's 40-entry `__all__` and
   nothing in the repository imported it from this package, so the removal is a true
   dead-import cleanup, not a re-export break.

2. **`src/dark_factory/github/client.py`** -- deleted the two constructor statements
   `self._token = token` and `self._timeout = timeout` inside `GitHubClient.__init__`.
   Both parameters still reach their real consumers unchanged: the `_known_secrets`
   redaction-map fallback (`{token: "dark_factory_github_token"}`) and the `githubkit`
   construction call (`GitHub(token, timeout=float(timeout))`). This is not purely
   cosmetic: `self._token` held the raw, unwrapped value of
   `Settings.dark_factory_github_token` for the client's entire lifetime while nothing
   ever read it, widening where that credential could leak by inspection (`vars()`, an
   accidental `repr`, a debugger frame, a crash dump). Removing it narrows the
   in-process credential surface to only the frames that genuinely need it: the
   constructor-local parameter, the redaction-map value, and the `githubkit` client
   held on `_client`.

**Precondition re-run at execution time (Task 2):** `grep -rnE '\._(token|timeout)\b'
src/ tests/ scripts/` returned exactly two hits, both the assignment lines being
deleted (`src/dark_factory/github/client.py:131` and `:132`). No hit anywhere in
`tests/` or `scripts/` was an attribute access on a `GitHubClient` instance, matching
planning's finding exactly. No genuine reader existed, so the precondition was met
and the edit proceeded.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Collapsed a double blank line left by the Task 1 edit**
- **Found during:** Task 2's whole-tree `uv run ruff check .` verification gate
- **Issue:** Deleting the `Path` import line left two consecutive blank lines
  between `from __future__ import annotations` and `__all__ = [`. The plan's own
  Task 1 verify command only ran `uv run ruff format --check` (format-clean, since
  ruff-format does not enforce blank-line count between a lone import statement and
  following code) -- it never ran the project's own `ruff check .`, which enforces
  isort's I001 rule (part of the enabled `select` list) and wants exactly one blank
  line there, not two. This was a genuine, if narrow, lint violation introduced by
  Task 1's edit, not a pre-existing condition.
- **Fix:** Removed the extra blank line, leaving a single blank line between the
  `__future__` import and `__all__`.
- **Files modified:** `src/dark_factory/git/__init__.py`
- **Commit:** `728d11d`

**2. [Rule 3 - Blocking] Synced the optional `mcp` extra to unblock `mypy --strict`**
- **Found during:** Task 2's `uv run mypy --strict src/` verification gate
- **Issue:** `mypy --strict src/` failed with two `import-not-found` errors in
  `src/dark_factory/tools/mcp_transport.py` (Phase 6, wholly unrelated to this
  plan's two files) because the optional `mcp` extra declared in `pyproject.toml`
  was not installed in this worktree's virtualenv.
- **Fix:** Ran `uv sync --all-extras --dev` -- this installs an already-declared,
  already-locked optional dependency group (`mcp>=2.2,<3` plus transitive deps), not
  a new or unpinned package, so it is not the package-install exclusion under Rule 3.
  No `pyproject.toml` or `uv.lock` edit was needed or made.
- **Files modified:** none (environment-only; no repository file changed)
- **Commit:** n/a (no code change)

Three commits total rather than the plan's anticipated two, because of deviation #1
above. The plan's verification step 7 ("`git log --oneline -2` -> two commits")
should read "three commits" for this execution; the two task-described production
diffs are unaffected and each still lands in its own atomic commit.

## Verification Results

- `uv run ruff check --select F401 src/ tests/` -> **0 errors** (was 1).
- `uv run ruff check .` -> **clean** (whole tree).
- `uv run ruff format --check src/` -> **clean**, 76 files.
- `uv run mypy --strict src/` -> **clean**, 76 source files, after syncing the `mcp` extra.
- Negative gate -- comment-filtered count of `self._(token|timeout) =` assignments in
  `src/dark_factory/github/client.py`: **0** (was 2).
- Positive gates -- `GitHub(token, timeout=float(timeout))`: **1** occurrence;
  `{token: "dark_factory_github_token"}`: **1** occurrence.
- `import dark_factory.git` resolves all 40 `__all__` names; `Path` is no longer an
  attribute of the package.
- `uv run pytest -q tests/unit/test_git_worktree.py tests/unit/test_git_ownership_boundary.py tests/unit/test_git_lifecycle.py`
  -> 29 passed.
- `uv run pytest -q tests/unit/test_github_client.py tests/unit/test_load_github.py tests/unit/test_redaction_dark_factory_github_token.py tests/unit/test_github_ownership_boundary.py`
  -> 42 passed.
- `uv run pytest -q -m "unit or contract"` -> **830 passed**, 416 deselected
  (151.82s).
- `git diff --stat` from the plan's pre-execution HEAD to the tree touches exactly
  `src/dark_factory/git/__init__.py` and `src/dark_factory/github/client.py`, net 4
  deletions, 0 insertions -- `git diff --stat <base> -- tests/` is empty, confirming
  zero test files edited.
- `db` and `integration` tiers were not run, per the plan's own scoping (neither
  touches the removed attributes, both require the remote Neon instance).

## Known Stubs

None.

## Threat Flags

None -- this plan removed surface rather than adding any. The threat register's
T-NGP-01 (information disclosure via the dead credential attribute) is closed by
Task 2's deletion; T-NGP-02/T-NGP-03/T-NGP-04 were all proven non-regressed by the
positive/negative grep gates and the full `__all__` resolution check above.

## Self-Check: PASSED

- FOUND: `src/dark_factory/git/__init__.py` (no `Path` import, single blank line
  before `__all__`)
- FOUND: `src/dark_factory/github/client.py` (no `_token`/`_timeout` assignments)
- FOUND commit `cd7e8d2` (Task 1: drop unused pathlib.Path import)
- FOUND commit `728d11d` (deviation: collapse double blank line)
- FOUND commit `e031a31` (Task 2: stop retaining the GitHub token as an instance attribute)
