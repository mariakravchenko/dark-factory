---
phase: 09-independent-quality-gate-bounded-feedback-loops
verified: 2026-09-23T12:00:00Z
status: gaps_found
score: 13/22 must-haves verified
behavior_unverified: 7
overrides_applied: 0
covered_files:
  - ".dark-factory/roles/DEVELOPMENT.yaml"
  - ".dark-factory/roles/QA.yaml"
  - ".planning/REQUIREMENTS.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-01-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-01-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-02-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-02-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-03-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-03-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-REVIEW.md"
  - "src/dark_factory/actions/builtins.py"
  - "src/dark_factory/config/loader.py"
  - "src/dark_factory/context/builder.py"
  - "src/dark_factory/domain/signal.py"
  - "src/dark_factory/events/catalog.py"
  - "src/dark_factory/orchestrator/lifecycle.py"
  - "src/dark_factory/orchestrator/quality_gate.py"
  - "src/dark_factory/orchestrator/runner.py"
  - "src/dark_factory/workflows/pipeline.py"
  - "tests/db/test_artifact_schema_violation_fails_role.py"
  - "tests/db/test_context_builder_retry_isolation.py"
  - "tests/db/test_feedback_reaches_developer.py"
  - "tests/db/test_iteration_cap_exhaustion.py"
  - "tests/db/test_qa_bounce.py"
  - "tests/db/test_quality_gate_gates_the_run.py"
  - "tests/support/fake_artifacts.py"
  - "tests/unit/test_context_builder.py"
  - "tests/unit/test_domain_enums.py"
  - "tests/unit/test_lifecycle.py"
  - "tests/unit/test_quality_gate.py"
covered_digest: "v1:sha256:e12f179625e561fce93c0285d70d639932d8a209ee8e8c8fba27de56f9fee486"
gaps:
  - truth: "A bounced terminal-role attempt is write-scope-enforced (ROLE-05) exactly like a completed one — an out-of-scope write cannot survive a bounce undetected"
    status: failed
    reason: "src/dark_factory/orchestrator/runner.py's enforce_write_scope block is gated only on `if signal is Signal.ROLE_COMPLETED:`. Signal.ROLE_BOUNCED — introduced by this phase inside the same terminal-role gate block, above this guard — leaves the condition false, so enforce_write_scope never runs for a bounced attempt. An out-of-scope write made during a bounced attempt is never detected or reverted; it survives uncaught into the next role's WIP-recovery commit. Confirmed by direct code read (runner.py ~line 1226-1246) and independently by 09-REVIEW.md CR-01. No test in the phase (or the codebase) exercises this combination — every db-tier fixture worker used in Phase 9's tests writes only inside the gitignored artifacts/<role>/ subtree, so attempt_changed_paths is always empty regardless of whether the guard runs."
    artifacts:
      - path: "src/dark_factory/orchestrator/runner.py"
        issue: "enforce_write_scope block condition `if signal is Signal.ROLE_COMPLETED:` (~line 1232) excludes Signal.ROLE_BOUNCED, which can be set earlier in the same function (the QA-verdict-FAIL and quality-gate-FAIL bounce paths, ~lines 1094 and ~1156)"
    missing:
      - "Broaden the guard to `if signal in (Signal.ROLE_COMPLETED, Signal.ROLE_BOUNCED):`, and on a WriteScopeViolation also clear counter_increments/bounce_reason (mirroring the existing GitError except-block a few lines above) so a scope violation correctly downgrades a would-be bounce to a genuine ROLE_FAILED rather than leaving stale bounce side effects — per 09-REVIEW.md CR-01's proposed fix"
      - "Add a db-tier regression test that makes the terminal role write outside its declared write_scope on an attempt whose verdict/gate also FAILs under cap, asserting the offending path is reverted and the run fails cleanly rather than bouncing with the violation intact"
  - truth: "No credential embedded in a configured quality_gate.commands entry reaches the committed verification/quality_gate.json artifact unredacted"
    status: failed
    reason: "run_quality_gate (src/dark_factory/orchestrator/quality_gate.py) redacts captured stdout and stderr against known_secrets before building each GateCommandResult, but stores the configured `command` string itself verbatim (line 165: `command=command`). verification/quality_gate.json is force-added and committed onto the run's working branch by the same commit_run_artifacts call that commits the terminal role's own artifacts, so a credential an operator embeds directly in a `.dark-factory.yaml` quality_gate.commands entry (e.g. a `curl -H \"Authorization: Bearer <token>\"` health-check command) is committed to git history in the clear. This contradicts the project's own CLAUDE.md Security constraint ('Infrastructure credentials ... must never reach workers, artifacts, prompts, event payloads, comments, logs, or reports') and 09-03-PLAN.md's own human-check step 4 ('Confirm no credential value appears anywhere in that file'). Confirmed by direct code read and independently by 09-REVIEW.md CR-02. tests/unit/test_quality_gate.py's only redaction test (test_a_known_secret_value_in_stdout_is_redacted) checks stdout only — no test anywhere covers a secret embedded in the configured command text itself."
    artifacts:
      - path: "src/dark_factory/orchestrator/quality_gate.py"
        issue: "GateCommandResult(command=command, ...) at line 165 passes the raw configured command string through unredacted, unlike stdout/stderr built on the two immediately preceding lines"
    missing:
      - "Redact the command string the same way stdout/stderr already are: `command=str(redact(command, known_secrets=known_secrets))`, per 09-REVIEW.md CR-02's proposed fix"
      - "Add a unit test mirroring test_a_known_secret_value_in_stdout_is_redacted that embeds a known secret directly in the configured command string (not just its output) and asserts it is absent from result.commands[0].command"
behavior_unverified_items:
  - truth: "GATE-02/GATE-03: a gate whose commands produced a non-zero exit_code never reaches RunStatus.COMPLETED on that attempt, regardless of the worker's own success-claiming WorkerResult.summary"
    test: "tests/db/test_quality_gate_gates_the_run.py::test_gate_fail_keeps_the_run_out_of_completed_despite_a_success_summary against a real PostgreSQL 17"
    expected: "Run reaches RunStatus.FAILED, not COMPLETED, with both configured commands recorded and the QA role-execution row's error naming quality_gate_fail"
    why_human: "This sandbox has no reachable PostgreSQL/Docker; the test collects cleanly (0 import/collection errors) but was not executed this session. Structurally sound by code read (the signal is derived from gate_result.status alone; result.summary is never consulted), but state-transition behavior is unproven without a real drive() run."
  - truth: "LOOP-03: the iteration counter is read off RunState and compared to its configured cap BEFORE the signal is chosen — under cap yields ROLE_BOUNCED with a one-entry counter_increments mapping, at/over cap yields ROLE_FAILED with none"
    test: "tests/db/test_qa_bounce.py::test_qa_fail_then_pass_bounces_once_and_completes and tests/db/test_qa_bounce.py::test_gate_fail_then_pass_bounces_once_and_completes"
    expected: "runs.qa_developer_iterations / runs.quality_gate_iterations increment by exactly 1 on a bounce and the two counters never cross-contaminate"
    why_human: "_bounce_or_fail has no direct unit test — it is exercised only through db-tier drive() runs, none of which executed in this sandbox (no PostgreSQL/Docker). Collection-verified clean."
  - truth: "LOOP-04 (adjacency): when the failing role is the pipeline's first node, the runner chooses ROLE_FAILED with reason no_earlier_role_to_bounce_to rather than handing transition() a bounce it would reject"
    test: "No dedicated single-role-pipeline db scenario exists in this phase's test modules; the pure transition()-level rejection is unit-proven (tests/unit/test_lifecycle.py) but the runner-level helper's adjacency branch is not exercised by any test found in this session"
    expected: "A pipeline whose only role FAILs produces ROLE_FAILED immediately with the adjacency reason, never a call into transition() with ROLE_BOUNCED from the first node"
    why_human: "Code-reviewed as correct (_bounce_or_fail returns ROLE_FAILED when bounce_target is None) but has no automated proof at the runner-integration level in this codebase as of this session."
  - truth: "LOOP-04 (empty): with a configured cap of 0, the first corresponding FAIL produces ROLE_FAILED immediately — zero bounces, no special-case branch"
    test: "tests/db/test_iteration_cap_exhaustion.py::test_zero_cap_makes_the_first_qa_rejection_terminal_with_no_bounce"
    expected: "Run ends FAILED with zero ROLE_BOUNCED events and runs.qa_developer_iterations still 0"
    why_human: "Db-tier only; not executed in this sandbox. Collection-verified clean."
  - truth: "LOOP-04 (idempotency): re-driving an already-FAILED exhausted run writes no further run_events rows and no further counter increments"
    test: "tests/db/test_iteration_cap_exhaustion.py::test_redriving_an_exhausted_run_is_a_no_op"
    expected: "run_events row count and both counter columns are byte-identical before and after a second advance() call on a terminal run"
    why_human: "Db-tier only; not executed in this sandbox. Relies on the pre-existing STOP_STATUSES early return (verified in earlier phases) applied to this phase's new terminal state — collection-verified clean, not re-executed here."
  - truth: "LOOP-01: after a QA-FAIL bounce, the Developer's second attempt actually receives a RoleContext containing verdict.json with QA's structured issues (severity, acceptance_criterion, description) — end to end through a real drive() run"
    test: "tests/db/test_feedback_reaches_developer.py::test_qa_fail_delivers_structured_issues_to_developer_attempt_2"
    expected: "Developer attempt-1 RoleContext has no verdict.json entry; attempt-2 RoleContext has one whose produced_by names QA and whose content carries the FAIL issue's severity/criterion/description"
    why_human: "The resolution logic itself (_resolve_optional_input) is unit-tested and passing (tests/unit/test_context_builder.py); this item is specifically the end-to-end pipeline proof, which is db-tier only and not executed in this sandbox. Collection-verified clean."
  - truth: "LOOP-02 (payload): after a quality-gate FAIL bounce, the Developer's second attempt actually receives a RoleContext containing quality_gate.json with the failing command's real exit_code/stdout/stderr — end to end through a real drive() run"
    test: "tests/db/test_feedback_reaches_developer.py::test_gate_fail_delivers_real_command_output_to_developer_attempt_2"
    expected: "Developer attempt-2 RoleContext has a quality_gate.json entry whose produced_by is the gate and whose parsed content carries a non-zero exit_code and the sentinel stderr text"
    why_human: "Same split as LOOP-01 above: resolution logic unit-verified, end-to-end db-tier proof not executed in this sandbox. Collection-verified clean."
---

# Phase 9: Independent Quality Gate & Bounded Feedback Loops Verification Report

**Phase Goal:** Nothing an agent claims is accepted as truth — Dark Factory re-runs the repository's own commands itself, and every rejection loops back to the Developer under a hard cap.
**Verified:** 2026-09-23T12:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

Phase 9's core mechanics — an orchestrator-run quality gate folding PASS/FAIL from exit
codes alone, a bounded bidirectional pipeline transition, and a config-declared feedback
channel back to the Developer — are all genuinely implemented, not stubbed, and the pure
and unit-tier proofs for each (668 unit/contract tests, 0 failures; mypy and ruff clean)
independently confirm the logic each proof targets. However, two **critical** defects
found by direct source inspection (independently corroborated by `09-REVIEW.md`) mean the
phase's own new code does not yet fully deliver on the invariants it explicitly commits
to: a bounced attempt bypasses the ROLE-05 write-scope authorization boundary entirely,
and a credential embedded in a configured `quality_gate.commands` entry would be
committed to git history unredacted, contradicting both the project's hard Security
constraint and this phase's own stated mitigation. Both are genuine regressions/gaps
introduced by this phase's new code paths, not pre-existing conditions.

Separately, and NOT counted as a fault of the implementation: every db-tier proof across
all three plans (`tests/db/test_quality_gate_gates_the_run.py`,
`tests/db/test_qa_bounce.py`, `tests/db/test_iteration_cap_exhaustion.py`,
`tests/db/test_feedback_reaches_developer.py`, plus the untouched pre-existing db suite)
requires a reachable PostgreSQL 17, which this sandbox does not have (no Docker, no local
`initdb`/`pg_ctl`, no `DARK_FACTORY_TEST_DATABASE_URL`) — the same pre-existing constraint
every prior phase (6/7/8) in this project has documented. All such tests collect cleanly
(zero import/collection errors) and were written to the letter of each plan's `<behavior>`
block, but were not executed this session. These items are listed as
`behavior_unverified_items` rather than failures.

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | GATE-01: `run_quality_gate` executes every configured command via `shell_execute` with `cwd` set to the run's worktree and the configured timeout | ✓ VERIFIED | `quality_gate.py:152-171`; `tests/unit/test_quality_gate.py` real-subprocess unit tests pass |
| 2  | GATE-01 (D-09): all commands run even after an earlier one fails; entry count always equals `len(commands)` | ✓ VERIFIED | `quality_gate.py`'s loop never breaks early; `test_a_failing_first_command_does_not_stop_the_second_and_yields_fail` passes |
| 3  | GATE-02: `QualityGateResult.status` is a `computed_field`, PASS iff every command's `exit_code==0` and `timed_out is False`; no constructor argument can hand-set it | ✓ VERIFIED | `quality_gate.py:113-122`; `test_quality_gate_result_cannot_be_constructed_with_an_explicit_status` passes |
| 4  | GATE-02/GATE-03: a gate FAIL keeps the run out of `COMPLETED` regardless of the worker's own success-claiming summary | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Structurally correct by code read (`runner.py` derives the signal from `gate_result.status` alone); db-tier proof not executed this session |
| 5  | GATE-04: `verification/quality_gate.json` parses as an object with exactly `status`/`commands`, each command entry with exactly `command`/`exit_code`/`stdout`/`stderr`/`timed_out` | ✓ VERIFIED | `quality_gate.py`'s two frozen `extra="forbid"` models; `test_quality_gate_result_status_key_order_is_commands_then_status` and the introspection commands in 09-01-PLAN's acceptance criteria both confirm the shape |
| 6  | Captured stdout/stderr capped at 16384 bytes with a tail-preserving, explicit dropped-byte marker | ✓ VERIFIED | `_cap_output`, `quality_gate.py:58-72`; unit test exercises the >16384-byte case |
| 7  | Captured stdout/stderr pass through `redact()` against `known_secrets` before being persisted | ✓ VERIFIED | `quality_gate.py:161-162`; `test_a_known_secret_value_in_stdout_is_redacted` passes |
| 8  | The configured **command string** itself is redacted against `known_secrets` before being persisted/committed | ✗ FAILED | `quality_gate.py:165` — `command=command` passes the raw string through unredacted; see Gaps (CR-02) |
| 9  | Terminal pipeline position detected structurally via `next_node(pipeline, node.name) is None`, never a role-name literal | ✓ VERIFIED | `runner.py`; `tests/unit/test_no_role_name_literal.py` passes against the new block |
| 10 | `transition()` computes a backwards move to the preceding node on `ROLE_BOUNCED`; illegal from the first node, from a `TERMINAL_STATUSES` status, and from `WAITING_HUMAN` | ✓ VERIFIED | `lifecycle.py:119-129`; `tests/unit/test_lifecycle.py` legal/illegal parametrized tables pass |
| 11 | `previous_node` mirrors `next_node` — first-node `None`, else the preceding node | ✓ VERIFIED | `pipeline.py:105-111`; direct unit tests pass |
| 12 | LOOP-03: the relevant iteration counter is read and compared to its cap **before** the signal is chosen; exactly one counter incremented per attempt | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `_bounce_or_fail` (`runner.py:205-231`) implements the rule and reads correctly by code inspection, but has no direct unit test — only db-tier `drive()` proofs exercise it, none executed this session |
| 13 | LOOP-03: the counter increment rides `apply_transition`'s existing `counter_increments` parameter under its existing row lock/fencing — no new lock site introduced | ✓ VERIFIED | `runner.py:1408` passes `counter_increments=counter_increments or None` into the unchanged `apply_transition` call; `grep -rn "with_for_update\|pg_advisory" src/ --include=*.py \| grep -v persistence/` returns no lines |
| 14 | LOOP-04 (adjacency): failing role with no earlier role yields `ROLE_FAILED` reason `no_earlier_role_to_bounce_to`, never a rejected `transition()` call | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Code-correct by inspection (`_bounce_or_fail` returns `ROLE_FAILED` when `bounce_target is None`); no automated proof at the runner-integration level found in this session |
| 15 | LOOP-04 (empty): a cap of 0 makes the first rejection terminal, no zero-value special case | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `0 < cap` correctly needs no branch; db-tier proof (`test_zero_cap_makes_the_first_qa_rejection_terminal_with_no_bounce`) collects but was not executed |
| 16 | LOOP-04 (idempotency): re-driving an exhausted run adds no further events/increments | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Relies on pre-existing `STOP_STATUSES` early return; db-tier proof collects but was not executed |
| 17 | LOOP-01: a bounced Developer's next attempt receives `verdict.json` with QA's structured issues, end to end through a real run | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Resolution logic unit-verified (`tests/unit/test_context_builder.py`); end-to-end `tests/db/test_feedback_reaches_developer.py` collects but was not executed |
| 18 | LOOP-02 (payload): a bounced Developer's next attempt receives `quality_gate.json` with the real per-command failure output, end to end through a real run | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Same split as #17 |
| 19 | `optional_inputs` is declared in `DEVELOPMENT.yaml` config, not a Python "is this a bounced attempt?" branch in `ContextBuilder` | ✓ VERIFIED | `DEVELOPMENT.yaml:52`; `context/builder.py` resolves purely from the declared list, no bounce-detection branch |
| 20 | On the Developer's first-ever attempt, neither optional input resolves and neither raises | ✓ VERIFIED | `tests/unit/test_context_builder.py::test_optional_input_absent_when_producing_role_has_no_completed_attempt` and the verification-tree-absent case both pass |
| 21 | An oversized feedback artifact raises loudly (`ArtifactTooLargeError`) rather than being silently truncated or omitted | ✓ VERIFIED | `_resolve_optional_input` never catches `ArtifactTooLargeError`; `test_oversized_optional_input_raises` passes |
| 22 | A bounced terminal-role attempt is write-scope-enforced (ROLE-05) exactly like a completed one — an out-of-scope write cannot survive a bounce undetected | ✗ FAILED | `runner.py`'s `enforce_write_scope` guard reads `if signal is Signal.ROLE_COMPLETED:`, excluding `Signal.ROLE_BOUNCED`; see Gaps (CR-01) |

**Score:** 13/22 truths verified (7 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/orchestrator/quality_gate.py` | `GateCommandResult`, `QualityGateResult`, `run_quality_gate`, `write_quality_gate_result` | ✓ VERIFIED | Present, exports match, 190 lines, wired into `runner.py` |
| `src/dark_factory/events/catalog.py` | `QUALITY_GATE_STARTED/PASSED/FAILED`, `ROLE_BOUNCED` members | ✓ VERIFIED | All four present; `EventType` count is 16, matching `tests/unit/test_domain_enums.py` |
| `tests/unit/test_quality_gate.py` | Pure-tier proof of PASS/FAIL fold, ordering, redaction | ✓ VERIFIED | Present, real-subprocess tests, all pass |
| `tests/db/test_quality_gate_gates_the_run.py` | Real `drive()` proof of gate-gating | ✓ VERIFIED (exists/wired) | Present, 3 scenarios, collects cleanly; not execution-verified (Postgres unavailable) |
| `src/dark_factory/workflows/pipeline.py` | `previous_node` | ✓ VERIFIED | Present, mirrors `next_node`, in `__all__` |
| `src/dark_factory/orchestrator/lifecycle.py` | `Signal.ROLE_BOUNCED` arm of `transition()` | ✓ VERIFIED | Present, structurally identical shape to existing arms |
| `tests/db/test_qa_bounce.py` | Real `drive()` proof of a bounce | ✓ VERIFIED (exists/wired) | Present, 2 scenarios, collects cleanly; not execution-verified |
| `tests/db/test_iteration_cap_exhaustion.py` | Real `drive()` proof of cap exhaustion | ✓ VERIFIED (exists/wired) | Present, 4 scenarios, collects cleanly; not execution-verified |
| `src/dark_factory/config/loader.py` | `RoleDefinition.optional_inputs` | ✓ VERIFIED | Present, projected into snapshot |
| `src/dark_factory/context/builder.py` | Lenient optional-input resolution + `verification/` path | ✓ VERIFIED | `_resolve_optional_input`, two-strategy, present and wired |
| `.dark-factory/roles/DEVELOPMENT.yaml` | Two declared feedback inputs | ✓ VERIFIED | `optional_inputs: [verdict.json, quality_gate.json]` present; mandatory `inputs` untouched |
| `tests/db/test_feedback_reaches_developer.py` | Real `drive()` proof of feedback delivery | ✓ VERIFIED (exists/wired) | Present, 2 scenarios, collects cleanly; not execution-verified |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `orchestrator/runner.py` | `orchestrator/quality_gate.py` | `run_quality_gate(...)` called inside `_run_current_role` before `transition()` | ✓ WIRED | Confirmed at `runner.py:1094` (bounce helper) and the gate call block |
| `orchestrator/quality_gate.py` | `tools/env.py` | `shell_execute(...)` with a shlex-split argv | ✓ WIRED | `quality_gate.py:155-160` |
| `orchestrator/quality_gate.py` | `events/redaction.py` | `redact(...)` applied to stdout/stderr | ✓ WIRED (partial) | Applied to stdout/stderr only — **not** to `command` (see Gap CR-02) |
| `orchestrator/lifecycle.py` | `workflows/pipeline.py` | `previous_node` used to compute the `ROLE_BOUNCED` target | ✓ WIRED | `lifecycle.py:120` |
| `orchestrator/runner.py` | `persistence/mutations.py` | `counter_increments` passed into `apply_transition` | ✓ WIRED | `runner.py:1408` |
| `.dark-factory/roles/DEVELOPMENT.yaml` | `context/builder.py` | `optional_inputs` read off the persisted snapshot, resolved leniently | ✓ WIRED | Config declares both filenames; `build_role_context` appends resolved optional inputs after mandatory ones |
| `context/builder.py` | `artifacts/store.py` | `read_artifact_text` against the run root's `verification/` tree | ✓ WIRED | `_resolve_optional_input` strategy two |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit + contract tier is green | `uv run pytest -m "unit or contract" -q --tb=line` | `668 passed, 333 deselected in 258.27s` | ✓ PASS |
| Static typing clean | `uv run mypy src/dark_factory` | `Success: no issues found in 68 source files` | ✓ PASS |
| Lint clean | `uv run ruff check .` | `All checks passed!` | ✓ PASS |
| Role-name-literal / no-live-config-read guards still green against new blocks | `uv run pytest -m unit -q tests/unit/test_no_role_name_literal.py tests/unit/test_orchestrator_no_live_config_read.py tests/unit/test_single_mutation_path.py` | `9 passed` | ✓ PASS |
| Phase 9 db-tier modules collect with zero errors | `uv run pytest -m db -q --collect-only tests/db/test_quality_gate_gates_the_run.py tests/db/test_qa_bounce.py tests/db/test_iteration_cap_exhaustion.py tests/db/test_feedback_reaches_developer.py tests/db/test_context_builder_retry_isolation.py` | `17 tests collected` | ✓ PASS (collection only) |
| Whole `db`-tier suite collects with zero errors | `uv run pytest -m db -q --collect-only` | `164/1001 tests collected (837 deselected)` | ✓ PASS (collection only) |
| `db`-tier execution (real `drive()` runs) | n/a — no reachable PostgreSQL 17 in this sandbox | not run | ? SKIP (routed to `behavior_unverified_items`) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| GATE-01 | 09-01 | Independently run configured `quality_gate.commands` in the repo environment | ✓ SATISFIED (unit-proven; db-proof pending) | `quality_gate.py`, `runner.py` wiring, `tests/unit/test_quality_gate.py` |
| GATE-02 | 09-01 | Gate decision from exit codes, never agent prose | ✓ SATISFIED (unit-proven; db-proof pending) | `QualityGateResult.status` computed field |
| GATE-03 | 09-01 | Self-validation by agents preserved but never final | ✓ SATISFIED (structural; db-proof pending) | Gate always runs independent of `result.summary` |
| GATE-04 | 09-01 | Result written to `verification/quality_gate.json` | ✓ SATISFIED, with a caveat | Shape correct; command-string redaction gap (CR-02) affects the file's content trustworthiness, not its existence/shape |
| LOOP-01 | 09-03 | QA FAIL returns structured issues artifact | ✓ SATISFIED (resolution unit-proven; end-to-end db-proof pending) | `optional_inputs`, `_resolve_optional_input` |
| LOOP-02 | 09-02/09-03 | Gate failure returns real failure output; QA re-evaluates, gate re-runs | ✓ SATISFIED (unit-proven; db-proof pending) | Bounce loop + `quality_gate.json` optional input |
| LOOP-03 | 09-02 | Feedback iterations bounded by repo config, checked before dispatch | ✓ SATISFIED (structural/unit-proven; db-proof pending) | `_bounce_or_fail`, `RetryConfig` |
| LOOP-04 | 09-02 | Exhaustion transitions to FAILED with attempt/reason persisted | ✓ SATISFIED (structural/unit-proven; db-proof pending) | `_bounce_or_fail`, extended `RUN_FAILED` payload |

No orphaned requirements: `REQUIREMENTS.md`'s Phase 9 mapping (GATE-01..04, LOOP-01..04) exactly matches the union of `requirements:` declared across `09-01-PLAN.md`, `09-02-PLAN.md`, and `09-03-PLAN.md`.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/dark_factory/orchestrator/runner.py` | ~1226-1246 | `enforce_write_scope` gated only on `Signal.ROLE_COMPLETED`, silently skipping `Signal.ROLE_BOUNCED` | 🛑 Blocker (CR-01) | An authorization-boundary bypass: an out-of-scope write on a bounced attempt is never detected or reverted |
| `src/dark_factory/orchestrator/quality_gate.py` | 165 | `command=command` stored without `redact()`, unlike `stdout`/`stderr` on the two preceding lines | 🛑 Blocker (CR-02) | A credential embedded in a configured gate command is committed to git history in the clear, contradicting SEC-01/CLAUDE.md and this phase's own T-09-03 claim |
| `src/dark_factory/orchestrator/runner.py` | 1110-1115 | `run_quality_gate(...)` call has no `try`/`except`, unlike every sibling post-worker operation in the same function | ⚠️ Warning (WR-01) | An unrunnable/misconfigured gate command (empty string, missing binary) raises out of `advance()`/`drive()` instead of failing the role/run cleanly, and breaks resumability (the QA role-execution row is never updated, so the worker's own work would silently re-run on the next `advance()`) |
| `src/dark_factory/orchestrator/quality_gate.py` | 58-72 | `_cap_output`'s reported "dropped bytes" count is computed before the marker's own byte cost is subtracted | ℹ️ Info (IN-01) | Docstring's promised dropped-byte count is a few tens of bytes off; cosmetic only |
| `src/dark_factory/orchestrator/runner.py` | 1071-1078 | Gate skip is silent if a future terminal role's declared outputs omit `verdict.json` | ℹ️ Info (IN-02) | Unreachable for the shipped pipeline (QA's outputs are schema-enforced); a latent gap for a future/user-configured pipeline |

No `TBD`/`FIXME`/`XXX` debt markers found in any Phase 9 file scanned.

### Gaps Summary

Two CRITICAL, independently-confirmed defects block this phase from being counted as
fully achieving its goal, despite the mechanics being genuinely real (not stubbed) and
668/668 unit+contract tests, mypy, and ruff all clean:

1. **CR-01 — write-scope enforcement bypass on bounce.** `enforce_write_scope`
   (ROLE-05, this project's own "authorization control, not a formatting nicety") is
   gated on `Signal.ROLE_COMPLETED` only. Phase 9 adds a second way `signal` can leave
   `ROLE_COMPLETED` before that guard runs — `Signal.ROLE_BOUNCED`, set earlier in the
   same function — and the guard was never widened to cover it. A bounced attempt's
   out-of-scope write is never checked, never reverted, and silently survives into the
   next role's WIP-recovery commit, indistinguishable in the audit trail from a
   legitimate change. This is a direct hit against the phase's own goal framing ("Nothing
   an agent claims is accepted as truth") — it is precisely an unaudited, unenforced
   write an agent could make.

2. **CR-02 — unredacted command string in a committed artifact.** `run_quality_gate`
   redacts `stdout`/`stderr` but not the configured `command` string itself before
   writing `verification/quality_gate.json`, which is then force-added and committed to
   the run's working branch. A credential embedded directly in a `quality_gate.commands`
   entry (a realistic authoring pattern, e.g. an authenticated health-check `curl`) would
   be committed to git history in the clear — contradicting the project's own hard
   Security constraint and this phase's own T-09-03 threat-mitigation claim and
   09-03-PLAN's human-check step 4.

Both fixes are small, precisely scoped, and named in `09-REVIEW.md`; neither requires
re-architecting any of the phase's real, working mechanics. Fixing both plus adding the
two named regression tests should close this phase cleanly.

Separately (not a gap, but unresolved): every db-tier proof across all three plans is
written and collection-verified but not execution-verified in this sandbox, for the same
pre-existing PostgreSQL-unavailability reason documented in every prior phase's
verification. These are listed under `behavior_unverified_items` and should be re-run
(`uv run pytest -m db -q tests/db/test_quality_gate_gates_the_run.py
tests/db/test_qa_bounce.py tests/db/test_iteration_cap_exhaustion.py
tests/db/test_feedback_reaches_developer.py`) once a real PostgreSQL 17 is reachable —
ideally in the same pass that closes CR-01/CR-02, since CR-01's proposed regression test
is itself a new db-tier test.

---

_Verified: 2026-09-23T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
