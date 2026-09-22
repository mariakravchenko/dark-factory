---
phase: 08-copilot-hermes-worker-independence-proven
verified: 2026-09-22T05:01:45Z
status: human_needed
score: 4/7 truths verified
behavior_unverified: 3
covered_files: [".dark-factory/roles/ARCHITECTURE.yaml", ".dark-factory/roles/BA.yaml", ".dark-factory/roles/DEVELOPMENT.yaml", ".dark-factory/roles/QA.yaml", ".planning/REQUIREMENTS.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-01-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-01-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-02-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-03-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-03-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-04-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-04-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-05-PLAN.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md", ".planning/phases/08-copilot-hermes-worker-independence-proven/08-REVIEW.md", "src/dark_factory/config/settings.py", "src/dark_factory/git/__init__.py", "src/dark_factory/git/scope.py", "src/dark_factory/orchestrator/runner.py", "src/dark_factory/tools/env.py", "src/dark_factory/tools/native.py", "src/dark_factory/workers/claude_code.py", "src/dark_factory/workers/cli_runtime.py", "src/dark_factory/workers/copilot.py", "src/dark_factory/workers/fake.py", "src/dark_factory/workers/hermes.py", "src/dark_factory/workers/registry.py", "tests/contract/test_coding_worker_contract.py", "tests/integration/test_artifact_scope_enforcement.py", "tests/integration/test_claude_code_live.py", "tests/integration/test_copilot_live.py", "tests/integration/test_hermes_live.py", "tests/integration/test_real_pipeline_zero_config.py", "tests/integration/test_role_reassignment_sc2.py", "tests/support/fake_claude_cli.py", "tests/support/fake_cli.py", "tests/support/fake_copilot_cli.py", "tests/support/fake_hermes_cli.py", "tests/support/live_runtime.py", "tests/unit/test_artifact_scope.py", "tests/unit/test_claude_code_worker.py", "tests/unit/test_copilot_worker.py", "tests/unit/test_every_real_adapter_has_a_live_suite.py", "tests/unit/test_fake_cli_declared_outputs.py", "tests/unit/test_git_ownership_boundary.py", "tests/unit/test_hermes_worker.py", "tests/unit/test_native_tool_contract.py", "tests/unit/test_no_role_name_literal.py", "tests/unit/test_no_tree_walk.py", "tests/unit/test_no_worker_name_leak.py", "tests/unit/test_worker_capabilities_match_behaviour.py", "tests/unit/test_write_scope.py"]
covered_digest: "v1:sha256:2271d1526f8e40dfefe27b2bc5af0e7fcb71037387cb461657da2a4a420e4d21"
behavior_unverified_items:
  - truth: "SC1 — `copilot`/`hermes` execute a role non-interactively and unattended in a clean container with no pre-existing CLI state, returning a normalized WorkerResult"
    test: "Install a real `copilot` and/or `hermes` binary with valid credentials and let `tests/integration/test_copilot_live.py` / `test_hermes_live.py` run past their skip guard against a genuinely clean container."
    expected: "The live suite's single test passes: a real `RoleContext` drives the real binary and returns a `WorkerResult` with a `WorkerResultStatus` member, with attempt logs under the resolved run root."
    why_human: "No `copilot` or `hermes` binary is installed in this sandbox (confirmed: `shutil.which` finds neither); the skip-guarded live suites correctly report SKIPPED with a named reason (verified directly) rather than running against a real CLI. The non-interactive/normalized-result claim is proven at the unit level against faked binaries (timeout, non-zero exit, missing binary, missing credential, NEEDS_INPUT variants, redaction — all passing), but the literal 'clean container, real binary' claim is unexercised here by design (D-02's deferred live spike)."
  - truth: "SC2 (WORK-09) — reassigning roles across three runtimes in configuration requires no workflow-code change and the run still completes"
    test: "Run `uv run pytest -m integration -q tests/integration/test_role_reassignment_sc2.py` and `tests/integration/test_real_pipeline_zero_config.py` against a reachable PostgreSQL 17."
    expected: "Both the three-runtime shipped-config run and the all-`fake` run reach `COMPLETED` with an identical role sequence and per-role artifact-type set, differing only in the persisted worker name; the negative case (no fake binaries on PATH) fails visibly rather than substituting a worker."
    why_human: "This sandbox has no reachable PostgreSQL 17 (no Docker, no local `initdb`/`pg_ctl`, `DARK_FACTORY_TEST_DATABASE_URL` unset — confirmed directly: running the test raises `pytest.UsageError: No PostgreSQL 17 is reachable`). The 'no workflow-code change' half of SC2 IS verified here (`test_no_worker_name_leak.py`, `test_no_role_name_literal.py` pass; the three role YAMLs are confirmed on disk to read `worker: copilot`/`claude-code`/`hermes`). The 'run still completes' half needs a live orchestrator run against Postgres, which this environment cannot provide. Both integration modules collect cleanly (0 collection errors) in this sandbox."
  - truth: "CR-01 closure (08-REVIEW.md BLOCKER) — a granted `artifacts.write` is confined to a role's own subtree on the real `HermesWorker` and `CopilotWorker`, end to end, with the tampered file's committed content restored"
    test: "Run `uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py` against a reachable PostgreSQL 17."
    expected: "The Hermes negative case (QA tampering with ARCHITECTURE's artifact) and the Copilot negative case (ARCHITECTURE tampering with BA's artifact) each fail the offending role, stop the pipeline, and restore the tampered file to its committed content; the positive control reaches COMPLETED with all four roles' artifacts collected."
    why_human: "Same missing-Postgres constraint as SC2. The underlying mechanism (`enforce_artifact_scope`, `attempt_changed_artifact_paths`, the `revert_paths(include_ignored=True)` extension) IS verified at the unit level — 17 cases in `tests/unit/test_artifact_scope.py`, all passing, covering in-scope, decoy-sibling, zero-tolerance, deleted-artifact-restore, and mixed in-scope/out-of-scope cases — and the wiring into `orchestrator/runner.py` ahead of `collect_role_artifacts`/`commit_run_artifacts`/`push_working_branch` was confirmed by direct code inspection. Only the real-subprocess-plus-real-database end-to-end proof is unexecuted here. The module collects cleanly (3 tests, 0 collection errors)."
coincidental_reliance_items: []
human_verification:
  - test: "Install a real `copilot` binary with a valid `COPILOT_GITHUB_TOKEN` and a real `hermes` binary with a valid `ANTHROPIC_API_KEY` in a clean container, then run `uv run pytest -q -rs tests/integration/test_copilot_live.py tests/integration/test_hermes_live.py tests/integration/test_claude_code_live.py`."
    expected: "All three suites transition from SKIPPED to PASSED with no code change, exercising `CopilotWorker`/`HermesWorker`/`ClaudeCodeWorker` against the genuine binaries (ROADMAP SC1's literal clean-container claim, D-02's deferred live spike)."
    why_human: "No live CLI binary exists in this development sandbox; this is the mechanism, not the proof, and by design (skip-guarded, verified to skip cleanly with a named reason) it cannot be exercised here."
  - test: "With a reachable PostgreSQL 17 (Docker, local `initdb`, or `DARK_FACTORY_TEST_DATABASE_URL`), run `uv run pytest -m integration -q tests/integration/test_role_reassignment_sc2.py tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py`."
    expected: "All 8 tests across the three modules pass: the SC2 paired-run equality proof and its negative case, the shipped-config zero-config pipeline reaching COMPLETED across three real runtimes, and the three artifact-scope-enforcement end-to-end scenarios (Hermes negative, Copilot negative, positive control)."
    why_human: "This sandbox has no reachable PostgreSQL 17 — confirmed directly (`pytest.UsageError: No PostgreSQL 17 is reachable...`), a documented pre-existing environment constraint affecting every 08-* plan, not something introduced by this phase. All modules collect with zero import/collection errors."
---

# Phase 8: Copilot & Hermes — Worker Independence Proven Verification Report

**Phase Goal:** The same role runs unchanged on three genuinely different agent runtimes, selected purely in configuration.
**Verified:** 2026-09-22T05:01:45Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Note on MVP mode

ROADMAP.md marks this phase `mode: mvp`, but 08-01-PLAN.md's own frontmatter note records that the ROADMAP `**Goal:**` line is deliberately **not** in `As a / I want to / so that` user-story form — the planner explicitly declined to invent one. Running the MVP-mode User Flow Coverage procedure against this goal text would fail `user-story.validate` by construction. Standard goal-backward verification is applied instead, which is what all five plans in this phase were themselves verified against.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 — `copilot`/`hermes` execute a role non-interactively/unattended in a clean container, returning a normalized `WorkerResult` | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Mechanism fully proven at unit level (93+35+30 tests across `test_copilot_worker.py`/`test_hermes_worker.py`/contract suite, all passing: COMPLETED/empty-output, timeout+process-group-kill, non-zero exit, missing binary, missing credential, NEEDS_INPUT variants, redaction). Live-binary clean-container variant deferred by design (D-02); `test_copilot_live.py`/`test_hermes_live.py`/`test_claude_code_live.py` correctly SKIP with a named reason (`'copilot' not found on PATH`, etc.) — confirmed directly. |
| 2 | SC2 (WORK-09) — role reassignment via configuration alone, no workflow-code change, run still completes | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Configuration edit confirmed on disk: `ARCHITECTURE.yaml`→`worker: copilot`, `DEVELOPMENT.yaml`→`worker: claude-code`, `QA.yaml`→`worker: hermes`, `BA.yaml` unchanged on `fake`. No-workflow-code-change half VERIFIED: `test_no_worker_name_leak.py`, `test_no_role_name_literal.py` pass. "Run still completes" half (`test_role_reassignment_sc2.py`, DB-gated) not executable in this sandbox — confirmed genuine Postgres-unavailability, not a code defect. |
| 3 | SC3 — each adapter has its own skip-guarded live suite; the shared `CodingWorker` contract suite passes over all four workers with no live binary/credential | ✓ VERIFIED | `pytest -q -rs` on the three live modules: 3 skipped, 0 failed, 0 errored, each with a named reason. `pytest -m contract` with `COPILOT_GITHUB_TOKEN`/`ANTHROPIC_API_KEY` unset: 26 passed. `WORKER_FACTORIES` has length 4. `test_every_real_adapter_has_a_live_suite.py` passes (enumerated from `default_registry`, self-detection case included). |
| 4 | SC4 — each adapter's declared `WorkerCapabilities` matches its own observed behaviour | ✓ VERIFIED | `tests/unit/test_worker_capabilities_match_behaviour.py` passes (parametrized over all four workers; resume-flag-versus-argv, structured-output-versus-argv, non-interactive-stdin, emits_changed_files axes each checked against observed behaviour, not a restated literal). |
| 5 | CR-01 closure (08-REVIEW.md BLOCKER) — a granted `artifacts.write` is confined to a role's own `artifacts/<role>/` subtree on every worker | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `enforce_artifact_scope`/`attempt_changed_artifact_paths` unit-verified (17 cases, `tests/unit/test_artifact_scope.py`, all pass — in-scope, decoy-sibling, zero-tolerance-when-ungranted, deleted-artifact-restore, mixed in-scope/out-of-scope). Wiring confirmed by direct code read: `runner.py`'s new `if signal is Signal.ROLE_COMPLETED:` block calls `enforce_artifact_scope` before `collect_role_artifacts`/`commit_run_artifacts`/`push_working_branch`. Real-subprocess-plus-Postgres end-to-end negative proof on Hermes and Copilot (`test_artifact_scope_enforcement.py`) not executable in this sandbox. `08-REVIEW.md`'s incremental re-review independently confirms CR-01 CLOSED by direct code inspection. |
| 6 | WR-02/WR-03 closure — `NATIVE_TOOL_CONTRACT`'s Copilot `artifacts.*` prose and both adapters' granted-case documentation state the real enforcement posture | ✓ VERIFIED | Read directly from `src/dark_factory/tools/native.py`: no `copilot=` field states parity with Claude Code; `artifacts.write`'s prose names `enforce_artifact_scope`. `spawn_is_permitted.__doc__` contains both `artifacts.write` and `artifacts.read` granted-case statements (confirmed by direct import and inspection). `tests/unit/test_native_tool_contract.py` passes with the two new pinning assertions. |
| 7 | Requirements traceability — WORK-05, WORK-06, WORK-09, QUAL-03 are each backed by real, passing code/tests; no Phase-8-mapped requirement is orphaned | ✓ VERIFIED | `.planning/REQUIREMENTS.md` maps exactly WORK-05, WORK-06, WORK-09, QUAL-03 to Phase 8, all marked `Complete`; every plan's `requirements:` frontmatter is accounted for (08-05's additional ROLE-05/TOOL-03 are Phase-5/Phase-6 requirements being extended, not new Phase-8 obligations, and are correctly still marked complete against their original phases). `grep -n "Phase 8"` finds no additional mapped ID outside these four. |

**Score:** 4/7 truths verified (3 present, behaviour deferred to human verification — all three are DB-gated or live-binary-gated, a pre-existing, documented environment constraint of this sandbox, not a phase defect)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dark_factory/workers/copilot.py` | Real `CopilotWorker` adapter | ✓ VERIFIED | Exists, substantive, wired (`default_registry.get("copilot")` returns `CopilotWorker` instance — confirmed by direct import/instantiation). |
| `src/dark_factory/workers/hermes.py` | Real `HermesWorker` adapter with `spawn_is_permitted` | ✓ VERIFIED | Exists, substantive, wired (`default_registry.get("hermes")` returns `HermesWorker` instance — confirmed). |
| `src/dark_factory/workers/cli_runtime.py` | Shared CLI-adapter runtime | ✓ VERIFIED | Imported by `claude_code.py`, `copilot.py`, `hermes.py` (confirmed via grep and passing test suite). |
| `src/dark_factory/git/scope.py` — `enforce_artifact_scope` | Sibling post-hoc artifact-scope control | ✓ VERIFIED | Present, unit-tested (17 cases), wired into `orchestrator/runner.py` (confirmed by direct code read of lines 894-919). |
| `.dark-factory/roles/{ARCHITECTURE,DEVELOPMENT,QA}.yaml` | Reassigned `worker:` lines | ✓ VERIFIED | Confirmed on disk: `copilot`/`claude-code`/`hermes` respectively; `BA.yaml` unchanged on `fake`. |
| `tests/support/live_runtime.py`, `tests/integration/test_*_live.py` | Skip-guarded live suites | ✓ VERIFIED | All three collect and SKIP with named reasons in this environment; confirmed directly. |
| `tests/integration/test_role_reassignment_sc2.py`, `test_artifact_scope_enforcement.py` | DB-gated integration proofs | ✓ VERIFIED (present, unexecuted) | Both modules exist, are substantive (multi-hundred-line real proofs, not stubs), collect cleanly with 0 errors; cannot execute without Postgres in this sandbox. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `workers/registry.py` | `CopilotWorker`/`HermesWorker` | `default_registry.register(...)` | WIRED | Confirmed: no placeholder remains; `default_registry.names() == {"hermes","copilot","fake","claude-code"}`. |
| `orchestrator/runner.py` | `git.scope.enforce_artifact_scope` | direct call, before artifact collect/commit/push | WIRED | Confirmed by direct code read: called inside its own `if signal is Signal.ROLE_COMPLETED:` block at lines 908-919, strictly before the `collect_role_artifacts` block at line 921. |
| `.dark-factory/roles/*.yaml` `worker:` | `config/loader.py` → persisted snapshot → `registry.get(node.worker)` | configuration-only reassignment | WIRED | `test_no_worker_name_leak.py`/`test_no_role_name_literal.py` pass — no runtime name appears outside `workers/`/`config/`. |
| `cli_runtime.collect_declared_artifacts` | `artifacts/validation.py::collect_role_artifacts` | shared artifact-reporting helper | WIRED | Used by both `CopilotWorker` and `ClaudeCodeWorker`'s COMPLETED branch — confirmed via passing end-to-end unit tests in `test_copilot_worker.py`/`test_claude_code_worker.py`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit+contract suite | `uv run pytest -m "unit or contract" -q` | 640 passed, 0 failed | ✓ PASS |
| mypy strict | `uv run mypy src/dark_factory` | Success: no issues found in 67 source files | ✓ PASS |
| ruff | `uv run ruff check .` | All checks passed | ✓ PASS |
| Registry has no placeholders | direct Python import/instantiation | `copilot`→`CopilotWorker`, `hermes`→`HermesWorker`, `claude-code`→`ClaudeCodeWorker` | ✓ PASS |
| Live suites skip cleanly | `pytest -q -rs` on the 3 live modules | 3 skipped, 0 failed, 0 errored, named reasons | ✓ PASS |
| Contract suite with no ambient credentials | `env -u COPILOT_GITHUB_TOKEN -u ANTHROPIC_API_KEY pytest -m contract -q` | 26 passed | ✓ PASS |
| DB-gated integration tests collect | `pytest -q --collect-only` on 3 integration modules | 8 tests collected, 0 collection errors | ✓ PASS |
| DB-gated integration tests execute | `pytest -q tests/integration/test_artifact_scope_enforcement.py` | `pytest.UsageError: No PostgreSQL 17 is reachable...` | ? SKIP (environment constraint, confirmed genuine — no Docker/initdb/DARK_FACTORY_TEST_DATABASE_URL) |
| Full test collection (no marker/collection errors) | `pytest -q --collect-only` (whole suite) | 962 tests collected | ✓ PASS |

### Anti-Patterns Found

None blocking. Two non-blocking findings carried from `08-REVIEW.md`'s incremental re-review (2026-09-22), both explicitly out of this phase's declared must-haves and correctly rated below BLOCKER:

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/dark_factory/git/scope.py` / `git/diff.py` | WR-04 — `enforce_artifact_scope` (and `enforce_write_scope`) deliberately do not cover the same run tree's `verification/`, `logs/`, `input/` directories; a worker with native filesystem/shell access could tamper with `verification/diff.patch` or another role's log file undetected. | Warning | Not a regression, not part of what CR-01 promised to fix (08-REVIEW.md's own words), and not named in any of this phase's roadmap Success Criteria or plan must-haves — genuinely out of this phase's scope, flagged by the reviewer as a residual risk for a future phase to pick up (candidate: Phase 9's quality-gate work, which reads `verification/diff.patch`). |
| `tests/unit/test_artifact_scope.py:243-274` | IN-02 — one multi-violation assertion checks `"3" in message`, which a random UUID substring could satisfy coincidentally even if the attempt number were rendered wrong. | Info | Test-quality nit only; the code under test renders the attempt number correctly (confirmed by direct reading of `enforce_artifact_scope`'s f-string); does not affect correctness of the shipped behaviour. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|-------------|--------|----------|
| WORK-05 | 08-01, 08-05 | `CopilotWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | ✓ SATISFIED | Real adapter, registered, 35-test unit suite passing, contract-suite-pinned; CR-01/WR-02 closure (08-05) additionally hardens its `artifacts.*` posture. |
| WORK-06 | 08-02, 08-05 | `HermesWorker` is a functional adapter that runs a role non-interactively and returns a normalized result | ✓ SATISFIED | Real adapter, registered, 30-test unit suite passing, `spawn_is_permitted` admission rule implemented per checkpoint Option A, contract-suite-pinned. |
| WORK-09 | 08-04 | Any role can be assigned to any supported worker via configuration with no change to workflow code | ✓ SATISFIED (config half); ? NEEDS HUMAN (completion half) | Role YAMLs confirmed reassigned; `test_no_worker_name_leak.py` passes. The "run still completes" proof is DB-gated and unexecuted in this sandbox. |
| QUAL-03 | 08-03 | Each real worker adapter has its own integration test suite, skipped when credentials are absent | ✓ SATISFIED | Three skip-guarded live suites confirmed collecting and skipping with named reasons; completeness guard enumerated from the registry. |

No orphaned requirements: `.planning/REQUIREMENTS.md` maps exactly WORK-05, WORK-06, WORK-09, QUAL-03 to Phase 8, matching this verification's scope precisely.

### Gaps Summary

No BLOCKER-level gaps found. The phase's own code review (`08-REVIEW.md`) identified one BLOCKER (CR-01) and two Warnings (WR-02, WR-03) against the wave-1/2/3 work; plan 08-05 was executed specifically to close all three, and this verification independently confirmed the closure by direct code inspection (not by trusting the SUMMARY or the review's own re-review verdict alone): `enforce_artifact_scope` exists, is unit-tested (17 passing cases), and is wired into `orchestrator/runner.py` ahead of the artifact commit/push sequence; the contract prose and both adapters' docstrings state the real granted-capability enforcement boundary; `spawn_is_permitted.__doc__` was read directly and confirmed to contain the granted-case statements.

The reason this verification is `human_needed` rather than `passed` is exclusively the DB-gated and live-binary-gated proof surface — the same, single, pre-existing environment constraint (no Docker, no local PostgreSQL 17, no live `copilot`/`hermes` binary) that every one of this phase's five plans independently hit and honestly documented. This was independently re-confirmed in this verification session, not merely copied from the SUMMARYs: `which docker pg_ctl initdb` all report not-found, `DARK_FACTORY_TEST_DATABASE_URL` is unset, and running the gated integration tests directly produces the identical `pytest.UsageError` every prior plan's SUMMARY quoted. All affected modules collect cleanly with zero import/collection errors, and their non-DB-gated logic (the actual enforcement mechanisms, the configuration edits, the no-leak guards) is proven and passing. This matches the explicit task instruction to treat these as legitimate human-verification items, not gaps.

---

_Verified: 2026-09-22T05:01:45Z_
_Verifier: Claude (gsd-verifier)_
