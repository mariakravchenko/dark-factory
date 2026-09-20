---
status: resolved
trigger: "3 pre-existing db/integration test failures, documented since 06-01-SUMMARY.md, confirmed unchanged before/after phase 6's own work (baseline 662 passed/3 failed -> 694 passed/3 failed): (1) tests/db/test_artifact_commit_per_role.py::test_one_artifact_commit_per_role_force_added_and_source_edits_survive -- AssertionError: assert 'source_edit.txt' in []; (2) tests/db/test_artifact_commit_per_role.py::test_completed_run_with_a_trailing_edit_gets_a_recovery_commit_then_loses_its_worktree -- AssertionError: assert <RunStatus.FAILED> is <RunStatus.COMPLETED>; (3) tests/integration/test_pr_diff_excludes_artifacts.py::test_pr_diff_excludes_dark_factory_and_ignores_the_base_branchs_own_post_cut_commit -- AssertionError: assert <RunStatus.FAILED> is <RunStatus.DEVELOPMENT>. All three are phase-4/phase-5 git-worktree/artifact-commit mechanics, unrelated to phase 6's tool-registry/capability-enforcement work per 06-01-SUMMARY.md and 06-04-SUMMARY.md."
created: 2026-09-20T00:00:00Z
updated: 2026-09-20T08:25:58Z
symptoms_prefilled: true
goal: find_and_fix
---

## Current Focus

status: RESOLVED -- single root cause, test-defect class (no production change).
        Fix applied in-session (derived statically); acceptance CONFIRMED by a
        user-run pytest execution against real PostgreSQL 17 on 2026-09-20:
        5 passed, up from the long-standing 3-failed baseline.

hypothesis: |
  All three failures share one cause: each test's role fixture declares
  `permissions: write_scope: []` (D-14 ZERO TOLERANCE -- every path is a
  violation) while that same test's own worker/fixture plants a NON-artifact
  file in the worktree. At `Signal.ROLE_COMPLETED`, runner.py:944-958 calls
  `enforce_write_scope`, which reverts the planted file and raises
  `WriteScopeViolation` -> `ROLE_FAILED` -> `RUN_FAILED`. The fixtures are
  stale: they predate phase 5's D-14 enforcement and were never updated to
  authorize what their own workers write.

test: |
  Static cross-reference of the live production polarity + enforcement call
  site against each failing test's fixture, plus a git probe confirming a
  staged-new file is visible to `git diff --name-only HEAD` and survives a
  pathspec-limited artifact commit.

expecting: |
  Widening ONLY the specific roles' write_scope to the specific file each
  test's own worker writes converts all three AssertionErrors without
  touching src/.

bug_class: Bohrbug (fully deterministic -- fixture-driven, no timing/concurrency component)

reasoning_checkpoint:
  hypothesis: "An empty `write_scope` fixture (D-14 zero tolerance) + a test-planted non-artifact file = WriteScopeViolation at ROLE_COMPLETED, reverting the file and failing the run."
  confirming_evidence:
    - "scope.py:92 `is_out_of_scope` -- `not any(... for p in write_scope)` over `()` is True for EVERY path; docstring:84-90 explicitly forbids an empty-list early return. Read live, holds."
    - "runner.py:944-958 -- `enforce_write_scope` runs on ROLE_COMPLETED AFTER collect/commit/push; `WriteScopeViolation` flips signal to ROLE_FAILED and clears artifact_writes. Read live, holds."
    - "scope.py:221-243 `revert_paths` -- path absent from HEAD gets `git rm --cached` + `git clean`, so `git diff --cached --name-only` afterwards is exactly []. Matches symptom 1 verbatim."
    - "Fixtures read live: test_artifact_commit_per_role.py:208 writes `write_scope: []` for all four roles and the test plants+stages `source_edit.txt` at :290-294; `_TrailingEditWorker.execute`:386 writes `trailing_edit.txt` under conftest.py:386 BA `write_scope: \"[]\"`; test_pr_diff_excludes_artifacts.py:82 gives BA `write_scope: []` and `_RoleAwareDiffProofWorker.execute`:172 writes `feature.py`."
    - "Sibling control holds: test_failed_run_keeps_its_worktree (:429) and test_waiting_human_run_keeps_its_worktree (:469) use the SAME `write_scope: []` default but plain FakeWorker writes nothing and neither reaches ROLE_COMPLETED, so runner.py:944 never fires. Pass/fail split is fully explained."
    - "Empirical git probe: a staged-new file IS reported by `git diff --name-only HEAD`; and diff.py:143-152 `commit_run_artifacts` commits with a trailing pathspec (`-- .dark-factory/runs/<id>`), so the staged source file is NOT swept up and stays visible to every LATER role's enforcement too."
    - "make_git_repo's .gitignore is only `.dark-factory/runs/`, so all three planted files are genuinely visible to `git ls-files --others --exclude-standard`."
  falsification_test: "If any of the three roles' fixtures did NOT declare an empty write_scope, or the planted file were gitignored / inside `.dark-factory/runs`, the hypothesis would be refuted. Checked all three: none refute."
  fix_rationale: "The D-14 zero-tolerance polarity is the deliberate, load-bearing production contract (scope.py docstring forbids inverting it, and tests/integration/test_write_scope_enforcement.py proves it -- 6/6 per 05-VERIFICATION.md). The defect is that these fixtures never authorized their own workers' writes. Widening each failing test's role write_scope to exactly the file that test plants addresses the actual cause."
  blind_spots:
    - status: RESOLVED (2026-09-20, by user-run execution)
      blind_spot: "No PostgreSQL 17 reachable in this session -- the db/ and integration/ tiers CANNOT be executed here. The 3-tests-green acceptance signal is UNVERIFIED and requires a user-run execution."
      closure: "Closed by evidence, not by assumption. The user ran the db/integration tier in their own terminal against a real PostgreSQL 17 (`set -a; . ./.env; set +a` then `uv run pytest -q tests/db/test_artifact_commit_per_role.py tests/integration/test_pr_diff_excludes_artifacts.py`) and reported `5 passed in 197.62s (0:03:17)`. This session still has NO database -- the PASS evidence is the user's, not this session's."
    - status: RESOLVED (2026-09-20, by the later assertions executing)
      blind_spot: "Downstream-of-the-failure behavior is unobserved: the trailing-edit test's WIP-commit assertion (:426) and the integration test's three-dot/two-dot diff assertions have never actually run to completion, so a second, later defect could be hiding behind this first one."
      closure: "Closed affirmatively. All 5 tests passed with no later assertion failing, which means the previously-unreachable code paths did run to completion this time: the trailing-edit test's WIP-commit assertion and the integration test's three-dot/two-dot diff assertions both executed and both passed. The suspected second defect is therefore demonstrated absent, not merely unobserved."
  candidate_causes:
    - "code (production): D-14 polarity is inverted/wrong -- ELIMINATED, polarity is deliberate and doc-locked"
    - "config (test fixture): role YAML declares write_scope: [] while the test writes a non-artifact file -- CONFIRMED"
    - "environment: missing PostgreSQL 17 -- ELIMINATED, that blocks execution but the AssertionErrors came from a real user run"
    - "data: planted file path gitignored or inside the excluded run tree -- ELIMINATED, .gitignore is only `.dark-factory/runs/`"
  and_gate: "no -- a single condition per test suffices. Proven by the sibling control: same `write_scope: []`, no planted file, test passes. One condition flips the outcome, so no second contributing cause is required."

next_action: |
  NONE -- session closed. The human-verify checkpoint was answered "confirmed
  fixed": the user ran the db/integration tier against a real PostgreSQL 17 and
  got `5 passed in 197.62s (0:03:17)`, closing both recorded blind spots. The
  acceptance signal is VERIFIED, the guardrail verdict is `accepted` (a clean
  pass, not accepted-as-debt), and this file is archived to
  .planning/debug/resolved/phase4-artifact-commit-bugs.md.

  Residual, NOT blocking and NOT part of this bug: the user's run covered only
  the two target files (5 tests). A full-suite run is still worth doing once to
  confirm the long-standing "3 failed" baseline is now 0 failed and that no
  other suite depended on the old fixture values -- though the untouched
  tests/conftest.py and the passing 442-test unit tier make a regression
  elsewhere unlikely.

knowledge_base: no .planning/debug/knowledge-base.md exists yet (checked 2026-09-20) -- no prior-pattern hypothesis available. Adjacent session in-scope-edit-missing-after-completed.md is a candidate pattern: "test asserts on worktree filesystem after COMPLETED, which D-04 destroys". Precedent for THIS fix's class: 05-05 G-05-1 closure, recorded in 05-05-SUMMARY.md:33 and 05-VERIFICATION.md:113 as "a test-defect fix, not a production fix ... zero production changes".

## Symptoms

- **Expected behavior:** All three tests pass when run against a real PostgreSQL 17 (the project's db/integration tiers require a real database — no SQLite/mock substitutes, per 01-RESEARCH.md).
- **Actual behavior:**
  1. `test_one_artifact_commit_per_role_force_added_and_source_edits_survive` fails with `AssertionError: assert 'source_edit.txt' in []` — a force-added source edit does not appear where the test expects it (an empty list where a file path was expected).
  2. `test_completed_run_with_a_trailing_edit_gets_a_recovery_commit_then_loses_its_worktree` fails with `AssertionError: assert <RunStatus.FAILED> is <RunStatus.COMPLETED>` — the run reaches `FAILED` instead of `COMPLETED`.
  3. `test_pr_diff_excludes_dark_factory_and_ignores_the_base_branchs_own_post_cut_commit` fails with `AssertionError: assert <RunStatus.FAILED> is <RunStatus.DEVELOPMENT>` — the run reaches `FAILED` instead of reaching (at least) `DEVELOPMENT`.
- **Error messages:** See the three AssertionErrors above (verbatim from 06-01-SUMMARY.md, which recorded them from a real pytest run against real PostgreSQL 17 performed by the user in their own terminal — this session cannot reproduce directly, no Docker/local initdb/DATABASE_URL available).
- **Timeline:** First documented in 06-01-SUMMARY.md (2026-09-19) as a pre-existing baseline failure (662 passed/3 failed BEFORE any phase-6 work), reconfirmed unchanged after 06-01 (694 passed/3 failed), and reconfirmed again as still-open in 06-04-SUMMARY.md and 06-VERIFICATION.md (2026-09-20). Root introduction point not yet established — likely phase 4 (artifact/worktree mechanics) or phase 5 (worktree lifecycle / D-09 per-role commit, D-10 PR-diff exclusion), never phase 6.
- **Reproduction:**
  - `uv --directory /Users/maryiakrauchanka/portfolio/dark-factory run pytest -q tests/db/test_artifact_commit_per_role.py tests/integration/test_pr_diff_excludes_artifacts.py` against a real PostgreSQL 17 (`.env` sourced or `DARK_FACTORY_TEST_DATABASE_URL` set).
  - This debugging session has NO reachable PostgreSQL 17 (no Docker, no local `initdb` 17, `DATABASE_URL` unset) — investigation must proceed via static/source analysis of the worktree lifecycle and artifact-commit code paths (`src/dark_factory/orchestrator/runner.py`, the git worktree/scope modules, `src/dark_factory/artifacts/`), cross-referencing the three failing tests' fixtures and assertions, and the adjacent phase-5 debug session `.planning/debug/in-scope-edit-missing-after-completed.md` (CONFIRMED root cause: worktree deleted on `COMPLETED` per D-04 — a *different* test, `test_an_in_scope_edit_completes_with_no_revert`, but same subsystem) in case the same D-04 cleanup-timing class of bug explains any of these three.

## Evidence

- timestamp: 2026-09-20
  checked: src/dark_factory/git/scope.py:70-92 (`is_out_of_scope`) + module docstring lines 16-20
  found: D-14 polarity -- an empty `write_scope` means ZERO TOLERANCE, not "unrestricted". `not any(fnmatchcase(path, p) for p in write_scope)` over an empty sequence is `True` for EVERY path. The docstring explicitly forbids adding an empty-list early return.
  implication: any role whose fixture declares `permissions: write_scope: []` fails on the first non-artifact path it changes

- timestamp: 2026-09-20
  checked: src/dark_factory/orchestrator/runner.py:923-958
  found: `enforce_write_scope` runs inside `_run_current_role` when `signal is Signal.ROLE_COMPLETED`, i.e. AFTER collect_role_artifacts + commit_run_artifacts + push_working_branch. A `WriteScopeViolation` flips the signal to `Signal.ROLE_FAILED` and clears `artifact_writes`.
  implication: a violation turns an otherwise-COMPLETED role into ROLE_FAILED -> RUN_FAILED, and `revert_paths` has already destroyed the offending file/index entry by the time the caller observes anything

- timestamp: 2026-09-20
  checked: src/dark_factory/git/scope.py:95-139 (`attempt_changed_paths`) and :165-247 (`revert_paths`)
  found: changed-path collection is `git diff --name-only HEAD` + `git ls-files --others --exclude-standard`, both with ARTIFACT_EXCLUDE_PATHSPEC (so `.dark-factory` is exempt). For a path absent from HEAD the revert is `git rm --cached --force --quiet -- <path>` then `git clean --force -- <path>`.
  implication: a newly-created, staged, non-artifact file is un-staged AND deleted -- `git diff --cached --name-only` afterwards is exactly `[]`

- timestamp: 2026-09-20
  checked: tests/db/test_artifact_commit_per_role.py:202-215 (`_write_four_role_tree`)
  found: every one of BA/ARCHITECTURE/DEVELOPMENT/QA is written with `permissions:\n  write_scope: []`. The test then creates+stages `work_dir/source_edit.txt` (lines 290-294) and immediately advances ARCHITECTURE (296-299) before asserting `"source_edit.txt" in staged_after` (301-304).
  implication: ARCHITECTURE's post-role enforcement sees `source_edit.txt` as its single out-of-scope change, reverts it, and `staged_after` is `[]` -- the exact reported `assert 'source_edit.txt' in []`

- timestamp: 2026-09-20
  checked: tests/conftest.py:385-390 (`_write_scope`) vs tests/db/test_artifact_commit_per_role.py:361,376-389
  found: `config_root_factory` gives BA `write_scope: "[]"`; `_TrailingEditWorker.execute` writes `work_dir/trailing_edit.txt` from inside BA's own worker call.
  implication: BA's enforcement reverts trailing_edit.txt and raises -> RUN_FAILED, the exact reported `assert <RunStatus.FAILED> is <RunStatus.COMPLETED>`. Secondary consequence: with the edit reverted, `_cleanup_run_worktree`'s `wip_commit_if_dirty` would find nothing dirty, so the test's later WIP-commit assertion (line 426) is also unreachable.

- timestamp: 2026-09-20
  checked: tests/integration/test_pr_diff_excludes_artifacts.py:74-89 (BA fixture) and :166-180 (`_RoleAwareDiffProofWorker.execute`)
  found: BA is written with `permissions:\n  write_scope: []` and BA's own `execute()` writes `work_dir/feature.py`.
  implication: BA's enforcement reverts feature.py and raises -> RUN_FAILED at the second `advance`, the exact reported `assert <RunStatus.FAILED> is <RunStatus.DEVELOPMENT>`

- timestamp: 2026-09-20
  checked: the two SIBLING tests in the same file that PASS -- test_failed_run_keeps_its_worktree (:429) and test_waiting_human_run_keeps_its_worktree (:469)
  found: both use the identical `config_root_factory(roles=("BA",))` tree with the same `write_scope: []`, but their scripted workers write NOTHING to the worktree (plain `FakeWorker`, no source file), and neither reaches `Signal.ROLE_COMPLETED` (FAILED / NEEDS_INPUT), so the enforcement branch at runner.py:944 never even runs.
  implication: the pass/fail split across the file is explained exactly by "does this test plant a non-artifact file in the worktree while the role's write_scope is empty" -- a single-cause, no second condition needed

## Eliminated

- hypothesis: "D-14's zero-tolerance polarity in `is_out_of_scope` is itself the bug (an empty write_scope should mean unrestricted)"
  evidence: "scope.py:84-90 forbids the inversion in terms (`**No early-return branch for the empty-list case may ever be added here.**`), and tests/unit/test_write_scope.py + test_write_scope_revert.py pin the behaviour (442 unit tests pass unchanged). 05-VERIFICATION.md records SC4 as VERIFIED with 6/6 integration scenarios. Inverting it would silently grant every role write access to all source -- an authorization regression."
  timestamp: 2026-09-20

- hypothesis: "Same D-04 cleanup-timing class as the adjacent session in-scope-edit-missing-after-completed.md (test asserts against a worktree the design deletes on COMPLETED)"
  evidence: "Symptoms 2 and 3 never REACH a terminal COMPLETED at all -- they report FAILED. The failure happens at `enforce_write_scope` (runner.py:944-958) strictly BEFORE any cleanup arm runs. Symptom 1's assertion runs mid-run, two roles before COMPLETED. D-04 cleanup timing is causally downstream of all three failures."
  timestamp: 2026-09-20

- hypothesis: "The artifact commit sweeps up the staged source file (a pathspec leak in commit_run_artifacts)"
  evidence: "diff.py:143-152 commits with a trailing `-- .dark-factory/runs/<run_id>` pathspec, so the staged source change is provably NOT swept in. Confirmed by git probe: a plain `git commit` DOES sweep the index, but the pathspec-limited form does not. T-05-17's guarantee holds -- which is precisely why `source_edit.txt` stays staged and remains visible to every later role's enforcement."
  timestamp: 2026-09-20

- hypothesis: "Phase 6's tool-registry / capability-enforcement work introduced the regression"
  evidence: "Baseline 662 passed/3 failed BEFORE any phase-6 work (06-01-SUMMARY.md); the same 3 failed after (694 passed/3 failed). Confirmed statically: the failing code path is scope.py/runner.py:944-958 (phase 5, plan 05-04), which contains no capability/tool-registry call. The fixtures' `tools:` lines were correctly updated for phase 6; their `write_scope:` lines were not updated for phase 5."
  timestamp: 2026-09-20

## Resolution

root_cause: |
  Stale test fixtures, not a production defect. Three tests declare a role
  `permissions: write_scope: []` -- which under D-14 means ZERO TOLERANCE
  (a path matches none of zero patterns, so every changed path is a
  violation) -- while that same test's own worker or fixture plants a
  non-artifact file in the worktree. At `Signal.ROLE_COMPLETED`
  (runner.py:944-958) `enforce_write_scope` reverts the planted file
  (`git rm --cached` + `git clean` for a path absent from HEAD) and raises
  `WriteScopeViolation`, flipping the signal to `ROLE_FAILED` -> `RUN_FAILED`.
  The fixtures predate phase 5 plan 05-04's D-14 enforcement and were never
  updated to authorize what their own workers write. Their `tools:` lines
  WERE updated for phase 6; their `write_scope:` lines were missed for phase 5.

  Per-symptom mapping:
  1. `source_edit.txt` staged before ARCHITECTURE's advance -> ARCHITECTURE
     reverts it -> `git diff --cached --name-only` is exactly `[]`
     -> `assert 'source_edit.txt' in []`.
  2. `_TrailingEditWorker` writes `trailing_edit.txt` inside BA's execute
     -> BA reverts and fails -> `FAILED` instead of `COMPLETED`.
  3. `_RoleAwareDiffProofWorker` writes `feature.py` inside BA's execute
     -> BA reverts and fails -> `FAILED` instead of `DEVELOPMENT`.

fix: |
  Test-defect fix, ZERO production changes (same class and precedent as the
  05-05 G-05-1 closure, recorded in 05-05-SUMMARY.md:33 and
  05-VERIFICATION.md:113). Each failing test's role `write_scope` is widened
  to name EXACTLY the one non-artifact file that test's own worker/fixture
  writes -- nothing broader, and never by slackening a shared default:

  1. `tests/db/test_artifact_commit_per_role.py::_write_four_role_tree`
     (private to this file, single call site) -- replaced the uniform
     `write_scope: []` with a per-role dict: BA stays `[]` (it runs before
     the file exists); ARCHITECTURE, DEVELOPMENT and QA each get
     `[source_edit.txt]`. All three are needed, not just ARCHITECTURE,
     because the pathspec-limited artifact commit leaves the file staged, so
     `git diff --name-only HEAD` reports it for every subsequent role.
  2. `tests/db/test_artifact_commit_per_role.py::test_completed_run_with_a_trailing_edit_...`
     -- a per-test in-place patch of the BA role YAML written by the SHARED
     `config_root_factory`, replacing only that one `write_scope` line with
     `[trailing_edit.txt]`. `tests/conftest.py` is deliberately NOT edited:
     the sibling `test_failed_run_keeps_its_worktree` and
     `test_waiting_human_run_keeps_its_worktree` ride on the same default and
     must keep the zero-tolerance empty list. An assertion makes a conftest
     reformat fail loudly rather than silently no-op the patch.
  3. `tests/integration/test_pr_diff_excludes_artifacts.py::_write_two_role_tree`
     (private, single call site) -- BA gets `[feature.py]`. DEVELOPMENT
     deliberately KEEPS `write_scope: []`: by the time its enforcement runs,
     its before-hook has WIP-committed `feature.py` and everything it writes
     itself lives under the excluded `.dark-factory/runs` tree.

  Every edit carries an inline comment restating D-14's polarity so a future
  reader cannot re-introduce the empty list believing it means "unrestricted".

verification: |
  guardrail_verdict: accepted -- every applicable signal PASSES, including the
  acceptance signal. This is a CLEAN pass, not `accepted_debt`: no signal was
  waived and no technical-debt escape was invoked. (Superseded verdict, kept for
  the trail: "PARTIAL -- accepted statically, acceptance signal UNVERIFIED",
  which was correct at the time the fix was applied and is no longer.)

  Provenance note, stated precisely: the fix itself was derived STATICALLY in
  this session -- no database was ever reachable here. The PASS evidence below
  comes from the USER's own terminal run against real PostgreSQL 17. This
  session did not execute the db/ or integration/ tiers at any point.

  signal: production-code-untouched -- PASS. `git status --porcelain -- src/`
    is empty. Only the two test files are modified.
  signal: not-a-symptom-deletion -- PASS. No assertion was weakened or removed;
    no test was skipped or xfailed. The three tests still assert exactly what
    they asserted before. Zero-tolerance coverage is untouched.
  signal: coverage-not-silently-deleted -- PASS. `tests/conftest.py` was NOT
    edited, so the two sibling zero-tolerance tests in the same file and every
    other `config_root_factory` consumer keep the empty-list default. The
    dedicated suites `tests/unit/test_write_scope.py`,
    `tests/unit/test_write_scope_revert.py` and
    `tests/integration/test_write_scope_enforcement.py` are untouched.
  signal: pattern-correctness -- PASS (executed). `yaml.safe_load` parses each
    new value to the intended single-element list;
    `validate_write_scope_patterns` accepts all three; `is_out_of_scope`
    returns False for the intended file and still True for `src/app.py` under
    `[feature.py]` and True for everything under `[]`.
  signal: collection -- PASS (executed). `uv run pytest --collect-only -q` on
    both files: 5 tests collected in 0.07s, no import/syntax/collection error.
  signal: lint/format/type -- PASS (executed). `ruff check` -> All checks
    passed; `ruff format --check` -> 2 files already formatted; `mypy` ->
    Success: no issues found in 2 source files.
  signal: regression (DB-free tier) -- PASS (executed). `uv run pytest -m unit
    -q` -> 442 passed, 321 deselected, 19.50s. No unit-tier regression.
  signal: acceptance (the 3 target tests go green) -- **VERIFIED / PASS**
    (2026-09-20). Executed by the USER in their own terminal against a real
    PostgreSQL 17 -- NOT by this session, which has no reachable database
    (`DATABASE_URL` and `DARK_FACTORY_TEST_DATABASE_URL` both unset; `docker`,
    `initdb` and `pg_ctl` all MISSING; the repo's `.env` blocked by the harness
    secret-read guard). Command run:
      set -a; . ./.env; set +a
      uv run pytest -q tests/db/test_artifact_commit_per_role.py \
                       tests/integration/test_pr_diff_excludes_artifacts.py
    Verbatim output:
      .....                                                                    [100%]
      5 passed in 197.62s (0:03:17)
    All 5 tests pass, up from the long-standing 3-failed baseline (3 failed ->
    0 failed across these two files). No later assertion failed, so the
    previously-unreachable downstream assertions -- the trailing-edit test's
    WIP-commit assertion and the integration test's three-dot/two-dot diff
    assertions -- executed to completion and passed. The static derivation is
    now a confirmed empirical pass.

  Scope of the acceptance evidence, not overstated: the user's run covered the
  two target files only (5 tests). A full-suite re-run to confirm the overall
  "3 failed" baseline is now 0 failed has NOT been performed and is recorded as
  a non-blocking residual in Current Focus.next_action.

files_changed:
  - tests/db/test_artifact_commit_per_role.py: per-role write_scope in `_write_four_role_tree` (BA `[]`, ARCHITECTURE/DEVELOPMENT/QA `[source_edit.txt]`); per-test BA write_scope patch `[trailing_edit.txt]` in the trailing-edit test
  - tests/integration/test_pr_diff_excludes_artifacts.py: BA write_scope `[feature.py]` in `_write_two_role_tree` (DEVELOPMENT deliberately left at `[]`)

oracle_type: specified -- each assertion checks a documented contract (D-09
  per-role artifact commit, D-14 write-scope enforcement, D-10 PR-diff
  exclusion), not merely "does not crash".

## Prevention

Blameless postmortem. No individual error here -- this is a change-management
gap around turning an inert config field into an enforced authorization gate.

### Branching 5-whys

1. **Why did the three tests fail?** `enforce_write_scope` reverted each test's
   planted non-artifact file and raised `WriteScopeViolation`, flipping
   `ROLE_COMPLETED` -> `ROLE_FAILED` -> `RUN_FAILED`.
2. **Why did it raise?** The role's `write_scope` was `[]`, which under D-14
   means ZERO TOLERANCE (a path matches none of zero patterns), while that same
   test's own worker/fixture wrote a file into the worktree.
3. **Why was `write_scope` `[]`?** The fixtures were authored BEFORE phase 5
   plan 05-04 added enforcement. Until then the field was inert, so `[]` read
   naturally as "unspecified / don't care" -- a harmless placeholder.
4. **Why weren't the fixtures updated when 05-04 landed?** Enforcement was added
   at the runner call site (runner.py:944-958) without a sweep of existing
   fixtures that declared an empty `write_scope` AND whose workers write to the
   worktree. The change silently promoted a placeholder value into a strict
   deny-all policy; every such fixture became a latent failure at the moment of
   the commit that introduced enforcement.
5. **Why did it survive two phases undiagnosed?** The failures WERE detected --
   but they were triaged as "pre-existing, unrelated to this phase" in
   06-01-SUMMARY.md and then carried forward as an accepted baseline through
   06-04-SUMMARY.md and 06-VERIFICATION.md. A standing "662 passed / 3 failed"
   became normal, so the red count stopped carrying information.

Two independent contributing conditions, in different categories:
- **config/process:** no fixture sweep accompanied the inert-to-enforced change.
- **process/culture:** a persistent red baseline was documented rather than
  driven to zero, which suppressed the signal that would have prompted triage.
(Note this is about why it went UNDIAGNOSED for two phases; the failure
mechanism itself remains single-cause -- the `and_gate` above stays "no".)

### Why wasn't this caught earlier?

Honestly: **the detection gate worked; the response gate did not exist.** The
db/ and integration/ tiers caught this the moment enforcement landed and kept
reporting it correctly for two phases. What was missing was a rule that a
non-zero failure count blocks phase verification -- so the correct signal was
repeatedly observed, correctly attributed to "not this phase", and never
assigned an owner.

A secondary, genuine gap: **no gate existed for the class** "a config field
changes from inert to enforced and existing fixtures declaring the
permissive-LOOKING value are not swept." Nothing statically links "this role
declares `write_scope: []`" to "this role's worker writes files", so nothing
could have flagged the stale fixtures at the time 05-04 merged.

Aggravating factor, not a cause: the db/integration tiers need a real
PostgreSQL 17, so they are absent from the fast inner loop and from any
environment (including this debugging session) without a database. That raises
the cost of running them and makes a red baseline easier to tolerate.

### Recurrence guards

Implemented by this fix:
- **Regression tests (the three themselves).**
  `tests/db/test_artifact_commit_per_role.py::test_one_artifact_commit_per_role_force_added_and_source_edits_survive`,
  `...::test_completed_run_with_a_trailing_edit_gets_a_recovery_commit_then_loses_its_worktree`,
  and `tests/integration/test_pr_diff_excludes_artifacts.py::test_pr_diff_excludes_dark_factory_and_ignores_the_base_branchs_own_post_cut_commit`
  now pass ONLY while each role authorizes exactly the file its own worker
  writes. Narrowing a `write_scope` back to `[]` re-breaks them immediately.
- **Inline D-14 polarity comments** at every edited `write_scope`, so a future
  reader cannot re-introduce `[]` believing it means "unrestricted".
- **A loud assertion** in the trailing-edit test that fails if the shared
  `config_root_factory` YAML is reformatted, rather than silently no-opping the
  in-place patch.
- **`tests/conftest.py` deliberately NOT edited**, preserving the empty-list
  zero-tolerance default for the two sibling tests that depend on it.

Recommended, NOT implemented here (out of scope for a test-defect fix; record
as follow-up rather than claim as done):
- Treat any db/integration failure as a phase-verification blocker instead of a
  documentable baseline -- this is the guard that would actually have collapsed
  the two-phase delay.
- When a config field moves from inert to enforced, require an explicit sweep of
  existing fixtures declaring that field as part of the enforcing plan.
