---
phase: 09-independent-quality-gate-bounded-feedback-loops
reviewed: 2026-09-23T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/dark_factory/orchestrator/quality_gate.py
  - src/dark_factory/orchestrator/runner.py
  - tests/db/test_write_scope_enforced_on_bounce.py
  - tests/support/fake_artifacts.py
  - tests/unit/test_quality_gate.py
  - tests/unit/test_write_scope_guard_covers_bounce.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-09-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found (Info only — no Critical or Warning findings)

## Summary

This is an independent re-review of the two gap-closure commits (`d276985`
"feat(09-04)" and `4ce341f` "feat(09-05)") that claim to close CR-01 and
CR-02 from the prior 09-REVIEW.md. I read both fixes against their diffs
(`git show d276985`, `git show 4ce341f`), traced the surrounding control
flow in `runner.py` and `quality_gate.py` line-by-line, cross-checked the
called-into modules (`git/scope.py`'s `enforce_write_scope`, `events/
redaction.py`'s `redact`, `persistence/mutations.py`'s `apply_transition`),
and ran the unit test suite plus `ruff`/`mypy --strict` against all six
files. The db-tier regression test could not be executed in this sandbox
(no reachable PostgreSQL 17 — `pytest.UsageError`, the documented fail-loud
behavior, not a defect), so its correctness was verified by static trace
against `runner.py` rather than by execution.

**CR-01 (ROLE-05 write-scope guard not covering `Signal.ROLE_BOUNCED`):
genuinely fixed, not superficial.** The guard at `runner.py:1238` now reads
`if signal in (Signal.ROLE_COMPLETED, Signal.ROLE_BOUNCED):` instead of
`if signal is Signal.ROLE_COMPLETED:`. This is reached exactly once, after
`transition()` has not yet been called, so a `ROLE_BOUNCED` signal set by
`_bounce_or_fail` earlier in the same function is visible to the guard
before `transition(state, signal, pipeline)` runs at line 1269 — the
downgrade to `ROLE_FAILED` on a violation happens before routing is
computed, not after. The `WriteScopeViolation` handler correctly clears
`counter_increments` and `bounce_reason` (so a downgraded bounce cannot
silently spend a retry-budget iteration that never happened and cannot
leave a non-empty `counter_increments` paired with `ROLE_FAILED`), while
deliberately leaving `gate_events` untouched (the gate's own commit already
landed durably on the working branch by the time this check runs, so its
audit events remain true statements). Two independent regression tests back
this: `tests/unit/test_write_scope_guard_covers_bounce.py` is an AST-level
structural guard (exactly one guard call site; its condition literally
names both `ROLE_COMPLETED` and `ROLE_BOUNCED`; its exception handler
assigns all five required targets and does not touch `gate_events`), and
`tests/db/test_write_scope_enforced_on_bounce.py` drives a real `drive()`
run where QA writes outside its declared `write_scope` on an attempt whose
verdict also FAILs under an unexhausted cap — the exact shape that pre-fix
would have chosen `ROLE_BOUNCED` and skipped enforcement entirely. Its
seven assertions are discriminating (zero `ROLE_BOUNCED` events, the stale
counter cleared to 0, exactly one `role_executions` row per role, the
planted file actually reverted from disk, no `"counter"` key on the
`RUN_FAILED` payload) rather than merely corroborating. All unit tests
pass; `ruff check` and `mypy --strict` are clean on both touched files.

**CR-02 (quality_gate.py persisting the configured command string
unredacted): genuinely fixed, not superficial.** `run_quality_gate` now
redacts `command` through the same `redact(..., known_secrets=known_secrets)`
call already used for `stdout`/`stderr`, before constructing
`GateCommandResult` (`quality_gate.py:176`). Critically, the *original*
unredacted `command` string is still what `shlex.split` and
`shell_execute` operate on (the redaction happens only when building the
persisted result object), so the gate still authenticates/executes
correctly — only the durable artifact is scrubbed. The redacted `command`
is deliberately never passed through `_cap_output` (only `stdout`/`stderr`
are capped), matching the updated docstring's stated rationale. I confirmed
there is no other leak path for the raw command text: the
`QUALITY_GATE_STARTED`/`_PASSED`/`_FAILED` event payloads carry only
`command_count`, `exit_codes`, and the artifact `path`, never the command
text itself, and nothing in `runner.py` logs `gate_commands` directly (any
`structlog` call would additionally go through the global redaction
processor as defense-in-depth, but this path doesn't even reach one).
`tests/unit/test_quality_gate.py` has an explicit, previously-missing test
for exactly this defect —
`test_a_known_secret_value_in_the_configured_command_is_redacted` — plus a
second test that proves the secret never reaches the *written artifact
file* on disk (`test_a_known_secret_in_a_command_never_reaches_the_written_
artifact`), which is the strongest possible proof for a defect framed
around "committing a credential to git history." All quality-gate unit
tests pass; `ruff check` and `mypy --strict` are clean.

**No new Critical or Warning-level regressions found** in either fix or in
the surrounding code they touch. I traced the interaction between the two
post-worker `ROLE_COMPLETED`/`ROLE_BOUNCED` blocks, the terminal-role
gate/bounce block, `enforce_write_scope`'s git-level revert mechanism
(`git/scope.py`), and `apply_transition`'s counter/event persistence
(`persistence/mutations.py`) and found the ordering and clearing logic
internally consistent. Two minor, non-blocking Info items are noted below.

## Info

### IN-01: Redundant `str(...)` wrapping around an already-`str` `redact()` result

**File:** `src/dark_factory/orchestrator/quality_gate.py:172-176`
**Issue:** `redact()` is typed to return `Any` (it recurses over
heterogeneous JSON-shaped values), but for a `str` input it always returns
`_redact_str(...)`, which is guaranteed to be a `str`. The three call sites
(`stdout`, `stderr`, and the new `command` redaction) all wrap the call in
`str(...)`. This is behaviorally harmless (round-trips a `str` through
`str()`) and not required for `mypy --strict` (an `Any` value is assignable
to a `str`-typed parameter without a cast), so it is a pure style nit
carried over from the pre-existing `stdout`/`stderr` pattern into the new
`command` line — not something CR-02 introduced independently, but worth
cleaning up now that `command` is being touched too.
**Fix:** Drop the redundant `str(...)` casts, or narrow `redact()`'s
signature with an `@overload` for `str -> str` if the cast is meant to
satisfy a stricter mypy configuration than what's currently enforced:
```python
command=redact(command, known_secrets=known_secrets),
```

### IN-02: DB-tier CR-01 regression test covers only the QA-verdict-FAIL bounce path, not the quality-gate-FAIL bounce path

**File:** `tests/db/test_write_scope_enforced_on_bounce.py`
**Issue:** Both the QA-verdict-FAIL branch (`runner.py:1086-1104`) and the
quality-gate-FAIL branch (`runner.py:1138-1170`) funnel through the exact
same `_bounce_or_fail` call shape and the exact same widened
`enforce_write_scope` guard at line 1238, so this is low residual risk —
but the db-tier test only exercises the QA-verdict-FAIL branch (QA's own
`verdict.json` is FAIL-shaped via `QA_VERDICT_FAIL_FILES`, so the quality
gate never even runs per the short-circuit at line 1086-1092). A second
scenario where QA's verdict PASSes but a configured `quality_gate.commands`
entry fails, with an out-of-scope write planted on that same bounced
attempt, would fully corroborate the symmetric branch rather than relying
on code-reading to infer it behaves identically.
**Fix:** Add a second `tests/db/` scenario (or parametrize the existing
one) that drives QA to a PASS verdict, configures a failing
`quality_gate.commands` entry, plants an out-of-scope write on that same
attempt, and asserts the identical FAILED-with-no-bounce outcome.

---

_Reviewed: 2026-09-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
