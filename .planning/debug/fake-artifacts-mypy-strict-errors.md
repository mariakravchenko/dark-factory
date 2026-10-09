---
status: investigating
trigger: "mypy --strict reports 3 pre-existing errors in tests/support/fake_artifacts.py, unrelated to and not caused by the in-scope-edit-missing-after-completed fix (test-only change to tests/integration/test_write_scope_enforcement.py); discovered as an adjacent-tier lint/type check during that session's fix-acceptance guardrail."
created: 2026-10-07T00:00:00Z
updated: 2026-10-07T00:00:00Z
origin: ".planning/debug/resolved/in-scope-edit-missing-after-completed.md (verification.adjacent_tests.lint_type)"
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

hypothesis: Not yet investigated — seeded from a sibling session's adjacent-tier check, not from a fresh investigation.
test: none run yet in this session
expecting: n/a
next_action: "Read tests/support/fake_artifacts.py lines ~270-290 and confirm the exact mypy error shape on clean HEAD, then determine whether the fix is a type-narrowing change at the call site or a signature change to the dict lookup being typed."

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: `uv run mypy --strict src tests` (or the project's configured mypy invocation) reports zero errors in tests/support/fake_artifacts.py.

actual: 3 errors, reproducing on a clean HEAD (not caused by any uncommitted change):
  - tests/support/fake_artifacts.py:276: error: Argument 1 to "get" of "dict" has incompatible type "tuple[Any, Any | None]"; expected "tuple[str, int]"
  - tests/support/fake_artifacts.py:278: error: Argument 1 to "get" of "dict" has incompatible type "tuple[Any, Any | None]"; expected "tuple[str, int]"
  - tests/support/fake_artifacts.py:286: error: Argument 1 to "get" of "dict" has incompatible type "tuple[Any, Any | None]"; expected "tuple[str, int]"

errors: see actual above — all three are the identical mypy error class (dict.get key-type mismatch: tuple[Any, Any | None] vs the dict's declared tuple[str, int] key type), at three call sites in the same file.

reproduction: "uv run mypy --strict tests/support/fake_artifacts.py (or the project's standard mypy invocation) on a clean checkout — no uncommitted changes needed to reproduce."

started: "Discovered 2026-10-07 during the fix-acceptance guardrail for debug session in-scope-edit-missing-after-completed, as an adjacent-tier lint/type check unrelated to that session's own change (tests/integration/test_write_scope_enforcement.py). Not a regression from that fix — reproduces independently on clean HEAD in a file that fix never touched."

## Eliminated
<!-- APPEND only - prevents re-investigating -->

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-10-07T00:00:00Z
  checked: "in-scope-edit-missing-after-completed.md verification.adjacent_tests.lint_type"
  found: "mypy --strict reports 3 PRE-EXISTING errors in tests/support/fake_artifacts.py:276/278/286 (reproduce in isolation at a clean HEAD, in a file this fix never touches)"
  implication: "unrelated pre-existing gap, worth its own session since pre-commit/CI run mypy strict and this will keep surfacing as noise on unrelated diffs until fixed."

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: ""
fix: ""
verification: ""
files_changed: []
