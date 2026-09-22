---
phase: 08-copilot-hermes-worker-independence-proven
verified: 2026-09-22T14:50:00Z
status: passed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "SC1 — `hermes` executes a role non-interactively and unattended in a clean container with no pre-existing CLI state, returning a normalized WorkerResult (the live-binary, real-credential half of the claim)"
    reason: "During this phase's own UAT session (08-UAT.md, 2026-09-22), the user installed and authenticated real `copilot` and `claude-code` binaries and ran the three live suites; both passed. The user then explicitly decided Hermes live-CLI testing is out of scope for this project ('Hermes deliberately out of scope for this project per user decision (2026-09-22) -- test_hermes_live.py remains SKIPPED by design, not a defect. Accepted as pass.'). This verification independently re-ran the three live suites in this session and reproduced the identical result (2 passed, 1 skipped with a named reason). The mechanism (skip-guard, redaction, non-interactive spawn) is fully proven at the unit/contract level for all three adapters including Hermes; only the literal live-binary exercise is deliberately not attempted for Hermes, and that is the user's own documented call, not an unresolved gap."
    accepted_by: "user (recorded in 08-UAT.md Test 1)"
    accepted_at: "2026-09-22"
re_verification:
  previous_status: human_needed
  previous_score: 4/7
  gaps_closed:
    - "SC1 (Copilot + Claude Code halves) — copilot and claude-code live suites now independently confirmed PASSED against real installed binaries and real credentials (2 passed, 1 skipped for the out-of-scope Hermes case), not merely collected-and-skipped"
    - "SC2 (WORK-09) 'run still completes' half — tests/integration/test_role_reassignment_sc2.py now independently confirmed passing against a real PostgreSQL instance, not merely collection-verified"
    - "CR-01 closure end-to-end proof — tests/integration/test_artifact_scope_enforcement.py's three scenarios (Hermes negative, Copilot negative, positive control) now independently confirmed passing against a real PostgreSQL instance, closing gap G-08-2 (a test-harness exit-code assertion bug, not a production defect) along the way"
  gaps_remaining: []
  regressions: []
covered_files: [".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".planning/REQUIREMENTS.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-01-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-01-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-02-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-03-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-03-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-04-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-04-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-05-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-06-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-06-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-REVIEW.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-SECURITY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-UAT.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-VALIDATION.md", "src/dark_factory/cli.py", "src/dark_factory/config/loader.py", "src/dark_factory/config/settings.py", "src/dark_factory/git/__init__.py", "src/dark_factory/git/scope.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/tools/env.py", "src/dark_factory/tools/native.py", "src/dark_factory/workers/claude_code.py", "src/dark_factory/workers/cli_runtime.py", "src/dark_factory/workers/copilot.py", "src/dark_factory/workers/fake.py", "src/dark_factory/workers/hermes.py", "src/dark_factory/workers/registry.py", "tests/contract/test_coding_worker_contract.py", "tests/db/test_artifact_commit_per_role.py", "tests/db/test_artifact_persistence.py", "tests/db/test_four_role_pipeline.py", "tests/integration/test_artifact_scope_enforcement.py", "tests/integration/test_claude_code_live.py", "tests/integration/test_copilot_live.py", "tests/integration/test_hermes_live.py", "tests/integration/test_real_pipeline_zero_config.py", "tests/integration/test_role_reassignment_sc2.py", "tests/support/fake_artifacts.py", "tests/support/fake_claude_cli.py", "tests/support/fake_cli.py", "tests/support/fake_copilot_cli.py", "tests/support/fake_hermes_cli.py", "tests/support/live_runtime.py", "tests/unit/test_artifact_scope.py", "tests/unit/test_claude_code_worker.py", "tests/unit/test_copilot_worker.py", "tests/unit/test_every_real_adapter_has_a_live_suite.py", "tests/unit/test_fake_cli_declared_outputs.py", "tests/unit/test_git_ownership_boundary.py", "tests/unit/test_hermes_worker.py", "tests/unit/test_native_tool_contract.py", "tests/unit/test_no_role_name_literal.py", "tests/unit/test_no_tree_walk.py", "tests/unit/test_no_worker_name_leak.py", "tests/unit/test_worker_capabilities_match_behaviour.py", "tests/unit/test_write_scope.py"]
covered_digest: "v1:sha256:64c3a7a0243e3c4261fae68a07732bbf85ef0883adab73e33ceea51d5e0c3b6f"
---

# Phase 8: Copilot & Hermes — Worker Independence Proven Verification Report

**Phase Goal:** The same role runs unchanged on three genuinely different runtimes, chosen in config. Reassigning roles across the three runtimes in configuration (e.g. Architect on Copilot, Developer on Claude Code, QA on Hermes) requires no change to workflow code and the run still completes.
**Verified:** 2026-09-22T14:50:00Z
**Status:** passed
**Re-verification:** Yes — following plan 08-06's gap closure (G-08-2) and this session's own independent re-execution of every DB-gated and live-binary-gated proof this verifier's prior run (2026-09-22T05:01:45Z, `human_needed`, 4/7) could not run for itself.

## Methodology note: independent re-execution, not SUMMARY trust

Per this agent's mandate, every claim below that a test "passes" was reproduced by this
verification session running the command itself — not by reading a SUMMARY.md or UAT.md
assertion and accepting it. Specifically, this session independently ran, in its own
process, with its own shell sourcing `DARK_FACTORY_TEST_DATABASE_URL`:

- `pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py tests/integration/test_exit_codes.py` → **10 passed in 353.62s**, against a real PostgreSQL instance.
- `pytest -m "unit or contract" -q` → **640 passed, 322 deselected in 221.56s**.
- `pytest -m db -q tests/db/test_artifact_persistence.py tests/db/test_four_role_pipeline.py tests/db/test_artifact_commit_per_role.py` → **8 passed in 297.54s**, against the same real PostgreSQL instance.
- `pytest -q -rs tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py tests/integration/test_claude_code_live.py` → **2 passed, 1 skipped** (Hermes skipped, named reason: `'hermes' not found on PATH`) — against genuinely installed `copilot`/`claude` binaries and real configured credentials (`Settings().copilot_github_token`/`.anthropic_api_key` both non-`None` in this environment).
- `mypy src/dark_factory` → clean. `ruff check .` → all checks passed. `ruff format --check .` → all files formatted.
- Direct code reads (not doc claims) of `src/dark_factory/orchestrator/runner.py` (lines 896-981), `src/dark_factory/cli.py` (`_CLEAN_FINALS`, `_drive_and_exit`), `src/dark_factory/workers/hermes.py` (`spawn_is_permitted`), `src/dark_factory/tools/env.py` (`build_worker_env`), and the AST-structural check for the D-05 cross-check in `tests/integration/test_artifact_scope_enforcement.py` — all re-run/re-read independently, all confirming the claims in 08-05/08-06's SUMMARYs.
- `git diff --numstat 99e9152..HEAD -- src/dark_factory/cli.py` → empty; `git log --oneline -1 -- src/dark_factory/cli.py` → last touched at phase-03 commit `6f0d633`, confirming zero production change to the exit-code contract across all of phase 8.
- Registry and role-config state read live from the interpreter: `default_registry.names() == {'claude-code','copilot','fake','hermes'}`; `.dark-factory/roles/*.yaml` parse to `{QA: hermes, DEVELOPMENT: claude-code, ARCHITECTURE: copilot, BA: fake}`.

This session's own prior verification pass (`08-VERIFICATION.md`, now overwritten) was `human_needed`
at 4/7 specifically because no reachable PostgreSQL 17 and no live binaries existed in that verifier's
sandbox. Plan 08-06 and this session's own UAT round changed that: a real PostgreSQL instance and real
`copilot`/`claude-code` binaries are now reachable, and every one of the previously-deferred proofs has
now actually been run — by this verification, independently, not merely reported as run.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 — `copilot`/`claude-code`/`hermes` execute a role non-interactively/unattended in a clean container, returning a normalized `WorkerResult` | ✓ VERIFIED (override for Hermes live-binary portion) | Copilot and Claude Code: independently re-run against real installed binaries and real credentials this session — **2 passed**. The full mechanism (spawn, timeout+process-group-kill, non-zero exit, missing binary, missing credential, NEEDS_INPUT, redaction) is proven at the unit level for all three adapters, including Hermes (93+35+30 tests, all passing). Hermes's own live-binary exercise is explicitly out of scope per a dated, documented user decision recorded in 08-UAT.md — see `overrides` above. |
| 2 | SC2 (WORK-09) — role reassignment via configuration alone, no workflow-code change, run still completes | ✓ VERIFIED | Configuration confirmed live from the interpreter: `ARCHITECTURE→copilot`, `DEVELOPMENT→claude-code`, `QA→hermes`, `BA→fake`. `tests/no_worker_name_leak.py`/`test_no_role_name_literal.py` re-run independently: 4 passed. `test_role_reassignment_sc2.py` independently re-run against a real PostgreSQL instance as part of the 10-test integration set: **passed** — the paired-run equality proof (three-runtime run vs. all-`fake` run: identical terminal status, role sequence, artifact-type sets, differing only on the persisted worker name) and its negative case (no fake binaries on `PATH` → visible failure, no silent substitution) both hold. |
| 3 | SC3 — each adapter has its own skip-guarded live suite; the shared `CodingWorker` contract suite passes over all four workers with no live binary/credential | ✓ VERIFIED | `pytest -q -rs` on the three live modules (re-run, real environment): 2 passed, 1 skipped with a named reason, 0 failed, 0 errored. `WORKER_FACTORIES` confirmed length 4 by direct read of `tests/contract/test_coding_worker_contract.py`. Full contract+unit suite (640 tests) passes. |
| 4 | SC4 — each adapter's declared `WorkerCapabilities` matches its own observed behaviour | ✓ VERIFIED | `tests/unit/test_worker_capabilities_match_behaviour.py` included and passing in the independently re-run 640-test unit/contract suite (parametrized over all four workers, argv/observed-behaviour checks, not restated literals). |
| 5 | CR-01 closure (08-REVIEW.md BLOCKER) — a granted `artifacts.write` is confined to a role's own `artifacts/<role>/` subtree on every worker | ✓ VERIFIED | `enforce_artifact_scope` confirmed wired into `orchestrator/runner.py` by direct code read: called at line 910, strictly before `collect_role_artifacts` (923), `commit_run_artifacts` (959) and `push_working_branch` (967). Unit level: 17/17 passing (`test_artifact_scope.py`). End-to-end: `tests/integration/test_artifact_scope_enforcement.py`'s three scenarios (Hermes negative, Copilot negative, positive control) independently re-run against a real PostgreSQL instance as part of the 10-test set — **all 3 passed**, closing the real-subprocess-plus-real-database gap the prior verification round left open. |
| 6 | G-08-2 closure — the CR-01 negative-path proofs assert the CLI exit code D-05 actually contracts for a persisted `FAILED` run, and the harness self-checks that contract | ✓ VERIFIED | Independently confirmed via `grep`: `_D05_SUCCESS_STATUSES = frozenset({"COMPLETED", "WAITING_HUMAN"})` matches `src/dark_factory/cli.py`'s own `_CLEAN_FINALS = (RunStatus.COMPLETED, RunStatus.WAITING_HUMAN)` exactly. The exact AST-structural check from plan 08-06's own acceptance criteria was independently re-run and printed `D-05 cross-check present via _D05_SUCCESS_STATUSES`. `git diff --numstat 99e9152..HEAD -- src/dark_factory/cli.py` empty and `git log -1 -- src/dark_factory/cli.py` shows last change at phase-03 commit `6f0d633` — the CLI's exit mapping is untouched. |
| 7 | WR-02/WR-03 closure — `NATIVE_TOOL_CONTRACT`'s Copilot `artifacts.*` prose and both adapters' granted-case documentation state the real enforcement posture | ✓ VERIFIED | Read directly from `src/dark_factory/workers/hermes.py::spawn_is_permitted`'s docstring: confirms a granted `artifacts.write` is "confined to the role's own `artifacts/<role>/` subtree only after the fact, by ... `enforce_artifact_scope`" and a granted `artifacts.read` "carries reach identical to `repo.read`, with no mechanism ... narrowing it" — matching the claimed posture exactly, not merely restated from the SUMMARY. `test_native_tool_contract.py` passing in the re-run suite. |
| 8 | Requirements traceability — WORK-05, WORK-06, WORK-09, QUAL-03, ROLE-05, TOOL-03 are each backed by real, passing code/tests; no Phase-8-mapped requirement is orphaned | ✓ VERIFIED | `.planning/REQUIREMENTS.md` maps WORK-05, WORK-06, WORK-09, QUAL-03 to Phase 8 (all `Complete`); ROLE-05 (Phase 5) and TOOL-03 (Phase 6) are correctly extended, not newly claimed, by plans 08-05/08-06 — confirmed by direct `grep` against REQUIREMENTS.md's own phase mapping. `grep -n "Phase 8"` finds exactly WORK-05, WORK-06, WORK-09, QUAL-03 — no orphans. |

**Score:** 8/8 truths verified (1 carries an accepted, documented override for the Hermes live-binary portion of SC1; 0 present-but-behaviour-unverified — every previously-deferred behavioural claim was independently re-executed this session)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/workers/copilot.py` | Real `CopilotWorker` adapter | ✓ VERIFIED | `default_registry.get("copilot")` confirmed live to return a `CopilotWorker` instance; live-binary exercise passed this session. |
| `src/dark_factory/workers/hermes.py` | Real `HermesWorker` adapter with `spawn_is_permitted` | ✓ VERIFIED | `default_registry.get("hermes")` confirmed live; `spawn_is_permitted` docstring read directly and matches claimed granted/denied-case posture. |
| `src/dark_factory/workers/cli_runtime.py` | Shared CLI-adapter runtime | ✓ VERIFIED | Imported by `claude_code.py`, `copilot.py`, `hermes.py`; exercised across all passing suites. |
| `src/dark_factory/git/scope.py` — `enforce_artifact_scope` | Sibling post-hoc artifact-scope control | ✓ VERIFIED | Present, unit-tested (17 cases, re-run), wired into `orchestrator/runner.py` at line 910 (confirmed by direct code read), end-to-end proof re-run and passing against real Postgres. |
| `.dark-factory/roles/{ARCHITECTURE,DEVELOPMENT,QA}.yaml` | Reassigned `worker:` lines | ✓ VERIFIED | Confirmed live from the interpreter: `copilot`/`claude-code`/`hermes` respectively; `BA.yaml` unchanged on `fake`. |
| `tests/support/live_runtime.py`, `tests/integration/test_*_live.py` | Skip-guarded live suites | ✓ VERIFIED | Re-run this session against real binaries: 2 passed, 1 skipped with named reason. |
| `tests/integration/test_role_reassignment_sc2.py`, `test_artifact_scope_enforcement.py` | DB-gated integration proofs | ✓ VERIFIED | Both modules re-run this session against a real PostgreSQL instance; all contained tests pass (part of the 10/10 result). |
| `tests/integration/test_artifact_scope_enforcement.py`'s `_drive_shipped_config` harness | Per-caller `expected_exit` + D-05 cross-check (G-08-2 repair) | ✓ VERIFIED | AST-structural check re-run independently: cross-check present. `expected_exit=` appears exactly 3 times (one per caller), confirmed by `grep`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `workers/registry.py` | `CopilotWorker`/`HermesWorker` | `default_registry.register(...)` | WIRED | Confirmed live: `default_registry.names() == {"hermes","copilot","fake","claude-code"}`. |
| `orchestrator/runner.py` | `git.scope.enforce_artifact_scope` | direct call, before artifact collect/commit/push | WIRED | Confirmed by direct code read: call at line 910, `collect_role_artifacts` at 923, `commit_run_artifacts` at 959, `push_working_branch` at 967 — strict ordering held. |
| `.dark-factory/roles/*.yaml` `worker:` | `config/loader.py` → persisted snapshot → `registry.get(node.worker)` | configuration-only reassignment | WIRED | `test_no_worker_name_leak.py`/`test_no_role_name_literal.py` re-run: 4 passed — no runtime name appears outside `workers/`/`config/`. |
| `src/dark_factory/cli.py::_drive_and_exit` | `tests/integration/test_artifact_scope_enforcement.py`'s D-05 cross-check | shared exit-code contract | WIRED | `_CLEAN_FINALS` (source) and `_D05_SUCCESS_STATUSES` (test guard) confirmed to name the identical two statuses; `cli.py` confirmed untouched since phase 3. |

### Behavioral Spot-Checks / Independent Re-Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit+contract suite | `uv run pytest -m "unit or contract" -q` | 640 passed, 322 deselected in 221.56s | ✓ PASS |
| mypy strict | `uv run mypy src/dark_factory` | Success: no issues found in 67 source files | ✓ PASS |
| ruff check | `uv run ruff check .` | All checks passed | ✓ PASS |
| ruff format check | `uv run ruff format --check .` | 526 files already formatted | ✓ PASS |
| DB-gated UAT Test 2 command set + D-05 guard | `pytest -m integration -q test_role_reassignment_sc2.py test_real_pipeline_zero_config.py test_artifact_scope_enforcement.py test_exit_codes.py` | 10 passed in 353.62s | ✓ PASS |
| Cross-role db-tier fixture tests (LazyFourRoleWorker fix) | `pytest -m db -q test_artifact_persistence.py test_four_role_pipeline.py test_artifact_commit_per_role.py` | 8 passed in 297.54s | ✓ PASS |
| Live suites against real binaries | `pytest -q -rs test_copilot_live.py test_hermes_live.py test_claude_code_live.py` | 2 passed, 1 skipped (named reason) | ✓ PASS |
| Registry has no placeholders | direct Python import/instantiation | `copilot`/`hermes`/`claude-code`/`fake` all resolve to real classes | ✓ PASS |
| No worker-name leak / no role-name literal | `pytest -m unit -q test_no_worker_name_leak.py test_no_role_name_literal.py` | 4 passed | ✓ PASS |
| D-05 structural cross-check (AST) | plan 08-06's own acceptance-criteria Python snippet | printed "D-05 cross-check present via _D05_SUCCESS_STATUSES" | ✓ PASS |
| `cli.py` untouched by phase 8 | `git diff --numstat 99e9152..HEAD -- src/dark_factory/cli.py`; `git log -1 -- src/dark_factory/cli.py` | empty diff; last touch = phase-03 commit `6f0d633` | ✓ PASS |

### Anti-Patterns Found

No debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`) found in any of the phase's core adapter/scope-enforcement files (`copilot.py`, `hermes.py`, `cli_runtime.py`, `git/scope.py`, `orchestrator/runner.py`) — confirmed by direct `grep`.

Carried forward from `08-REVIEW.md`, all explicitly out of this phase's declared must-haves and correctly rated below BLOCKER — none block this verification:

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/dark_factory/git/scope.py` / `git/diff.py` | WR-04 — `enforce_artifact_scope`/`enforce_write_scope` deliberately do not cover the run tree's `verification/`, `logs/`, `input/` directories. | Warning | Explicitly named as out of CR-01's scope by the reviewer; candidate for a future phase (e.g. Phase 9's quality-gate work). Not a regression. |
| `src/dark_factory/tools/env.py`, `workers/hermes.py`, `workers/cli_runtime.py` | WR-01 — role-name/attempt values interpolated into filesystem paths with no character-allowlist validation. | Warning | Low likelihood today (role names originate only from trusted `.dark-factory/roles/*.yaml`); untouched by this session beyond whitespace-only `ruff format`. |
| `tests/unit/test_artifact_scope.py:243-274` | IN-02 — a multi-violation assertion checks `"3" in message`, satisfiable by a coincidental UUID digit. | Info | Test-quality nit; the code under test renders the attempt number correctly (confirmed by direct reading). |
| `.dark-factory/roles/DEVELOPMENT.yaml` | IN-01 — `repo.write` makes the `artifacts.write` grant's Claude-Code path-scoped specifier redundant. | Info | Harmless role-config smell, no functional impact. |
| `tests/support/fake_artifacts.py` | IN-03 — `four_role_script` now has zero callers, duplicating `_FOUR_ROLE_FILES`'s content with nothing enforcing the two stay in sync. | Info | Dead-code/duplication nit found this session; no functional impact, both `ruff`/`mypy` clean on the file. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|-------------|--------|----------|
| WORK-05 | 08-01, 08-05, 08-06 | `CopilotWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | ✓ SATISFIED | Real adapter, registered, unit suite passing, contract-suite-pinned, live-binary exercise independently re-run and passing this session; CR-01/WR-02 closure (08-05) hardens its `artifacts.*` posture. |
| WORK-06 | 08-02, 08-05, 08-06 | `HermesWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | ✓ SATISFIED | Real adapter, registered, unit suite passing, `spawn_is_permitted` admission rule confirmed by direct code read, contract-suite-pinned. Live-binary exercise carries an accepted, documented override (see `overrides`). |
| WORK-09 | 08-04 | Any role can be assigned to any supported worker via configuration with no change to workflow code | ✓ SATISFIED | Role YAMLs confirmed reassigned live; `test_no_worker_name_leak.py` passes; the "run still completes" proof independently re-run against real PostgreSQL and passing this session — no longer a deferred claim. |
| QUAL-03 | 08-03 | Each real worker adapter has its own integration test suite, skipped when credentials are absent | ✓ SATISFIED | Three skip-guarded live suites independently re-run: 2 passed against real binaries, 1 skipped with a named, accepted reason. |
| ROLE-05 (extended, owned by Phase 5) | 08-05, 08-06 | A role's permitted write scope is enforced after execution | ✓ SATISFIED (extension) | `enforce_artifact_scope` extends the Phase-5 write-scope mechanism to the artifacts subtree; end-to-end proof independently re-run and passing. |
| TOOL-03 (extended, owned by Phase 6) | 08-05 | Each role receives only its explicitly configured tools, deny-by-default | ✓ SATISFIED (extension) | Copilot/Hermes translation tables and contract prose confirmed to state the real posture by direct code read. |

No orphaned requirements: `.planning/REQUIREMENTS.md` maps exactly WORK-05, WORK-06, WORK-09, QUAL-03 to Phase 8 (all `Complete`); ROLE-05 and TOOL-03 are correctly attributed to their original phases (5 and 6 respectively) while being genuinely extended here — confirmed by direct `grep` against REQUIREMENTS.md, not assumed.

### Gaps Summary

No gaps. This is a re-verification following plan 08-06's gap closure (G-08-2) and this session's own UAT round, both of which supplied the one thing the prior verification pass (`human_needed`, 4/7) lacked: a reachable real PostgreSQL instance and real `copilot`/`claude-code` binaries. Every one of the three previously-deferred human-verification items has now been independently re-executed by this verification itself, not merely read from a SUMMARY or UAT record:

1. **Live-binary clean-container proof (SC1):** Copilot and Claude Code now pass against genuinely installed binaries and credentials, confirmed by this verification's own `pytest` run. Hermes's live-binary portion carries one accepted, dated, documented override (the user's own explicit decision in `08-UAT.md`, not this verifier's judgment call) — the underlying mechanism is still fully proven at the unit level for Hermes, including the redaction, timeout, and NEEDS_INPUT paths.
2. **SC2/WORK-09 "run still completes" half:** independently re-run against real PostgreSQL — passed.
3. **CR-01 end-to-end artifact-scope enforcement:** independently re-run against real PostgreSQL — passed, along with the exit-code contract repair (G-08-2) that plan 08-06 correctly diagnosed as a test-harness bug (not a production defect) and fixed with zero change to `src/dark_factory/cli.py`.

The four Warning/Info findings carried in `08-REVIEW.md` (WR-01, WR-04, IN-01, IN-02) plus one new Info finding (IN-03) are all explicitly out of this phase's declared must-haves or genuinely low-impact code-quality nits — none block phase completion, and all were confirmed still accurately characterized as non-blocking by this verification's own reading of the review's evidence.

---

_Verified: 2026-09-22T14:50:00Z_
_Verifier: Claude (gsd-verifier)_
