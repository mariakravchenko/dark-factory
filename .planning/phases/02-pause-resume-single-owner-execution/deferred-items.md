# Deferred items — Phase 02

Out-of-scope discoveries logged during execution, not fixed (SCOPE BOUNDARY).

## 02-03

- **`ruff format --check .` reports 9 unformatted files**, all outside this
  plan's scope: `.claude/gsd-core/templates/*.md` (untracked GSD framework
  files) and `.planning/phases/01-*/*-SUMMARY.md` (pre-existing Phase 1 docs
  with Python code fences that `ruff format` now wants to rewrap). Zero files
  under `src/` or `tests/` are unformatted. Not caused by 02-03; left untouched.
  `ruff check .` and `ruff format --check src tests` both pass clean.
