---
phase: 09-independent-quality-gate-bounded-feedback-loops
verified: 2026-09-26T09:35:00Z
status: human_needed
score: 20/22 must-haves verified
behavior_unverified: 2
overrides_applied: 0
covered_files:
  - ".dark-factory/roles/DEVELOPMENT.yaml"
  - ".dark-factory/roles/QA.yaml"
  - ".planning/REQUIREMENTS.md"
  - ".planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-01-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-01-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-02-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-02-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-03-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-03-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-04-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-04-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-05-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-05-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-06-PLAN.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-06-SUMMARY.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-REVIEW.md"
  - ".planning/phases/09-independent-quality-gate-bounded-feedback-loops/09-UAT.md"
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
  - "tests/db/test_write_scope_enforced_on_bounce.py"
  - "tests/support/fake_artifacts.py"
  - "tests/unit/test_context_builder.py"
  - "tests/unit/test_domain_enums.py"
  - "tests/unit/test_lifecycle.py"
  - "tests/unit/test_quality_gate.py"
  - "tests/unit/test_role_context_rebuild_uses_the_worktree.py"
  - "tests/unit/test_write_scope_guard_covers_bounce.py"
covered_digest: "v1:sha256:f83596f870f3bd200d1c59351ba1fa00569c8dce2b8c116bbeb32cc8bf996ced"
re_verification:
  previous_status: human_needed
  previous_score: "14/22"
  gaps_closed: []
  gaps_remaining:
    - "G-09-6 (LOOP-01) and G-09-7 (LOOP-02): the test-fixture root-cause is corrected and pinned by a new DB-free AST guard, but the actual db-tier proof against a real PostgreSQL 17 has not been executed by anyone since the fix — not this sandbox (no reachable PostgreSQL), and 09-06-PLAN.md's own prohibitions forbid marking either gap resolved on structural evidence alone"
  regressions: []
behavior_unverified_items:
  - truth: "LOOP-01: after a QA-FAIL bounce, the Developer's second attempt actually receives a RoleContext containing verdict.json with QA's structured issues (severity, acceptance_criterion, description) — end to end through a real drive() run"
    test: "tests/db/test_feedback_reaches_developer.py::test_qa_fail_delivers_structured_issues_to_developer_attempt_2 against a real PostgreSQL 17"
    expected: "2 passed, 0 skipped, 0 failed — specifically no MissingArtifactContentError on design.md"
    why_human: "This sandbox has no reachable PostgreSQL/Docker (confirmed directly this session: pytest.UsageError). 09-06 corrected the test fixture's root-cause defect (the attempt-2 rebuild now derives the worktree via ensure_worktree instead of reading the config repo root) and the fix is independently confirmed by direct source read, a clean AST-diff against the plan's exact prescription, and 3 passing DB-free structural-guard tests run this session — but per 09-06-PLAN.md's own prohibition, the fix must not be recorded as verified on the strength of the structural guard alone; only an actual db-tier execution proves the behavior."
  - truth: "LOOP-02 (payload): after a quality-gate FAIL bounce, the Developer's second attempt actually receives a RoleContext containing quality_gate.json with the failing command's real exit_code/stdout/stderr — end to end through a real drive() run"
    test: "tests/db/test_feedback_reaches_developer.py::test_gate_fail_delivers_real_command_output_to_developer_attempt_2 against a real PostgreSQL 17"
    expected: "Same command as LOOP-01 above (both scenarios share this module and its now-corrected rebuild hook); confirm this test also passes with 0 failures"
    why_human: "Same split as LOOP-01 above: same shared root-cause fix, same sandbox constraint, same 09-06-PLAN.md prohibition against declaring it verified without an actual run."
---

# Phase 9: Independent Quality Gate & Bounded Feedback Loops Verification Report

**Phase Goal:** Nothing an agent claims is accepted as truth — Dark Factory re-runs the repository's own commands itself, and every rejection loops back to the Developer under a hard cap.
**Verified:** 2026-09-26T09:35:00Z
**Status:** human_needed
**Re-verification:** Yes — after UAT (09-UAT.md, 6 passed / 2 issues) and gap-closure plan 09-06-PLAN.md (G-09-6, G-09-7)

## Goal Achievement

This is a full re-verification of all six plans (09-01 through 09-06), not a re-check of only
the newest plan. The prior `09-VERIFICATION.md` (2026-09-23, `human_needed`, 14/22, 8
`behavior_unverified_items`) predates two events that materially change the picture:

1. **The user ran UAT** (`09-UAT.md`, via `/gsd-verify-work`) against a real PostgreSQL 17 in
   their own environment. Of the 8 behavior-dependent items the prior verification could not
   execute, **6 passed** on that real run: GATE-02/GATE-03 gate-gating
   (`test_quality_gate_gates_the_run.py`), LOOP-03 counter increments and LOOP-04's
   empty-cap/idempotency scenarios (`test_qa_bounce.py`, `test_iteration_cap_exhaustion.py`),
   CR-01's own db-tier write-scope-on-bounce proof (`test_write_scope_enforced_on_bounce.py`),
   and LOOP-04's adjacency case (via a one-time manual throwaway script, not a permanent
   regression test — see Anti-Patterns). **2 failed**: both scenarios in
   `tests/db/test_feedback_reaches_developer.py` (LOOP-01, LOOP-02), both with the identical
   `MissingArtifactContentError` on `design.md` — logged as gaps G-09-6 and G-09-7.
2. **A debug session** (`.planning/debug/g-09-6-and-g-09-7-missing-architecture-design-md.md`)
   root-caused both failures to a single test-fixture defect, confirmed by a decisive DB-free
   differential experiment: `_CapturingWorker`'s attempt-2 `RoleContext` rebuild passed the
   **config repo root** to `build_role_context` where the production runner
   (`runner.py:866`) always passes the **git worktree** — a directory `worktree_path` places
   as a structural sibling of the repo root, never the same tree. Production code (the only
   `build_role_context` call site in `src/`) was independently confirmed correct; the defect
   was entirely in the observer.
3. **09-06-PLAN.md** closed the fixture defect: `_record_and_maybe_rebuild` now derives the
   worktree itself via `ensure_worktree(base_branch, working_branch)` read off the freshly
   loaded `RunState`, mirroring `_advance_once` line for line, and passes that value —
   never `self._repo_root` — to `build_role_context`. A new DB-free AST guard
   (`tests/unit/test_role_context_rebuild_uses_the_worktree.py`) pins this so the defect class
   cannot silently regress.

This session independently confirmed, without reusing SUMMARY.md narrative as evidence:

- **The diff is exactly what 09-06-PLAN.md and 09-06-SUMMARY.md claim.** `git show 8df8f06`
  shows only `_record_and_maybe_rebuild`'s body changed (new `ensure_worktree` call, `work_dir`
  substituted for `self._repo_root` as `build_role_context`'s root argument) plus a docstring
  extension — nothing else in the 413-line module changed. `git diff --name-only` across both
  09-06 commits touches zero paths under `src/`.
- **Both `_CapturingWorker` construction sites are untouched** — `repo_root=root` still appears
  at both call sites (now lines 295, 393), confirmed by direct grep; `__init__` is unchanged.
- **The new AST guard runs green in isolation this session**: `tests/unit/test_role_context_rebuild_uses_the_worktree.py` → `3 passed in 0.02s`.
- **`ensure_worktree`'s signature genuinely accepts what the fix now passes** —
  `base_branch: str | None`, `working_branch: str | None` as keyword-only parameters
  (`src/dark_factory/git/worktree.py:46-52`), matching `RunState`'s persisted columns
  (`persistence/repositories.py:108-109`).
- **No regression.** `uv run pytest -m "unit or contract"` → `676 passed, 335 deselected in
  256.52s` (grew from the prior session's 673 by exactly the 3 new AST-guard tests; 0
  failures). `mypy src/dark_factory` → `Success: no issues found in 68 source files`. `ruff
  check .` → `All checks passed!`. `git diff 4ce341f..HEAD -- src/` is empty — **zero**
  production files have changed since the CR-01/CR-02 fixes were last independently verified,
  so every previously-`✓ VERIFIED` static/structural truth is unaffected by this round.
- **The edited db module still collects cleanly** (`pytest -m db -q --collect-only
  tests/db/test_feedback_reaches_developer.py` → `2 tests collected`) and fails loud with the
  documented, non-regression `pytest.UsageError: No PostgreSQL 17 is reachable` when actually
  run — the same pre-existing sandbox constraint carried through Phases 6–9.

**What remains open, honestly:** the db-tier proof that the fix actually makes both scenarios
pass has **not been executed by anyone** since the fix landed — not by this sandbox (which
cannot reach PostgreSQL 17), and there is no record of the human re-running it either.
09-06-PLAN.md's own prohibition is explicit: *"MUST NOT record G-09-6 or G-09-7 as verified on
the strength of the structural guard alone."* This report honors that distinction exactly:
LOOP-01 and LOOP-02 are `⚠️ PRESENT_BEHAVIOR_UNVERIFIED`, not `✓ VERIFIED` and not a gap — the
code is genuinely fixed and structurally pinned; only the live-database confirmation is
outstanding.

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | GATE-01: `run_quality_gate` executes every configured command via `shell_execute` with `cwd` set to the run's worktree and the configured timeout | ✓ VERIFIED | `quality_gate.py:152-171`; unchanged since last verification; `tests/unit/test_quality_gate.py` re-run green this session (17 passed together with the write-scope guard tests) |
| 2  | GATE-01 (D-09): all commands run even after an earlier one fails; entry count always equals `len(commands)` | ✓ VERIFIED | `quality_gate.py`'s loop never breaks early; unchanged, `git diff 4ce341f..HEAD -- src/` empty |
| 3  | GATE-02: `QualityGateResult.status` is a `computed_field`, PASS iff every command's `exit_code==0` and `timed_out is False`; no constructor argument can hand-set it | ✓ VERIFIED | `quality_gate.py:113-122`, confirmed unchanged this session |
| 4  | GATE-02/GATE-03: a gate FAIL keeps the run out of `COMPLETED` regardless of the worker's own success-claiming summary | ✓ VERIFIED | Promoted from `PRESENT_BEHAVIOR_UNVERIFIED`: `09-UAT.md` test 1, human-executed against a real PostgreSQL 17 via `tests/db/test_quality_gate_gates_the_run.py`, result `pass`. `src/` is unchanged since (confirmed `git diff` empty), so the result still applies to the current codebase |
| 5  | GATE-04: `verification/quality_gate.json` parses as an object with exactly `status`/`commands`, each command entry with exactly `command`/`exit_code`/`stdout`/`stderr`/`timed_out` | ✓ VERIFIED | Unchanged; `GateCommandResult`'s five fields confirmed by direct AST/grep this session |
| 6  | Captured stdout/stderr capped at 16384 bytes with a tail-preserving, explicit dropped-byte marker | ✓ VERIFIED | `_cap_output`, unchanged |
| 7  | Captured stdout/stderr pass through `redact()` against `known_secrets` before being persisted | ✓ VERIFIED | `quality_gate.py:172-173`, confirmed unchanged this session |
| 8  | The configured **command string** itself is redacted against `known_secrets` before being persisted/committed (CR-02) | ✓ VERIFIED | `quality_gate.py:176`, confirmed unchanged; unit-tier proof still green |
| 9  | Terminal pipeline position detected structurally via `next_node(pipeline, node.name) is None`, never a role-name literal | ✓ VERIFIED | Unchanged |
| 10 | `transition()` computes a backwards move to the preceding node on `ROLE_BOUNCED`; illegal from the first node, from a `TERMINAL_STATUSES` status, and from `WAITING_HUMAN` | ✓ VERIFIED | `lifecycle.py`, unchanged |
| 11 | `previous_node` mirrors `next_node` — first-node `None`, else the preceding node | ✓ VERIFIED | `pipeline.py:105`, confirmed unchanged |
| 12 | LOOP-03: the relevant iteration counter is read and compared to its cap **before** the signal is chosen; exactly one counter incremented per attempt | ✓ VERIFIED | Promoted from `PRESENT_BEHAVIOR_UNVERIFIED`: `09-UAT.md` test 2, human-executed, `tests/db/test_qa_bounce.py` + `tests/db/test_iteration_cap_exhaustion.py` both green "in the combined run" |
| 13 | LOOP-03: the counter increment rides `apply_transition`'s existing `counter_increments` parameter under its existing row lock/fencing — no new lock site introduced | ✓ VERIFIED | Unchanged |
| 14 | LOOP-04 (adjacency): failing role with no earlier role yields `ROLE_FAILED` reason `no_earlier_role_to_bounce_to`, never a rejected `transition()` call | ✓ VERIFIED (see Anti-Patterns) | Promoted from `PRESENT_BEHAVIOR_UNVERIFIED`: `09-UAT.md` test 3, human-run against a real PostgreSQL 17, confirmed `RunStatus.FAILED`, zero `ROLE_BOUNCED` events, counter untouched. **Caveat:** the executed test was a one-time throwaway script (`tests/db/test_manual_check_loop04_adjacency.py`), not a committed permanent regression test — it remains untracked in this sandbox's working tree despite its own docstring instructing deletion after use. See Anti-Patterns for the coverage-debt flag |
| 15 | LOOP-04 (empty): a cap of 0 makes the first rejection terminal, no zero-value special case | ✓ VERIFIED | Promoted from `PRESENT_BEHAVIOR_UNVERIFIED`: `09-UAT.md` test 4, human-executed, `tests/db/test_iteration_cap_exhaustion.py` green |
| 16 | LOOP-04 (idempotency): re-driving an exhausted run adds no further events/increments | ✓ VERIFIED | Promoted from `PRESENT_BEHAVIOR_UNVERIFIED`: `09-UAT.md` test 5, human-executed, `tests/db/test_iteration_cap_exhaustion.py` green |
| 17 | LOOP-01: a bounced Developer's next attempt receives `verdict.json` with QA's structured issues, end to end through a real run | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `09-UAT.md` test 6 originally FAILED (G-09-6). 09-06 fixed the root cause (test-fixture defect) — confirmed by direct diff read and 3 green AST-guard tests this session — but the db-tier re-execution proving the fix actually resolves the scenario has not been performed since (unreachable in this sandbox; no record of a post-fix human run) |
| 18 | LOOP-02 (payload): a bounced Developer's next attempt receives `quality_gate.json` with the real per-command failure output, end to end through a real run | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Same split as #17 — `09-UAT.md` test 7 originally FAILED (G-09-7), same shared fix, same pending re-execution |
| 19 | `optional_inputs` is declared in `DEVELOPMENT.yaml` config, not a Python "is this a bounced attempt?" branch in `ContextBuilder` | ✓ VERIFIED | Unchanged |
| 20 | On the Developer's first-ever attempt, neither optional input resolves and neither raises | ✓ VERIFIED | Unchanged |
| 21 | An oversized feedback artifact raises loudly (`ArtifactTooLargeError`) rather than being silently truncated or omitted | ✓ VERIFIED | Unchanged |
| 22 | A bounced terminal-role attempt is write-scope-enforced (ROLE-05) exactly like a completed one — an out-of-scope write cannot survive a bounce undetected (CR-01) | ✓ VERIFIED | Promoted from `PRESENT_BEHAVIOR_UNVERIFIED`: `09-UAT.md` test 8, human-executed against a real PostgreSQL 17, `tests/db/test_write_scope_enforced_on_bounce.py::test_a_bounce_is_write_scope_enforced_exactly_like_a_completion` — "green in the combined run", explicitly noted in UAT as "CR-01's own behavioral proof, the last item this phase's gap closure needed" (prior to G-09-6/G-09-7 surfacing) |

**Score:** 20/22 truths verified (2 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/db/test_feedback_reaches_developer.py` | `_CapturingWorker._record_and_maybe_rebuild` derives the worktree via `ensure_worktree` and resolves `build_role_context` against it | ✓ VERIFIED | Confirmed by direct read and `git show 8df8f06`: exactly the prescribed 2-line change (new `ensure_worktree` call + `work_dir` substitution) plus docstring; both construction sites (`repo_root=root`, lines 295/393) unchanged |
| `tests/unit/test_role_context_rebuild_uses_the_worktree.py` | DB-free AST guard, 3 tests, `pytestmark = pytest.mark.unit` | ✓ VERIFIED | Present, 157 lines, 3 test functions confirmed by direct read; independently run green this session (`3 passed in 0.02s`) |
| `src/dark_factory/orchestrator/quality_gate.py` | `GateCommandResult`, `QualityGateResult`, `run_quality_gate`, `write_quality_gate_result`, command-string redaction (CR-02) | ✓ VERIFIED | Unchanged since last verification; `command=str(redact(command, known_secrets=known_secrets))` still at line 176 |
| `src/dark_factory/orchestrator/runner.py` | `enforce_write_scope` guard covering both `ROLE_COMPLETED` and `ROLE_BOUNCED` (CR-01) | ✓ VERIFIED | Unchanged; confirmed still present at the same call site this session |
| `tests/unit/test_write_scope_guard_covers_bounce.py` | AST structural regression guard for the widened write-scope check | ✓ VERIFIED | Unchanged; independently re-run green this session |
| `tests/db/test_write_scope_enforced_on_bounce.py` | Real `drive()` proof of write-scope enforcement on a bounce | ✓ VERIFIED (behaviorally proven via UAT) | Present, collects cleanly; UAT test 8 confirms it passes against real PostgreSQL 17 |
| `tests/db/test_quality_gate_gates_the_run.py` | Real `drive()` proof of gate-gating | ✓ VERIFIED (behaviorally proven via UAT) | UAT test 1 confirms pass |
| `tests/db/test_qa_bounce.py`, `tests/db/test_iteration_cap_exhaustion.py` | Real `drive()` proofs of bounce/cap-exhaustion | ✓ VERIFIED (behaviorally proven via UAT) | UAT tests 2, 4, 5 confirm pass |
| `src/dark_factory/workflows/pipeline.py` | `previous_node` | ✓ VERIFIED | Unchanged |
| `src/dark_factory/orchestrator/lifecycle.py` | `Signal.ROLE_BOUNCED` arm of `transition()` | ✓ VERIFIED | Unchanged |
| `src/dark_factory/config/loader.py` | `RoleDefinition.optional_inputs` | ✓ VERIFIED | Unchanged |
| `src/dark_factory/context/builder.py` | Lenient optional-input resolution + `verification/` path | ✓ VERIFIED | Unchanged |
| `.dark-factory/roles/DEVELOPMENT.yaml` | Two declared feedback inputs | ✓ VERIFIED | Unchanged |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/db/test_feedback_reaches_developer.py` | `src/dark_factory/git/worktree.py` | `_record_and_maybe_rebuild` calling `ensure_worktree(base_branch, working_branch)` from `fresh_state` | ✓ WIRED (new, 09-06) | `ensure_worktree\(` confirmed present in `_record_and_maybe_rebuild` by direct AST read and by the new guard's own passing test |
| `tests/unit/test_role_context_rebuild_uses_the_worktree.py` | `tests/db/test_feedback_reaches_developer.py` | AST walk asserting the single `build_role_context` call's root argument is the `ensure_worktree`-bound local | ✓ WIRED | Confirmed: `root_arg_source == worktree_local` assertion, independently re-run green |
| `orchestrator/runner.py` | `orchestrator/quality_gate.py` | `run_quality_gate(...)` called inside role dispatch before `transition()` | ✓ WIRED | Unchanged |
| `orchestrator/quality_gate.py` | `events/redaction.py` | `redact(...)` applied to stdout, stderr, and the configured `command` string | ✓ WIRED | Unchanged since CR-02 closure |
| `orchestrator/runner.py` | `git/scope.py` | `enforce_write_scope(...)` for both `ROLE_COMPLETED` and `ROLE_BOUNCED` | ✓ WIRED, behaviorally confirmed via UAT | Unchanged since CR-01 closure; UAT test 8 is the live-run confirmation |
| `orchestrator/lifecycle.py` | `workflows/pipeline.py` | `previous_node` used to compute the `ROLE_BOUNCED` target | ✓ WIRED | Unchanged |
| `.dark-factory/roles/DEVELOPMENT.yaml` | `context/builder.py` | `optional_inputs` read off the persisted snapshot, resolved leniently | ✓ WIRED | Unchanged |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| New AST guard (09-06) is green in isolation | `uv run pytest -m unit -q tests/unit/test_role_context_rebuild_uses_the_worktree.py` | `3 passed in 0.02s` | ✓ PASS (independently run this session) |
| Edited db module collects cleanly (no collection regression) | `uv run pytest -m db -q --collect-only tests/db/test_feedback_reaches_developer.py` | `2 tests collected in 0.06s` | ✓ PASS (independently run this session) |
| Edited db module still fails loud on the documented sandbox limitation, not a new defect | `uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py` | `pytest.UsageError: No PostgreSQL 17 is reachable...` | ? SKIP — confirmed directly this session, matches the documented pre-existing constraint, routed to `behavior_unverified_items` |
| Full unit + contract tier is green, grown by exactly the 3 new guard tests | `uv run pytest -m "unit or contract" -q --tb=line` | `676 passed, 335 deselected in 256.52s` (was 673 last session) | ✓ PASS (independently run this session) |
| Static typing clean | `uv run mypy src/dark_factory` | `Success: no issues found in 68 source files` | ✓ PASS (independently run this session) |
| Lint clean | `uv run ruff check .` | `All checks passed!` | ✓ PASS (independently run this session) |
| CR-01/CR-02 structural + unit proofs still green | `uv run pytest -m unit -q tests/unit/test_write_scope_guard_covers_bounce.py tests/unit/test_quality_gate.py` | `17 passed in 1.73s` | ✓ PASS (independently run this session) |
| Zero production files changed since CR-01/CR-02 | `git diff 4ce341f..HEAD -- src/` | empty | ✓ PASS (confirms no regression risk to previously-VERIFIED static/structural truths) |
| No debt markers in 09-06's touched files | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` on both files | no matches | ✓ PASS |
| Both `_CapturingWorker` construction sites unchanged | `grep -n "repo_root=root"` | 4 matches (2 constructor sites at 295/393, 2 `drive()` calls at 305/403) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| GATE-01 | 09-01 | Independently run configured `quality_gate.commands` in the repo environment | ✓ SATISFIED (behaviorally proven) | `quality_gate.py`, `runner.py` wiring, unit tests + UAT test 1 |
| GATE-02 | 09-01 | Gate decision from exit codes, never agent prose | ✓ SATISFIED (behaviorally proven) | `QualityGateResult.status` computed field + UAT test 1 |
| GATE-03 | 09-01 | Self-validation by agents preserved but never final | ✓ SATISFIED (behaviorally proven) | Gate always runs independent of `result.summary`; UAT test 1 |
| GATE-04 | 09-01, 09-05 | Result written to `verification/quality_gate.json` | ✓ SATISFIED | Shape correct (5 fields, D-11); command-string redaction proven at unit tier |
| LOOP-01 | 09-03, 09-06 | QA FAIL returns structured issues artifact | ⚠️ SATISFIED — structurally fixed, db-tier re-proof pending | `optional_inputs`, `_resolve_optional_input`; test-fixture root cause (G-09-6) corrected in 09-06 and AST-guarded, but the end-to-end db-tier scenario has not been re-executed since the fix |
| LOOP-02 | 09-02/09-03, 09-06 | Gate failure returns real failure output; QA re-evaluates, gate re-runs | ⚠️ SATISFIED — structurally fixed, db-tier re-proof pending | Same as LOOP-01 (G-09-7, shared root cause, shared module) |
| LOOP-03 | 09-02, 09-04 | Feedback iterations bounded by repo config, checked before dispatch | ✓ SATISFIED (behaviorally proven) | `_bounce_or_fail`, `RetryConfig`; UAT test 2 |
| LOOP-04 | 09-02, 09-04 | Exhaustion transitions to FAILED with attempt/reason persisted | ✓ SATISFIED (behaviorally proven, adjacency case via one-time manual script — see Anti-Patterns) | `_bounce_or_fail`, extended `RUN_FAILED` payload; UAT tests 3, 4, 5 |

No orphaned requirements: `REQUIREMENTS.md`'s Phase 9 mapping (GATE-01..04, LOOP-01..04) exactly
matches the union of `requirements:` declared across all six plans (`09-01` through `09-06`).
All eight IDs are marked `[x]` / `Complete` in `REQUIREMENTS.md`, and the roadmap phase entry
(`gsd_run query roadmap.get-phase 9`) lists all six plans as executed.

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX` debt markers found in any Phase 9 file, including both files touched by
09-06 (confirmed by an independent grep this session).

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/db/test_manual_check_loop04_adjacency.py` | whole file | Untracked, uncommitted throwaway script left in the working tree; its own docstring instructs `rm` after use, and its purpose (a one-time manual proof for LOOP-04's adjacency case) has already been served per `09-UAT.md` test 3 | ⚠️ Warning (coverage debt + repo hygiene) | This is the *only* evidence that LOOP-04's adjacency invariant was ever behaviorally proven, and it is not a permanent regression test — a future `git clean` or fresh clone loses it entirely, silently reverting truth #14 to unproven. Recommend either deleting it (per its own instruction, since it already served its purpose) and accepting the one-time UAT confirmation as historical record, or promoting it into a committed permanent test under `tests/db/`. Not a phase-blocking gap: the behavior itself is proven correct by direct code read (`_bounce_or_fail` returns `ROLE_FAILED` when `bounce_target is None`) independent of this script |
| `src/dark_factory/orchestrator/runner.py` | 1110-1115 | `run_quality_gate(...)` call has no `try`/`except`, unlike every sibling post-worker operation in the same function | ⚠️ Warning (WR-01, carried forward — pre-existing, unmodified by 09-06) | An unrunnable/misconfigured gate command raises out of `advance()`/`drive()` instead of failing the role/run cleanly. Confirmed still present this session; out of scope for this gap-closure round |
| `src/dark_factory/orchestrator/quality_gate.py` | 172-176 | `str(...)` wrapping around an already-`str` `redact()` result on all three redaction call sites | ℹ️ Info (IN-01, carried forward) | Cosmetic; harmless, not required for `mypy --strict` |
| `tests/db/test_write_scope_enforced_on_bounce.py` | whole module | Covers only the QA-verdict-FAIL bounce branch, not the symmetric quality-gate-FAIL bounce branch | ℹ️ Info (IN-02, carried forward) | Both branches share the identical guard call site; low residual risk |

### Gaps Summary

No FAILED truths, no MISSING/STUB artifacts, no NOT_WIRED key links, and no unresolved debt
markers. The phase's structural and unit-tier implementation is complete and independently
confirmed clean this session (676/676 unit+contract tests passing, mypy clean, ruff clean, zero
production-file drift since the last independently-verified commit).

**Two items remain genuinely open and route this report to `human_needed`, not `passed`:**

- **LOOP-01 / LOOP-02 (G-09-6, G-09-7):** the shared test-fixture root cause is fixed and
  AST-guarded against regression, but nobody — not this sandbox, not a recorded post-fix human
  run — has yet executed `tests/db/test_feedback_reaches_developer.py` against a real
  PostgreSQL 17 since the fix landed. Per 09-06-PLAN.md's own prohibition, this must not be
  claimed done until that command actually runs green.

Recommended re-run once PostgreSQL 17 is reachable (Docker, local `initdb`, or
`DARK_FACTORY_TEST_DATABASE_URL`):

```
uv run pytest -m db -q tests/db/test_feedback_reaches_developer.py
```

Confirm **2 passed, 0 skipped, 0 failed** — specifically that neither scenario raises
`MissingArtifactContentError`. This single command closes both G-09-6 and G-09-7.

Separately (not gating, but worth doing in the same pass): `tests/db/test_manual_check_loop04_adjacency.py` is a stray, untracked, already-served throwaway script — either delete it (its own instruction) or promote it to a committed permanent test so LOOP-04's adjacency invariant has lasting coverage instead of a one-time manual confirmation.

---

_Verified: 2026-09-26T09:35:00Z_
_Verifier: Claude (gsd-verifier)_
