---
phase: 02-pause-resume-single-owner-execution
plan: 06
subsystem: testing
tags: [postgres, pause-resume, redaction, crash-injection, pipeline, contract, tdd]

# Dependency graph
requires:
  - phase: 02-03
    provides: "the pause/resume mechanism — _run_current_role's signal-dispatch NEEDS_INPUT branch; apply_transition's one with-session.begin() block with HumanInteractionWrite; submit_answer; the RESUMING marker; question/answer through the one redact() call site"
  - phase: 02-01
    provides: "human_interactions table (question / answer TEXT columns), the partial unique WAITING index"
  - phase: 01-03
    provides: "redact() / scrub_known_values(); Settings.known_secret_values(); the D-15 pattern table"
  - phase: 01-09
    provides: "tests/support/log_sink.real_log_sink; the presence-then-absence redaction-proof discipline; the whole-surface sweep shape"
  - phase: 01-07
    provides: "the after_cursor_execute mid-transaction crash-injection recipe (tests/db/test_transition_atomic.py)"
provides:
  - "tests/db/test_pause_mechanism_generic.py — HITL-01: a two-node pipeline (BA + an invented ARCHITECTURE node) injected through the runner's pipeline parameter; either node pauses through structurally identical code once the role name and role-execution row identity are projected out; answering either returns to the node that asked on the same attempt and the run completes through the remaining node"
  - "tests/db/test_pause_path_atomic.py — HITL-02 atomicity half: crash injected between the sub-writes of the pause transition (role-execution update / interaction insert / runs update) and of the answer transition (role-execution update / interaction update / runs update) — every point is all-or-nothing, the run stays resumable, and the eventual attempt number is unchanged"
  - "tests/integration/test_redaction_interactions.py — SEC-01/SEC-02 for human_interactions.question and .answer: seeded credential shapes in a worker's question and the configured DATABASE_URL value + a token + a password= pair in the answer, swept from every interaction column, every event payload, the role-execution result and a real log sink, with paired presence (the [redacted:] marker) and absence assertions"
  - "tests/contract/test_coding_worker_contract.py — extended to exercise resume (non-null and null answer) on every parametrised worker and to pin that a NEEDS_INPUT WorkerResult with no questions cannot be constructed"
affects: ["02-07"]

# Actuals (#2632)
actuals:
  tokens: 12000
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "generic-mechanism proof by projected-remainder equality: collect two outcomes as dicts, project out only the values allowed to differ (role name, row identity), assert the remainders are equal — a stronger statement than asserting each against a literal, because it is exactly the claim 'the same code ran'"
    - "step-wise advance() over drive() for a multi-node in-process pipeline: conftest.fake_worker_registry hands back a fresh FakeWorker per registry.get(), so a multi-step drive replays script element 0; one advance() call per scripted result keeps each node's outcome distinct (the tests/db/test_lease_lost_aborts_step.py idiom)"
    - "crash-injection prefix qualified with a discriminator substring: the pause/answer runs-update injection point is ('UPDATE RUNS', 'STATUS') so it matches the lifecycle write and not the lease's own UPDATE runs (claim/renew/release touch only owner_token / lock_expires_at / updated_at)"
    - "redaction sweep of a persisted text field paired with a presence assertion on the [redacted:] marker, so a field that was never written cannot pass the absence check"

key-files:
  created:
    - "tests/db/test_pause_mechanism_generic.py"
    - "tests/db/test_pause_path_atomic.py"
    - "tests/integration/test_redaction_interactions.py"
  modified:
    - "tests/contract/test_coding_worker_contract.py"

key-decisions:
  - "test_redaction_interactions.py runs the real orchestrator entry points in-process (start_run + drive + submit_answer with advance_session_factory + real_log_sink), not as a subprocess — the presence-then-absence log-sink assertion needs the production processor chain attached in-process, exactly as its sibling test_secret_redaction_e2e.py does. The --answer value is passed verbatim to submit_answer (the function `resume --answer` calls)."
  - "The two-node pipeline's second node is named ARCHITECTURE — a value already in the RunStatus vocabulary (the pure transition function does RunStatus(node.name)) and absent from DEFAULT_PIPELINE, so it is genuinely a node the test invents."
  - "The runs-update crash-injection point is ('UPDATE RUNS', 'STATUS'), not a bare 'UPDATE RUNS' prefix: the lease's claim/renew/release also emit UPDATE runs and would otherwise be hit first. Only the lifecycle write sets status."
  - "The answer seeded into --answer is the configured credential's LITERAL value (the whole DATABASE_URL connection string), plus a ghp_ token shape and a password= pair — not a bare password fragment. known_secret_values() registers the full connection string, not its substrings; a fragment is neither a known value nor a pattern-matchable shape and is (correctly, by design) not scrubbed."

patterns-established:
  - "projected-remainder equality as a generic-mechanism proof"
  - "step-wise advance() for multi-node in-process pipeline drives under conftest.fake_worker_registry"
  - "discriminator-qualified crash-injection prefix (prefix + required substring) to disambiguate a lifecycle UPDATE from a lease UPDATE on the same table"

requirements-completed: [HITL-01, HITL-02, STATE-04]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "HITL-01 — every node of an arbitrary pipeline pauses through the same code: a two-node pipeline is injected through the runner's pipeline parameter and a NEEDS_INPUT result from either node produces a structurally identical pause (same run status, role-execution status marker, stored result, interaction status, and last two events), differing only in the recorded role name and the role-execution row identity"
    requirement: "HITL-01"
    verification:
      - kind: db
        ref: "tests/db/test_pause_mechanism_generic.py::test_either_node_pauses_with_the_same_properties[BA]"
        status: pass
      - kind: db
        ref: "tests/db/test_pause_mechanism_generic.py::test_either_node_pauses_with_the_same_properties[ARCHITECTURE]"
        status: pass
      - kind: db
        ref: "tests/db/test_pause_mechanism_generic.py::test_the_two_nodes_pause_through_structurally_identical_code"
        status: pass
    human_judgment: false
  - id: D2
    description: "HITL-01 — answering either pause returns the run to the node that asked, on the same attempt, and the run then completes through the remainder of the pipeline"
    requirement: "HITL-01"
    verification:
      - kind: db
        ref: "tests/db/test_pause_mechanism_generic.py::test_answering_either_pause_returns_to_that_node_and_the_run_completes[BA]"
        status: pass
      - kind: db
        ref: "tests/db/test_pause_mechanism_generic.py::test_answering_either_pause_returns_to_that_node_and_the_run_completes[ARCHITECTURE]"
        status: pass
    human_judgment: false
  - id: D3
    description: "HITL-02 (atomicity half) — a crash injected between any two sub-writes of the pause transition leaves none of them: the run is at its original status with no interaction row, no QUESTION_CREATED/RUN_PAUSED event and an untouched role-execution row, and it is still resumable to the same terminal state on the same attempt"
    requirement: "HITL-02"
    verification:
      - kind: db
        ref: "tests/db/test_pause_path_atomic.py::test_a_crash_between_the_pause_sub_writes_leaves_the_run_unpaused[role_execution_update|interaction_insert|runs_update]"
        status: pass
    human_judgment: false
  - id: D4
    description: "HITL-02 (atomicity half) — a crash injected between the sub-writes of the answer transition leaves the run still fully waiting: still WAITING_HUMAN, interaction still WAITING with no answer, no HUMAN_ANSWER_RECEIVED/RUN_RESUMED event, role-execution row unchanged; a later answer then succeeds and the run completes on the same attempt"
    requirement: "HITL-02"
    verification:
      - kind: db
        ref: "tests/db/test_pause_path_atomic.py::test_a_crash_between_the_answer_sub_writes_leaves_the_run_waiting[role_execution_update|interaction_update|runs_update]"
        status: pass
    human_judgment: false
  - id: D5
    description: "SEC-01/SEC-02 — a credential shape in a worker's question and the configured infrastructure credential's value in --answer are both replaced before the database: a sweep of every human_interactions column, every event payload, the role-execution result and a real log sink (production processor chain) finds zero occurrences, and the stored question and answer each carry the [redacted:] marker and are non-empty"
    requirement: "STATE-04"
    verification:
      - kind: integration
        ref: "tests/integration/test_redaction_interactions.py::test_the_cycle_completed_and_redaction_is_proven_presence_then_absence"
        status: pass
      - kind: integration
        ref: "tests/integration/test_redaction_interactions.py::test_the_stored_question_and_answer_are_markers_not_dropped_fields"
        status: pass
      - kind: integration
        ref: "tests/integration/test_redaction_interactions.py::test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site"
        status: pass
    human_judgment: false
  - id: D6
    description: "The shared coding-worker contract suite now covers resume (with a non-null and a null answer) on every parametrised worker, and pins that a NEEDS_INPUT WorkerResult with no questions cannot be constructed — so a Phase 7 real adapter cannot diverge from the fake on the path resume depends on"
    verification:
      - kind: contract
        ref: "tests/contract/test_coding_worker_contract.py::test_resume_returns_a_worker_result / test_resume_accepts_a_null_answer / test_a_needs_input_result_with_no_questions_cannot_be_constructed"
        status: pass
    human_judgment: false

# Metrics
duration: ~75min (dominated by remote-Neon test runs: ~7min db pair, ~3min integration pair, ~33min full suite)
completed: 2026-09-10
status: complete
plan_head_before: d9ab01f6f84d996427cfe05582205af503f715e9
---

# Phase 2 Plan 06: Generic Pause Mechanism, Pause/Answer Atomicity, and Interaction-Field Redaction Summary

**Three proofs about the pause path that are easy to assert and hard to notice going wrong: a two-node pipeline pauses through provably identical code with no per-role branch (HITL-01), a crash injected between any two sub-writes of the pause and of the answer is all-or-nothing with the run still resumable (HITL-02), and a credential seeded in a worker's question and one pasted into `--answer` are both swept from every persisted surface and a real log sink — proven present as a `[redacted:]` marker, not as a silently dropped field.**

## Performance

- **Duration:** ~75 min wall (most of it remote-Neon test runs)
- **Completed:** 2026-09-10
- **Tasks:** 2 of 2
- **Files created:** 3 (all test files); **modified:** 1 (the contract suite). No production change.

## Accomplishments

- **HITL-01** (`tests/db/test_pause_mechanism_generic.py`, 5 tests): a `Pipeline` of two `RoleNode`s — the real `BA` role plus a second node named `ARCHITECTURE` (a `RunStatus` value that appears in no production pipeline) — is passed through the `pipeline` keyword parameter `advance` already accepts. Parametrised over which node pauses, the test asserts for each: `runs.status` is `WAITING_HUMAN`, the current role is the node that asked, both lease columns are NULL, the latest role-execution row has status marker `WAITING_HUMAN` and stores the `NEEDS_INPUT` result on attempt 1, exactly one `WAITING` interaction row exists, and the run's last two events are `QUESTION_CREATED` then `RUN_PAUSED`. A separate test collects both outcomes as dictionaries, projects out the role name and the role-execution row identity, and asserts the remainders are equal — the honest form of "the same code ran". Answering either pause returns the run to the node that asked (`submit_answer` → the node's status), on the same attempt, and the run then completes through the remaining node (`ROLE_COMPLETED` twice, ending `RUN_COMPLETED`).
- **HITL-02 (atomicity half)** (`tests/db/test_pause_path_atomic.py`, 6 tests): the `after_cursor_execute` crash-injection recipe from `tests/db/test_transition_atomic.py`, its injection-point map extended with the interaction insert (pause) and the interaction update (answer). Parametrised over 3 pause injection points and 3 answer injection points; for each, the injected `_InjectedCrash` fires inside `apply_transition`'s single `with session.begin()` block and the post-rollback state is asserted all-or-nothing — no interaction row / no pause events / untouched role-execution row after a pause crash; still `WAITING_HUMAN` with the interaction still `WAITING` and no resume events after an answer crash — and in every case the run is then driven to `COMPLETED` on the unchanged attempt number, and a later answer succeeds after an answer crash.
- **SEC-01 / SEC-02 for the two new text fields** (`tests/integration/test_redaction_interactions.py`, 3 tests): a sibling of `test_secret_redaction_e2e.py`. A worker's `NEEDS_INPUT` question embeds a connection-string shape and a `ghp_` token shape; the answer passed to `submit_answer` (the value `resume --answer` forwards) embeds the configured `DATABASE_URL` literal value, a token shape and a `password=` pair. The whole cycle runs in-process under `real_log_sink`. The sweep covers **every column of the run's `human_interactions` row** (`question`, `answer`, `status`, `role_execution_id`), **every `run_events.payload`**, **`role_executions.result`/`.error`** (which holds the serialised `NEEDS_INPUT` outcome, hence the question), and **a real structlog sink carrying the production processor chain** — asserted presence-then-absence so a never-written field cannot pass. A structural test pins that the scrubbing happens in `_write_human_interaction` (the one mutation-path call site) and that `orchestrator/runner.py` contains no `redact(` call on the pause path.
- **Worker contract extended** (`tests/contract/test_coding_worker_contract.py`, +3 tests): `resume` is exercised on every parametrised worker with a non-null and a null answer; a `NEEDS_INPUT` `WorkerResult` with an empty question list is pinned as unconstructable.

## Task Commits

1. **Task 1: HITL-01 generic pause mechanism + HITL-02 pause/answer atomicity** — `2a9dced` (`test(02-06)`)
2. **Task 2: sweep the two new persisted text fields for credentials; contract covers resume** — `cb6ea31` (`test(02-06)`)

**Plan metadata:** _(this commit)_ — SUMMARY.md, STATE.md, ROADMAP.md, REQUIREMENTS.md, deferred-items.md.

`plan_head_before = d9ab01f6f84d996427cfe05582205af503f715e9`; `git rev-list --count d9ab01f..HEAD` (pre-metadata) = **2** task commits.

## RED / GREEN / REFACTOR notes

Both tasks carry `tdd="true"` and both list only test files in `files_modified` — production modules are conditional, "if a proof turns up a real gap". **No gap was found**, so this is a proof-only plan with one `test(02-06)` commit per task, exactly like 02-04 and 02-05.

- **RED:** each proof was written against the mechanism 02-03 shipped and run. None failed for a real-defect reason. Two iterations were needed, both test-authoring corrections:
  - `test_pause_mechanism_generic.py` first used `drive` for the two-node pipeline and the `ARCHITECTURE`-node parametrisations reached `COMPLETED` instead of `WAITING_HUMAN`. Cause: `conftest.fake_worker_registry` returns a **fresh** `FakeWorker` on every `registry.get()` call, so a multi-step `drive` replays script element 0. Fixed by stepping with one `advance()` call per scripted result (the `test_lease_lost_aborts_step.py` idiom). Not a production issue — `default_registry` uses a process-lifetime `FakeWorker` whose cursor advances, and real adapters are stateless per call.
  - `test_redaction_interactions.py` first seeded the answer with a bare DB-password fragment, which was (correctly) not redacted — `known_secret_values()` registers the whole `DATABASE_URL` connection string, not its substrings, and a bare alphanumeric fragment matches no D-15 pattern. Fixed to seed the configured credential's **literal value** (the full connection string) plus a token shape and a `password=` pair; all three are then scrubbed. This is a test correction, **not a production gap** — redaction scrubs the configured value and pattern-shaped secrets as designed.
- **GREEN:** no `feat(02-06)` / `fix(02-06)` commit — there is no production change to make. All 17 new tests pass; the full suite is 349 passed.
- **REFACTOR:** none.

## Recorded details (for 02-07 to assert against)

**Crash-injection point map** (`test_pause_path_atomic.py`), each entry `(upper-cased left-stripped statement prefix, required substring | None)`:

| Transition | Point key | Prefix | Discriminator |
|---|---|---|---|
| pause | `role_execution_update` | `UPDATE ROLE_EXECUTIONS` | — |
| pause | `interaction_insert` | `INSERT INTO HUMAN_INTERACTIONS` | — |
| pause | `runs_update` | `UPDATE RUNS` | `STATUS` |
| answer | `role_execution_update` | `UPDATE ROLE_EXECUTIONS` | — |
| answer | `interaction_update` | `UPDATE HUMAN_INTERACTIONS` | — |
| answer | `runs_update` | `UPDATE RUNS` | `STATUS` |

The `STATUS` discriminator makes the `runs_update` point match the lifecycle write and skip the lease's own `UPDATE runs` (`claim_lease` / `renew_lease` / `release_lease` set only `owner_token` / `lock_expires_at` / `updated_at`).

**Redaction sweep surfaces** (`test_redaction_interactions.py`):
1. every column of the run's `human_interactions` row — `question`, `answer`, `status`, `role_execution_id`
2. every `run_events.payload` for the run
3. `role_executions.result` + `.error` for the run
4. a real `structlog` sink with the production processor chain (`tests.support.log_sink.real_log_sink`), presence-then-absence

**Structural-identity comparison shape** (`test_pause_mechanism_generic.py::_pause_outcome`): a dict whose `_`-prefixed keys — `_current_role`, `_role_execution_id`, `_role_execution_role` — are **projected out**; the compared remainder is `{run_status, lease_owner_token_null, lease_expiry_null, role_execution_status_marker, role_execution_attempt, stored_result_status, stored_result_questions, interaction_count, interaction_status, last_two_events}`.

## Decisions Made

See `key-decisions` frontmatter. The load-bearing ones: (1) the redaction proof runs the real orchestrator entry points **in-process** (not a subprocess) because the presence-then-absence log-sink assertion needs the production processor chain attached in-process — the same choice `test_secret_redaction_e2e.py` makes; the `--answer` string is passed verbatim to `submit_answer`. (2) The `runs_update` crash-injection prefix is qualified with `STATUS` so the lease's `UPDATE runs` is not hit first. (3) The answer seeds the configured credential's whole literal value, not a fragment — `known_secret_values()` registers the connection string, not its substrings.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test bug] Multi-step `drive` replayed script element 0 for the two-node pipeline**
- **Found during:** Task 1 (first run — `test_either_node_pauses_with_the_same_properties[ARCHITECTURE]` reached `COMPLETED`, not `WAITING_HUMAN`)
- **Issue:** `conftest.fake_worker_registry` registers `lambda: FakeWorker(list(script), ...)`, so every `registry.get("fake")` call inside a multi-step `drive` returns a fresh worker with its cursor at 0 — the second node re-ran script element 0 (`COMPLETED`) instead of element 1 (`NEEDS_INPUT`).
- **Fix:** step the run with one `advance()` call per scripted result (a fresh single-element registry each call), the `tests/db/test_lease_lost_aborts_step.py` idiom. Each node's outcome stays distinct while still exercising the one signal-dispatch branch.
- **Files modified:** `tests/db/test_pause_mechanism_generic.py`
- **Verification:** `pytest -m db tests/db/test_pause_mechanism_generic.py` → 5 passed.
- **Committed in:** `2a9dced` (Task 1)

**2. [Rule 1 - Test bug] Answer seeded with a bare password fragment that is not a configured secret**
- **Found during:** Task 2 (first integration run — `assert "[redacted:" in swept.answer` failed; the fragment `int06SUPERSECRETpw012345` survived verbatim)
- **Issue:** `known_secret_values()` registers `settings.database_url.get_secret_value()` — the whole connection string — not its substrings. A bare alphanumeric password fragment is neither a known value nor a D-15 pattern shape, so `redact()` correctly does not touch it. The test's seed was wrong, not the redaction.
- **Fix:** seed the answer with the configured credential's **literal value** (the full `_FAKE_DB_URL` connection string) plus a `ghp_` token shape and a `password=<value>` pair; assert all three are replaced by their `[redacted:]` markers and the bare-password substring is gone as a consequence of the whole URL being scrubbed.
- **Files modified:** `tests/integration/test_redaction_interactions.py`
- **Verification:** `pytest -m integration tests/integration/test_redaction_interactions.py tests/integration/test_secret_redaction_e2e.py` → 8 passed.
- **Committed in:** `cb6ea31` (Task 2)

---

**Total deviations:** 2, both test-authoring corrections made before the respective task commits. **No production code changed.** No scope creep — every stated success criterion is proven.

## Issues Encountered

- **`conftest.fake_worker_registry` per-`get()` freshness vs. multi-node in-process drives** — resolved by stepping with `advance()` (deviation 1). The fixture's docstring already flags this; only the default registry advances a cursor across `drive` steps.
- **Multi-node `role_executions` row reuse** — surfaced while building the two-node pipeline: `_run_current_role` inserts no `RUNNING` row for nodes after the first, so the second node updates the first node's row (`.role` stays `"BA"` while `runs.current_role` moves on). **Out of scope for 02-06** (Phase 1's pipeline is single-node; Phase 3 makes it configuration-driven) and it does not affect the genericness claim — both nodes still hit the one `Signal.ROLE_NEEDS_INPUT` branch, which is why the structural-identity test projects the row identity out. Logged to `deferred-items.md` § 02-06.
- **Remote-Neon test latency** — the db pair runs ~7 min, the integration pair ~3 min, the full suite 33 min. Consistent with 02-03/02-04/02-05. All tiers exit 0.

## Known Stubs

None. Every path is a real end-to-end proof: real `start_run` / `advance` / `drive` / `submit_answer` against real PostgreSQL, real `after_cursor_execute` crash injection inside the real `apply_transition` transaction, real `redact()` at the real `_write_human_interaction` call site, and the real `structlog` production processor chain via `real_log_sink`.

## Broken-windows ledger

One `--kind deviation` entry appended for the multi-node `role_executions` row-reuse observation (also in `deferred-items.md`). It is an out-of-scope discovery, not a stub or skipped test in this plan's own files — all 17 new tests are live and passing.

## Requirements status (shared-ID gate)

The plan's `requirements: [HITL-01, HITL-02, STATE-04]` all remain **Pending** in `REQUIREMENTS.md`. Every one is also declared by `02-07` (the phase acceptance gate), which has no `*-SUMMARY.md` yet, so the shared-ID gate keeps them Pending until `02-07` finishes and marks them Complete. This plan ships and proves: HITL-01 in full (generic mechanism, projected-remainder identity), the atomicity half of HITL-02 (crash between every sub-write of both transitions), and extends the STATE-04 redaction guarantee to `human_interactions.question` / `.answer`.

## Next Phase Readiness

- **02-07** (phase acceptance gate): the deliverables map by name —
  HITL-01 → `tests/db/test_pause_mechanism_generic.py`,
  HITL-02 (atomicity) → `tests/db/test_pause_path_atomic.py`,
  the interaction-field security criterion → `tests/integration/test_redaction_interactions.py`,
  the resume contract → `tests/contract/test_coding_worker_contract.py`.
  The exact crash-injection prefix map, sweep surface list and structural-identity comparison shape are tabulated above.
- **Phase 3** (configuration-driven pipeline): `deferred-items.md` § 02-06 records the multi-node `role_executions` insert that belongs there.

---
*Phase: 02-pause-resume-single-owner-execution*
*Completed: 2026-09-10*

## Self-Check: PASSED

- All created files present on disk: `tests/db/test_pause_mechanism_generic.py`, `tests/db/test_pause_path_atomic.py`, `tests/integration/test_redaction_interactions.py`, `.planning/phases/02-pause-resume-single-owner-execution/02-06-SUMMARY.md`; `tests/contract/test_coding_worker_contract.py` modified.
- Both task commits present in history: `2a9dced` (`test(02-06)` — HITL-01 generic pause + HITL-02 atomicity), `cb6ea31` (`test(02-06)` — interaction-field redaction sweep + resume contract).
- Full `<verification>` green: `pytest -q` → **349 passed** (33m27s); `mypy src/dark_factory` → Success, no issues in 39 files; `ruff check .` → All checks passed.
- `git rev-list --count d9ab01f..HEAD` (pre-metadata) = 2, matching `actuals.commits: 2`.
