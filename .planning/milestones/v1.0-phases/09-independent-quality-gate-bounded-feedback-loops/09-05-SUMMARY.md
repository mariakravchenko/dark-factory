---
phase: 09-independent-quality-gate-bounded-feedback-loops
plan: 05
subsystem: orchestrator
tags: [quality-gate, redaction, security, gap-closure]

requires:
  - dark_factory.events.redaction.redact
  - dark_factory.orchestrator.quality_gate.GateCommandResult
provides:
  - "GateCommandResult.command redacted against known_secrets before construction"
affects:
  - dark_factory.orchestrator.quality_gate

actuals:
  tokens: 1000
  tasks: 1
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Redact at model-construction time, before the field ever exists in an unredacted form, so every downstream reader (artifact file, git commit, next role's RoleContext) inherits the redacted form from one choke point."

key-files:
  created: []
  modified:
    - src/dark_factory/orchestrator/quality_gate.py
    - tests/unit/test_quality_gate.py

key-decisions:
  - "Applied redact(command, known_secrets=known_secrets) to the command= argument of GateCommandResult, identical in shape to the existing stdout/stderr redaction calls, per 09-REVIEW.md's CR-02 prescription."
  - "Left patterns=True (default) on the command redaction, so the D-15 pattern table (Authorization: Bearer, GitHub/postgres token shapes) also scrubs credentials never registered in Settings — defence in depth."
  - "Did not apply _cap_output to the command string — only to stdout/stderr — since a configured command is a short operator-authored line and truncating it would destroy the identifying information the artifact exists to hand the Developer."
  - "Fixed the docstring's citation of the project's Security constraint from '.claude/CLAUDE.md' to bare 'CLAUDE.md' after a genuine RED discovered mid-GREEN: the directory-prefixed form tripped tests/unit/test_no_worker_name_leak.py's runtime-name guard because '.claude/' still contains the substring 'claude' even after the guard's claude.md-filename exemption strips the trailing 'claude.md'. Matches the existing bare-'CLAUDE.md' citation convention already used in tools/env.py and context/builder.py."

requirements-completed: [GATE-04]

coverage:
  - id: COV-1
    description: "A credential registered in known_secrets and embedded in a configured command's literal text is absent from GateCommandResult.command and replaced by [redacted:<label>]"
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_a_known_secret_value_in_the_configured_command_is_redacted"
        status: pass
    human_judgment: false
  - id: COV-2
    description: "That same redaction survives serialisation: the written verification/quality_gate.json contains no literal occurrence of the secret"
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_a_known_secret_in_a_command_never_reaches_the_written_artifact"
        status: pass
    human_judgment: false
  - id: COV-3
    description: "A command with no known secret and no D-15 pattern match round-trips byte-identically — the existing ordering test keeps passing unmodified"
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "tests/unit/test_quality_gate.py::test_two_passing_commands_yield_pass_with_two_entries_in_order"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-09-23
status: complete
---

# Phase 9 Plan 05: Redact the configured quality-gate command string before it is persisted Summary

Closes gap CR-02: a credential an operator embeds directly in a `.dark-factory.yaml`
`quality_gate.commands` entry (e.g. `curl -H "Authorization: Bearer <token>"`) is now redacted
against `known_secrets` — with the D-15 pattern table also applied — before `GateCommandResult`
is constructed, so it never reaches the model field, the written `verification/quality_gate.json`
bytes, or the git commit that carries that file onto the run's working branch.

## Performance

- **Duration:** ~25min
- **Started:** 2026-09-23
- **Completed:** 2026-09-23
- **Tasks:** 1/1
- **Files modified:** 2

## Accomplishments

- `run_quality_gate`'s `GateCommandResult(...)` call now redacts the configured `command` string
  via `redact(command, known_secrets=known_secrets)`, mirroring the existing `stdout`/`stderr`
  redaction exactly (same function, same keyword, same `str(...)` coercion).
- Widened `run_quality_gate`'s docstring to name all three redacted fields and record why the
  command string belongs in the set: `verification/quality_gate.json` is force-added and
  committed onto the run's working branch, so a credential written there — unlike a transient log
  line — is permanent and unrecallable.
- Two new unit tests prove the property end to end: one asserts the secret is absent from
  `result.commands[0].command`, the other asserts it is absent from the text of the written
  `verification/quality_gate.json`.
- Confirmed genuine RED before implementing: both new tests failed on the assertion (secret
  present in `.command` / in the written bytes), not on a collection/import error.
- Verified the existing `test_two_passing_commands_yield_pass_with_two_entries_in_order` — which
  asserts `.command` equality against the configured strings — still passes unmodified, proving
  the change does not over-redact commands carrying no secret.

## Task Commits

1. `a78f8f2` — test(09-05): add failing test for command-string redaction (RED)
2. `4ce341f` — feat(09-05): redact configured command string before persisting gate result (GREEN)

No separate REFACTOR commit was needed — the GREEN implementation was already minimal (one
argument change plus a docstring update).

## Files Created/Modified

- `src/dark_factory/orchestrator/quality_gate.py` — modified. `command=command` →
  `command=str(redact(command, known_secrets=known_secrets))` inside `run_quality_gate`'s loop;
  widened docstring paragraph. No change to `GateCommandResult`/`QualityGateResult` shape, no new
  import (`redact` was already imported), no new symbol.
- `tests/unit/test_quality_gate.py` — modified. Two new test functions added immediately after
  `test_a_known_secret_value_in_stdout_is_redacted`:
  `test_a_known_secret_value_in_the_configured_command_is_redacted` and
  `test_a_known_secret_in_a_command_never_reaches_the_written_artifact`. No existing test modified
  or removed; both reuse the module's existing `_py` helper.

## Decisions Made

See `key-decisions` in frontmatter above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring citation tripped the worker-runtime-name leak guard**
- **Found during:** Task 1, first full-suite verify run after the GREEN implementation
- **Issue:** The widened docstring paragraph cited the project's Security constraint as
  ``.claude/CLAUDE.md``. `tests/unit/test_no_worker_name_leak.py`'s guard lowercases each line,
  strips the literal `claude.md` filename pattern (an explicit, deliberate exemption for citing
  the doc by name), but the directory component `.claude/` still contains the substring `claude`
  after that strip — so the guard correctly flagged it as a worker-runtime-name leak
  (`tests/unit/test_no_real_worker_runtime_name_leaks_into_the_core` failed with
  `1 failed, 672 passed`).
- **Fix:** Changed the citation from `` ``.claude/CLAUDE.md`` `` to bare `` ``CLAUDE.md`` ``,
  matching the existing citation convention already used elsewhere in this same source tree
  (`tools/env.py:105`, `tools/native.py:29`, `context/builder.py:73`) — none of which prefix the
  filename with a directory.
- **Files modified:** `src/dark_factory/orchestrator/quality_gate.py` (docstring only)
- **Verification:** Re-ran `tests/unit/test_no_worker_name_leak.py` and
  `tests/unit/test_quality_gate.py` (16 passed), then the full
  `pytest -m "unit or contract" -q --tb=short` suite (673 passed, 0 failed).
- **Commit:** folded into `4ce341f` (the docstring was still uncommitted at the time the guard
  failure was discovered; no separate fix commit was needed).

**Total deviations:** 1 auto-fixed (Rule 1 — bug caused by this plan's own docstring wording,
caught by an existing regression guard before commit). **Impact:** none on shipped behaviour;
the fix only changed prose inside a docstring comment.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None — no external services, no credentials, no new dependency.

## Next Phase Readiness

Gap CR-02 is closed. Combined with `09-04-PLAN.md` (gap CR-01, no file overlap), both gaps
recorded in `09-VERIFICATION.md` are now resolved. `09-VERIFICATION.md`'s failed truth #8 ("the
configured command string itself is redacted against `known_secrets` before being
persisted/committed") is now true, and `09-03-PLAN.md`'s human-check step 4 ("confirm no
credential value appears anywhere in that file") is now backed by an automated unit test rather
than a human read. Phase 9's remaining `behavior_unverified_items` (seven items, db-tier) are
carried under Manual-Only Verification in `09-04-PLAN.md`/`09-04-SUMMARY.md` — not gaps, not
addressed by this plan, and out of this plan's scope by design.

## Self-Check: PASSED

- FOUND: src/dark_factory/orchestrator/quality_gate.py
- FOUND: tests/unit/test_quality_gate.py
- FOUND: a78f8f2 (git log --oneline --all)
- FOUND: 4ce341f (git log --oneline --all)
