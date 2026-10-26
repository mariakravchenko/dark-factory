---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 07
subsystem: testing
tags: [test-harness, quality-gate, config, gap-closure, G-10-1]

requires:
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "10-06's publish step and its `publishing.create_pr` gating (the field this harness now neutralizes for a throwaway repo)"
provides:
  - "tests/support/shipped_config.py -- the single shipped-config copy-and-neutralize harness for the whole test tree"
  - "A DB-free proof (tests/unit/test_shipped_config_harness.py) that the harness rewrites exactly quality_gate + publishing and folds the real quality gate to PASS"
  - "Four real-CLI-subprocess integration modules restored to reflect the SHIPPED pipeline reaching COMPLETED (pending DB-tier execution -- see Known Gaps below)"
  - "Three negative-control tests strengthened to assert on the persisted role-execution error naming their own condition, not merely on exit code 1"
affects: [10-08-gap-closure, gsd-verify-work, future-integration-tests-that-copy-shipped-config]

actuals:
  tokens: 6146
  tasks: 3
  commits: 8
  plan_head_before: 589d57ce23bf988ca75c4f0c095512bf351f64e0

tech-stack:
  added: []
  patterns:
    - "Single shared test-support harness (tests/support/shipped_config.py) replacing four duplicated per-module copy helpers -- the same tests/support/git_repo.py convention"
    - "Neutralize-on-parsed-document, never duplicate-key-append, when rewriting a copied YAML config for a test fixture"
    - "A DB-free unit test that proves a test fixture's honesty (same top-level key set, only the intentionally-neutralized keys differ) as a structural guard against future fixture drift"

key-files:
  created:
    - tests/support/shipped_config.py
    - tests/unit/test_shipped_config_harness.py
  modified:
    - tests/integration/test_artifact_cross_clone.py
    - tests/integration/test_real_pipeline_zero_config.py
    - tests/integration/test_artifact_scope_enforcement.py
    - tests/integration/test_role_reassignment_sc2.py

key-decisions:
  - "HARNESS_GATE_COMMANDS = (\"git --version\",) as the harness's quality-gate placeholder: always exits 0, writes nothing to the worktree, and PATH is in WORKER_ENV_ALLOWLIST -- exercises the real gate-execution path instead of a zero-length command list folding to PASS vacuously."
  - "neutralize_repo_local_config operates on the yaml.safe_load-parsed document and yaml.safe_dump(sort_keys=False)'s it back, never appends a second quality_gate: block -- a duplicate YAML key resolves by last-wins silently, which is exactly the class of implicit behaviour that let G-10-1 live undetected for two phases."
  - "test_role_reassignment_sc2.py's no-fake-binaries negative control asserts on the real persisted-error substring (\"COPILOT_GITHUB_TOKEN ... not configured\"), not the plan prose's \"missing copilot executable\" framing -- read from src/dark_factory/workers/copilot.py: CopilotWorker's credential check runs before any subprocess spawn is attempted, so with COPILOT_GITHUB_TOKEN deleted the run never reaches a spawn-not-found failure at all."

requirements-completed: [GIT-03]

coverage:
  - id: D1
    description: "tests/support/shipped_config.py is the single shipped-config copy-and-neutralize harness; a DB-free unit suite proves the copied snapshot differs from the shipped snapshot in exactly quality_gate + publishing, the harness gate command list is non-empty and folds to VerdictStatus.PASS through the real run_quality_gate, and create_pr is False in the copy while still True in the shipped file."
    requirement: GIT-03
    verification:
      - kind: unit
        ref: "uv run pytest -m unit -q tests/unit/test_shipped_config_harness.py (3 passed)"
        status: pass
      - kind: other
        ref: "uv run ruff check . && uv run mypy src/dark_factory"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exactly one shipped-config copy helper exists under tests/, and all four real-CLI-subprocess integration modules (test_artifact_cross_clone, test_real_pipeline_zero_config, test_artifact_scope_enforcement, test_role_reassignment_sc2) import it and collect cleanly."
    requirement: GIT-03
    verification:
      - kind: other
        ref: "grep -rEl 'def _?copy_shipped_config_into' tests --include='*.py' | wc -l == 1"
        status: pass
      - kind: other
        ref: "uv run pytest -q --collect-only <the four modules> (7 tests collected, 0 errors)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The two artifact-scope tamper cases and the no-fake-binaries case assert on the persisted role-execution error naming their own condition (the tampered artifact path / the missing-credential message), in addition to the exit-code and role-status assertions they already had -- closing the G-10-1 masked-assertion risk."
    requirement: GIT-03
    verification:
      - kind: other
        ref: "grep -c 'error_by_role\\[' tests/integration/test_artifact_scope_enforcement.py -ge 2; grep -c 'architecture_error' tests/integration/test_role_reassignment_sc2.py -ge 2"
        status: pass
    human_judgment: false
  - id: D4
    description: "Against a reachable PostgreSQL, the four real-CLI-subprocess tests (test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script, test_fresh_clone_of_the_working_branch_carries_every_artifact_byte, test_the_identical_shipped_config_with_no_tampering_completes_with_all_artifacts, test_reassigned_roles_reach_completed_identically_to_all_fake) reach terminal COMPLETED, and the three negative controls (two artifact-scope tampers, no-fake-binaries) still FAIL their run for their own stated reason."
    requirement: GIT-03
    verification: []
    human_judgment: true
    rationale: "No PostgreSQL was reachable in this execution sandbox (no Docker, no local initdb/pg_ctl, no DARK_FACTORY_TEST_DATABASE_URL) -- the exact precondition .planning/debug/qa-gate-exhausts-bounces-terminates-failed.md's own diagnosis session hit. Steps 1-4 of the plan's <verification> (DB-free harness proof, single-sweep-point grep, unit+contract tier, lint/types) all pass; step 5 (the real gate against a reachable PostgreSQL) and Task 3's <human-check> are UNMET PRECONDITIONS per the plan's own instruction not to report the plan verified on steps 1-4 alone. A human with a reachable PostgreSQL must run: `uv run pytest -m integration -q tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py tests/integration/test_artifact_cross_clone.py tests/integration/test_role_reassignment_sc2.py`."

duration: 55min
completed: 2026-09-28
status: complete
---

# Phase 10 Plan 07: Shipped-Config Test Harness (G-10-1 Gap Closure) Summary

**Collapsed four duplicated, non-neutralizing shipped-config copy helpers into one shared harness that rewrites the two repo-local `.dark-factory.yaml` declarations (`quality_gate.commands`, `publishing.create_pr`) a throwaway repo cannot satisfy, closing G-10-1's two serial root causes and its masked-assertion risk -- with the real-PostgreSQL end-to-end proof deferred as an unmet precondition (no database reachable in this sandbox).**

## Performance
- **Duration:** 55min
- **Started:** 2026-09-28T07:10:00Z (approx, first Read of the plan)
- **Completed:** 2026-09-28T08:05:48Z
- **Tasks:** 3 completed
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- Built `tests/support/shipped_config.py`, the single shipped-config copy-and-neutralize harness (`SHIPPED_CONFIG_PATHS`, `HARNESS_GATE_COMMANDS`, `neutralize_repo_local_config`, `copy_shipped_config_into`), proven by a 3-test DB-free unit suite that reproduces the exact G-10-1 defect on a naive (non-neutralizing) RED-phase stub, then passes once the real neutralization lands
- Rewired all four real-CLI-subprocess integration modules (`test_artifact_cross_clone.py`, `test_real_pipeline_zero_config.py`, `test_artifact_scope_enforcement.py`, `test_role_reassignment_sc2.py`) onto the one harness, removing three duplicated per-module copy helpers and their supporting constants
- Strengthened the three negative-control tests (two artifact-scope tamper cases, the no-fake-binaries case) to assert on the persisted `role_executions.error` content naming their own condition, closing the masked-assertion risk the G-10-1 diagnosis flagged: before this plan all three exited 1 from gate exhaustion, not from the condition each claims to prove
- `src/dark_factory/orchestrator/runner.py` untouched (confirmed via `git diff --stat` against the plan's base commit) -- this was entirely a test-harness defect, exactly as diagnosed

## Task Commits
1. **Task 1: End-to-end "the shipped config, neutralized for a throwaway repo" -- one consumer only** (TDD: RED -> GREEN)
   - `ec8d606` test(10-07): add failing test for shipped-config harness (RED)
   - `58fba52` feat(10-07): implement shipped-config neutralization harness (G-10-1) (GREEN; also rewires `test_artifact_cross_clone.py`)
2. **Task 2: Move the remaining three integration modules onto the one harness** - `cfc4cc0` refactor(10-07)
3. **Task 3: Make the three negative controls fail for their own stated reason** - `5d8057c` test(10-07)

**Plan metadata:** (this commit, following this SUMMARY)

## Files Created/Modified
- `tests/support/shipped_config.py` - The shared harness: `SHIPPED_CONFIG_PATHS`, `HARNESS_GATE_COMMANDS = ("git --version",)`, `neutralize_repo_local_config`, `copy_shipped_config_into`
- `tests/unit/test_shipped_config_harness.py` - Three DB-free tests: honesty guard (exactly `quality_gate`/`publishing` differ), real-gate-PASS proof, `create_pr` flip proof
- `tests/integration/test_artifact_cross_clone.py` - Own copy helper + constants removed; imports the shared harness
- `tests/integration/test_real_pipeline_zero_config.py` - Own copy helper + constants removed; imports the shared harness; docstring paragraph explains what changed and why
- `tests/integration/test_artifact_scope_enforcement.py` - Cross-module import switched to the shared harness; Copilot tamper case gains a persisted-error assertion mirroring the Hermes case's existing one; comments on both negative cases explain why exit code alone is not proof
- `tests/integration/test_role_reassignment_sc2.py` - Cross-module import switched to the shared harness; SC2 role-yaml-diff call site gains a one-line precondition comment; no-fake-binaries case binds `architecture_error` and asserts on the real `MissingWorkerCredentialError` substring

## Decisions Made
- **HARNESS_GATE_COMMANDS is `git --version`, not an empty list**: an empty `quality_gate.commands` list folds to PASS vacuously (as `tests/conftest.py`'s `_write_config_tree` already does for ~24 other db-tier tests) and would leave the gate-execution path -- the exact path silently broken since Phase 9 -- unexercised by these four tests. `git --version` is a hard dependency every one of these tests already shells out to, always exits 0, and writes nothing.
- **Neutralize the parsed document, not append a duplicate key**: `neutralize_repo_local_config` does `yaml.safe_load` -> mutate the two keys -> `yaml.safe_dump(sort_keys=False)`, deliberately not a second `quality_gate:\n  commands: []\n` block appended to the copied file. A duplicate YAML key resolves last-wins silently, the exact category of implicit behavior that let the original defect (repo-specific declarations copied verbatim) go undetected for two phases.
- **The no-fake-binaries negative control asserts the real message, not the plan's stated framing**: the plan's task prose describes the expected failure as "the spawn failure for the missing `copilot` executable." Reading `src/dark_factory/workers/copilot.py`'s `_spawn_and_parse` shows the credential check (`settings.copilot_github_token is None`) runs and raises `MissingWorkerCredentialError` *before* `run_streamed` (the actual spawn) is ever called. With `COPILOT_GITHUB_TOKEN` deleted and no `.env` reachable from the throwaway repo's cwd, the persisted error genuinely names the missing credential, not a process-not-found failure. Per the plan's own instruction ("read the actual persisted value first ... assert on the real substring it contains -- do not guess a message"), the assertion targets `"COPILOT_GITHUB_TOKEN"` / `"not configured"`, the true production behavior.

## Deviations from Plan
None - plan executed exactly as written. The no-fake-binaries assertion substring (above) is not a deviation: the plan explicitly instructed reading the adapter's own code to determine the real message rather than guessing, and that is what was done.

## Issues Encountered
- **No PostgreSQL reachable in this execution sandbox** (no Docker, no local `initdb`/`pg_ctl`, no `DARK_FACTORY_TEST_DATABASE_URL`) -- the same precondition the G-10-1 diagnosis session itself hit. This blocks: (a) the plan's `<verification>` step 5 (the real gate against a reachable PostgreSQL, driving all four real-CLI-subprocess tests), and (b) Task 3's `<human-check>` (confirming the strengthened negative-control assertions against a real run). Steps 1-4 of `<verification>` all pass (DB-free harness proof, single-sweep-point grep, whole unit+contract tier -- 808 passed, lint/types clean). Per the plan's own instruction, this is recorded as an **unmet precondition**, not reported as full verification. See coverage item D4.

## User Setup Required
A reachable PostgreSQL is needed to complete verification: either a local Docker Postgres, a local `initdb`-provisioned instance, or `DARK_FACTORY_TEST_DATABASE_URL` pointing at a throwaway database (a Neon branch works, as prior phases used). Once reachable, run:

```
uv run pytest -m integration -q tests/integration/test_real_pipeline_zero_config.py tests/integration/test_artifact_scope_enforcement.py tests/integration/test_artifact_cross_clone.py tests/integration/test_role_reassignment_sc2.py
```

Expected: all seven tests pass -- the four positive/reassignment cases reach `COMPLETED`, and the three negative controls (two artifact-scope tampers, no-fake-binaries) fail their run with the persisted error naming their own condition (not gate exhaustion).

## Next Phase Readiness
- The test-harness defect behind G-10-1 is closed at the code level; the remaining work is purely running the already-strengthened suite against a reachable database (see User Setup Required above).
- `.planning/phases/10-github-issue-intake-idempotent-publishing-comment-resume/10-08-PLAN.md` (already authored) closes the two unrelated test-only defects the same diagnosis surfaced (the adjacency-reason test and the over-broad redaction guard) -- independent of this plan's changes, no blocking dependency either direction.
- 10-UAT.md Test 2 (live GitHub API end-to-end smoke) remains blocked pending both this plan's DB-tier confirmation and real GitHub credentials -- unchanged by this plan, still deferred.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-28*

## Self-Check: PASSED

All created files verified present on disk (`tests/support/shipped_config.py`, `tests/unit/test_shipped_config_harness.py`, this SUMMARY.md). All six commit hashes (`ec8d606`, `58fba52`, `cfc4cc0`, `5d8057c`, `f152345`, `e63b6c7`) verified present in `git log --oneline --all`.
