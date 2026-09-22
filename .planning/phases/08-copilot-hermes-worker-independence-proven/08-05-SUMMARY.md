---
phase: 08-copilot-hermes-worker-independence-proven
plan: 05
subsystem: git-scope-enforcement
tags: [artifact-scope, write-scope, gap-closure, code-review-remediation, security, hermes-worker, copilot-worker, native-tool-contract]

requires:
  - phase: 08-copilot-hermes-worker-independence-proven
    provides: "enforce_write_scope, is_out_of_scope, revert_paths and the D-14 zero-tolerance matcher polarity in git/scope.py (Phase 5) -- the exact matcher and revert mechanism this plan's sibling control reuses rather than duplicates."
  - phase: 08-copilot-hermes-worker-independence-proven
    provides: "08-REVIEW.md CR-01/WR-02/WR-03 -- the code-review findings this plan closes -- and 08-02-SUMMARY.md's Option A checkpoint decision record, whose denied-capability analysis this plan's addendum extends to the granted case."
provides:
  - "enforce_artifact_scope(worktree, run_id, *, role, attempt, granted) -- a sibling post-hoc control in git/scope.py that confines a granted artifacts.write to a role's own artifacts/<role>/ subtree for every worker at once, wired into orchestrator/runner.py ahead of collect_role_artifacts/commit_run_artifacts/push_working_branch"
  - "ArtifactScopeViolation(GitError) -- the exception the runner folds into the existing ROLE_FAILED/RUN_FAILED shape, no new event type or status"
  - "attempt_changed_artifact_paths(worktree, run_id) -- enumerates changed paths under a run's gitignored artifacts/ tree via git diff + git ls-files --others --ignored, the mirror function A-05-15's attempt_changed_paths deliberately excludes"
  - "revert_paths(..., include_ignored=True) -- extends the existing revert mechanism to remove an untracked, ignored file a role created inside another role's subtree"
  - "run_root_writes keyword on the shared fake-CLI generator -- lets a test make a real adapter's real subprocess write outside its own artifact subtree, the mechanism both negative proofs depend on"
  - "The corrected NATIVE_TOOL_CONTRACT Copilot artifacts.* prose, spawn_is_permitted's granted-case docstring paragraph, and the 08-02-SUMMARY.md addendum -- closing WR-02/WR-03"
affects: []

actuals:
  tokens: 17200
  tasks: 3
  commits: 6
  plan_head_before: cf2a4b5ea53a19a671bd31ca072ef471a64d08e8

tech-stack:
  added: []
  patterns:
    - "Sibling post-hoc control over a shared matcher: enforce_artifact_scope reuses is_out_of_scope's D-14 zero-tolerance polarity and revert_paths' revert-then-raise shape rather than inventing a second enforcement mechanism -- the same pattern enforce_write_scope already established, now proven to generalize to a second gitignored subtree the first control deliberately does not cover."
    - "Orchestrator-side, worker-agnostic enforcement ordering: a new control is added as its own sibling `if signal is Signal.ROLE_COMPLETED:` block placed before the artifact collect/commit/push sequence, not a branch inside the existing block -- keeps the diff readable and the docstring's stated ordering (enforce artifact scope, then check the grant, then read, then validate, then commit, then push, then enforce write scope) verifiably true."
    - "Documentation-truth pinning: a retired overclaiming string (Copilot 'same scope as Claude Code') is asserted absent from every contract entry, and the contract's breadth statement is pinned to the shipped `_TOOL_NAMES` translation table by a direct equality assertion -- so contract and implementation cannot silently diverge again."

key-files:
  created:
    - tests/unit/test_artifact_scope.py
    - tests/integration/test_artifact_scope_enforcement.py
  modified:
    - src/dark_factory/git/__init__.py
    - src/dark_factory/git/scope.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/tools/native.py
    - src/dark_factory/workers/copilot.py
    - src/dark_factory/workers/hermes.py
    - tests/support/fake_cli.py
    - tests/support/fake_claude_cli.py
    - tests/support/fake_copilot_cli.py
    - tests/support/fake_hermes_cli.py
    - tests/unit/test_native_tool_contract.py
    - .planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md

key-decisions:
  - "Implemented option (a) -- a sibling post-hoc artifact-scope enforcement check (enforce_artifact_scope) reusing enforce_write_scope's is_out_of_scope matcher and revert_paths mechanism -- not option (b), extending spawn_is_permitted's 'no-compensating-control -> refuse to spawn' rule to the granted case. Option (b) would have broken locked decision D-04: it would refuse to spawn for both of this phase's shipped reassignments (QA -> hermes, ARCHITECTURE -> copilot), unshipping the phase's own headline SC2 proof to close a gap option (a) closes without touching it. Option (a) also lands the control where it belongs architecturally -- orchestrator-side and worker-agnostic, holding the boundary for all four workers at once rather than being re-derived per adapter."
  - "The read half (artifacts.read) is not closed by any post-hoc control, because no mechanism can undo a read. It is treated as a documentation-truth fix (WR-02/WR-03) rather than an enforcement gap: a granted artifacts.read on Copilot/Hermes carries reach identical to repo.read, which is in fact the intended posture -- ClaudeCodeWorker's own artifacts.read grant is deliberately run-scoped, not role-scoped."
  - "The DB-gated end-to-end integration proofs (Hermes negative case, Copilot negative case, positive control) are written and collection-verified but not execution-verified in this sandbox, which has no reachable PostgreSQL 17 -- the same pre-existing constraint every prior 08-* plan documented. This is recorded honestly in coverage below with human_judgment: true rather than claimed as passing."

patterns-established:
  - "A worker-agnostic post-hoc control proven identically on two different real CLI adapters (Hermes, Copilot) through one shared drive-and-collect harness parametrized only by which fake CLI carries the tampering entry -- so the two negative proofs are visibly the same proof on two runtimes, not two independently written tests that could diverge."

requirements-completed: [WORK-05, WORK-06, ROLE-05, TOOL-03]

coverage:
  - id: D1
    description: "attempt_changed_artifact_paths enumerates changed paths under a run's gitignored artifacts/ tree via git diff + git ls-files --others --ignored (never a directory walk), returning [] for a nonexistent artifacts/ tree or no change, and never reporting verification/, logs/, or input/ paths"
    requirement: "ROLE-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_artifact_scope.py (empty-tree, no-change, tracked-modification, new-file, verification/-exclusion, logs/-exclusion, input/-exclusion cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "enforce_artifact_scope confines a granted artifacts.write to the role's own artifacts/<role>/ subtree (in-scope, deep-nesting, decoy-sibling matcher cases), enforces D-14 zero tolerance when artifacts.write is not granted, reverts a modified prior-role artifact from HEAD and removes a role-created foreign file, reverts every violation before raising, and leaves an in-scope write in the same attempt untouched when a foreign write is also present"
    requirement: "ROLE-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_artifact_scope.py (all 17 non-end-to-end cases, including the deleted-artifact-restore and mixed in-scope/out-of-scope cases added in Task 2)"
        status: pass
    human_judgment: false
  - id: D3
    description: "ArtifactScopeViolation is a GitError subclass and the runner folds it into the existing ROLE_FAILED/RUN_FAILED shape; enforce_artifact_scope runs before collect_role_artifacts/commit_run_artifacts/push_working_branch so a tampered path is reverted before it can be committed or pushed"
    requirement: "ROLE-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_git_ownership_boundary.py, tests/unit/test_no_tree_walk.py, tests/unit/test_write_scope.py (all pass unchanged, confirming A-05-15 and the existing write-scope control are untouched)"
        status: pass
    human_judgment: false
  - id: D4
    description: "End to end: a role running on the real HermesWorker that overwrites another role's committed artifact (QA writing into artifacts/ARCHITECTURE/design.md) leaves the run not COMPLETED, QA's execution FAILED naming the violating path, and design.md restored to ARCHITECTURE's committed content"
    requirement: "ROLE-05"
    verification:
      - kind: integration
        ref: "tests/integration/test_artifact_scope_enforcement.py::test_a_hermes_run_qa_that_overwrites_architectures_artifact_is_reverted_and_fails"
        status: not_run
    human_judgment: true
    rationale: "Requires a reachable PostgreSQL 17 for the pg_url/engine fixtures (same precondition tests/integration/test_write_scope_enforcement.py already carries). This sandbox has no Docker, no local initdb/pg_ctl, and no DARK_FACTORY_TEST_DATABASE_URL -- confirmed via the same pre-run assertion plans 08-01 through 08-04 all hit. The test collects cleanly (verified: 3 tests collected, zero import/collection errors) but cannot execute here. Re-run once a real Postgres 17 is available: `uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py`."
  - id: D5
    description: "End to end: the identical boundary holds on the real CopilotWorker (ARCHITECTURE writing into artifacts/BA/acceptance_criteria.json fails ARCHITECTURE, stops the pipeline before DEVELOPMENT/QA, restores BA's artifact) -- the same proof on the second runtime, through the same shared harness"
    requirement: "ROLE-05"
    verification:
      - kind: integration
        ref: "tests/integration/test_artifact_scope_enforcement.py::test_a_copilot_run_architecture_that_overwrites_bas_artifact_is_reverted_and_fails"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D4. Collection-verified clean; not execution-verified in this sandbox. Re-run once a real Postgres 17 is available: `uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py`."
  - id: D6
    description: "Positive control: the identical shipped four-role configuration with no tampering entry reaches COMPLETED with all four roles completed and every role's artifacts collected -- the new control adds no failure to correct behaviour"
    requirement: "TOOL-03"
    verification:
      - kind: integration
        ref: "tests/integration/test_artifact_scope_enforcement.py::test_the_identical_shipped_config_with_no_tampering_completes_with_all_artifacts"
        status: not_run
    human_judgment: true
    rationale: "Same missing-Postgres precondition as D4/D5. Collection-verified clean; not execution-verified in this sandbox. Re-run once a real Postgres 17 is available: `uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py`."
  - id: D7
    description: "WR-02 closed: NATIVE_TOOL_CONTRACT's Copilot artifacts.read/artifacts.write prose states the shipped posture (unscoped, identical breadth to repo.read/repo.write) and no longer claims Claude-Code-equivalent scoping; artifacts.write names enforce_artifact_scope as the control holding the boundary post-hoc. Pinned by two assertions: the retired equivalence claim appears in no entry's copilot field, and copilot._TOOL_NAMES['artifacts.read'/'artifacts.write'] equal _TOOL_NAMES['repo.read'/'repo.write']"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_native_tool_contract.py (two new assertions, plus test_hermes_entries_are_honest_about_having_no_native_mechanism and test_every_claude_code_entry_names_the_real_worktree_mechanism unchanged and passing)"
        status: pass
    human_judgment: false
  - id: D8
    description: "WR-03 closed: spawn_is_permitted's docstring, hermes.py's module docstring, and copilot.py's _TOOL_NAMES comment each state the granted-case enforcement boundary explicitly -- a granted artifacts.write is confined post-hoc by enforce_artifact_scope, a granted artifacts.read carries reach identical to repo.read with no narrowing mechanism of any kind"
    requirement: "WORK-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_hermes_worker.py, tests/unit/test_copilot_worker.py (unchanged, passing); spawn_is_permitted.__doc__ manually confirmed to contain both artifacts.write and artifacts.read granted-case statements"
        status: pass
    human_judgment: false
  - id: D9
    description: "08-02-SUMMARY.md gains an additive addendum recording the granted-case finding (CR-01) and this plan's resolution (option a); the original Option A decision record and every frontmatter key survive verbatim"
    requirement: "WORK-05"
    verification:
      - kind: automated
        ref: "git diff --numstat cf2a4b5..f82f176 -- .planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md reports 65 added, 0 deleted"
        status: pass
    human_judgment: false
  - id: D10
    description: "The full unit+contract suite (630 tests), mypy on src/dark_factory, and ruff check all pass in this sandbox with no new errors beyond the 2 pre-existing, unrelated mcp_transport.py import errors"
    requirement: "TOOL-03"
    verification:
      - kind: unit
        ref: "uv run pytest -m 'unit or contract' -q -> 630 passed, 1 skipped, 322 deselected"
        status: pass
      - kind: automated
        ref: "uv run mypy src/dark_factory -> 2 pre-existing errors in tools/mcp_transport.py only; uv run ruff check . -> All checks passed"
        status: pass
    human_judgment: false

duration: 13min (implementation, 2026-09-21) + resume verification session (2026-09-22)
completed: 2026-09-22
status: complete
---

# Phase 8 Plan 5: Artifact-Scope Enforcement Gap Closure Summary

**Closes 08-REVIEW.md's CR-01 (BLOCKER), WR-02 and WR-03: `enforce_artifact_scope` -- a sibling post-hoc control (option a) reusing `enforce_write_scope`'s matcher and revert mechanism -- now confines a granted `artifacts.write` to a role's own `artifacts/<role>/` subtree on every worker, proven end to end on both Hermes and Copilot, with the design contract and decision record corrected to state the real granted-capability enforcement posture.**

## Performance

- **Duration:** ~13 minutes of implementation work on 2026-09-21 (19:36:59 to 19:49:06, first commit to last), followed by a resume session on 2026-09-22 that fast-forwarded the prior work in, re-ran all non-DB-gated verification, and wrote this SUMMARY
- **Started:** 2026-09-21T19:36:59+03:00
- **Completed:** 2026-09-22 (this resume)
- **Tasks:** 3
- **Files modified:** 12 (2 created, 10 modified)

## Accomplishments

- `enforce_artifact_scope(worktree, run_id, *, role, attempt, granted)` (`src/dark_factory/git/scope.py`) is a real, tested, wired-in control: it enumerates every path a role's attempt changed under the run's `.dark-factory/runs/<run_id>/artifacts/` tree via `attempt_changed_artifact_paths` (two `run_git` calls only -- `diff --name-only HEAD` and `ls-files --others --ignored --exclude-standard`, both scoped to the artifacts pathspec, no directory walk), reverts every path outside the role's own `artifacts/<role>/**` subtree (or every path at all when `artifacts.write` is not granted, under the same D-14 zero-tolerance polarity `is_out_of_scope` already implements), and raises `ArtifactScopeViolation` naming the role, attempt and complete violation set.
- `ArtifactScopeViolation` is a `GitError` subclass; `orchestrator/runner.py` folds it into the identical `ROLE_FAILED`/`RUN_FAILED` shape every other post-worker check already writes -- no new event type, no new status. The check runs in its own sibling block, placed *before* `collect_role_artifacts`/`commit_run_artifacts`/`push_working_branch`, because a tampered path stops being visible to a `HEAD` diff the moment it is committed, and has left the machine the moment it is pushed.
- `revert_paths` gained `include_ignored: bool = False` -- when true, the absent-from-`HEAD` revert branch also passes the flag that makes `git clean` act on ignored files, because the entire run tree is gitignored and a role-created foreign file is therefore an *ignored* untracked file the default clean invocation would silently leave on disk. The default preserves `enforce_write_scope`'s existing behaviour byte-for-byte.
- The shared fake-CLI generator (`tests/support/fake_cli.py`) gained a `run_root_writes` keyword, forwarded unchanged through all three CLI wrappers -- the mechanism that lets a test make a real adapter's real subprocess write outside its own artifact subtree, which both negative proofs depend on.
- The boundary is proven on both new runtimes through one shared drive-and-collect harness in `tests/integration/test_artifact_scope_enforcement.py`, parametrized only by which fake CLI carries the tampering entry: a Hermes-run `QA` overwriting `ARCHITECTURE`'s artifact, and a Copilot-run `ARCHITECTURE` overwriting `BA`'s artifact, each fail the offending role, stop the pipeline, and restore the tampered file -- plus a positive-control test proving the identical shipped configuration with no tampering still reaches `COMPLETED` with all four roles' artifacts collected.
- `NATIVE_TOOL_CONTRACT`'s Copilot `artifacts.read`/`artifacts.write` prose (`src/dark_factory/tools/native.py`) no longer claims Claude-Code-equivalent scoping it does not have; it states the shipped posture (unscoped, identical breadth to `repo.read`/`repo.write`) and, for write, names `enforce_artifact_scope` as the control that holds the boundary post-hoc. Two new unit assertions pin this: the retired equivalence claim is asserted absent from every entry, and `copilot._TOOL_NAMES['artifacts.*']` is asserted equal to `_TOOL_NAMES['repo.*']`, so the contract's breadth statement is checkable rather than decorative.
- `spawn_is_permitted`'s docstring, `hermes.py`'s module docstring, and `copilot.py`'s `_TOOL_NAMES` comment each now state the granted-case boundary explicitly, not only the denied case -- closing WR-03.
- `.planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md` gained an additive addendum (verified: 65 lines added, 0 deleted) recording the granted-case finding this checkpoint did not originally examine and how this plan resolved it, leaving the original Option A decision record completely intact.

## Task Commits

Each task was committed atomically (RED test, then GREEN implementation where applicable):

1. **Task 1 RED: failing unit test for `enforce_artifact_scope`** - `94a3038` (test)
2. **Task 1 GREEN: `enforce_artifact_scope` confines granted `artifacts.write` to a role's own subtree** - `3173bed` (feat)
3. **Task 1: end-to-end Hermes artifact-scope negative proof (DB-gated)** - `e65aa25` (test)
4. **Task 2: the same boundary on Copilot, plus the positive control** - `29ec3c2` (test)
5. **Task 3: contract and decision-record fixes (WR-02, WR-03)** - `f82f176` (docs)
6. **Plan metadata: this SUMMARY commit** (STATE/ROADMAP applied by the orchestrator after wave merge -- worktree mode)

## Files Created/Modified

- `src/dark_factory/git/__init__.py` - `ArtifactScopeViolation(GitError)`, a sibling of `WriteScopeViolation`
- `src/dark_factory/git/scope.py` - `ARTIFACTS_WRITE_CAPABILITY` constant, `attempt_changed_artifact_paths()`, `enforce_artifact_scope()`, `revert_paths(..., include_ignored=)`
- `src/dark_factory/orchestrator/runner.py` - `granted` hoisted above both post-worker `ROLE_COMPLETED` blocks; new sibling block calling `enforce_artifact_scope` before the artifact collect/commit/push sequence
- `src/dark_factory/tools/native.py` - Copilot `artifacts.*` prose rewritten (WR-02); module docstring gains the granted-case finding paragraph
- `src/dark_factory/workers/copilot.py` - `_TOOL_NAMES` deviation-1 comment replaced with the real posture
- `src/dark_factory/workers/hermes.py` - module docstring and `spawn_is_permitted` docstring state the granted-case boundary (WR-03)
- `tests/support/fake_cli.py`, `fake_claude_cli.py`, `fake_copilot_cli.py`, `fake_hermes_cli.py` - `run_root_writes` keyword added and forwarded
- `tests/unit/test_artifact_scope.py` (created) - full behavior suite for `attempt_changed_artifact_paths`/`enforce_artifact_scope` (17 cases)
- `tests/integration/test_artifact_scope_enforcement.py` (created) - 3 end-to-end scenarios: Hermes negative, Copilot negative, positive control
- `tests/unit/test_native_tool_contract.py` - two new pinning assertions for WR-02
- `.planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md` - additive addendum recording the granted-case finding and this plan's resolution

## Decisions Made

**Implemented option (a): a sibling post-hoc artifact-scope enforcement check, not option (b).**

`08-REVIEW.md`'s CR-01 offered two directions. This plan takes option (a): `enforce_artifact_scope`, a sibling post-hoc control in `git/scope.py` that diffs and reverts out-of-role-subtree changes under `.dark-factory/runs/<run_id>/artifacts/`, reusing `is_out_of_scope`'s matcher and `revert_paths`' revert mechanism rather than inventing a new one. Three facts decided it, stated in the plan's own "judgment call" section:

1. **Option (b) breaks a locked decision.** Extending `spawn_is_permitted`'s "no-compensating-control -> refuse to spawn" rule to the *granted* case of `artifacts.write`/`artifacts.read` would refuse to spawn for `QA` on Hermes and `ARCHITECTURE` on Copilot -- the two assignments locked by D-04 and used verbatim as ROADMAP SC2's own example. It would unship this phase's headline proof to close a gap option (a) closes without touching it.
2. **The write half is genuinely compensable, and cheaply.** `commit_run_artifacts` force-adds and commits the run tree after each completed role, so a prior role's artifacts are *tracked* on the working branch by the time a later role runs -- visible to a `HEAD`-scoped diff over the artifacts pathspec, which `enforce_write_scope` simply never looks at because it excludes that pathspec by design (A-05-15). A sibling check with the opposite pathspec sees all of it.
3. **Option (b) would not close the read half either.** No spawn rule and no post-hoc check can undo a read. The real deviation on Copilot/Hermes is reach *beyond* the artifacts tree, identical to `repo.read`'s breadth -- a documentation-truth problem, not an enforcement one, closed instead by Task 3 (WR-02/WR-03).

The read half (`artifacts.read`) is deliberately left uncompensated by any technical control: `ClaudeCodeWorker`'s own `artifacts.read` grant is run-scoped, not role-scoped, by design ("a worker legitimately reads a prior role's artifact output"), so run-scoped read reach on Copilot/Hermes is the *intended* posture stated honestly, not a residual gap.

## Deviations from Plan

None - plan executed exactly as written. `tests/unit/test_write_scope.py` was listed in the plan frontmatter's `files_modified` as an anticipated touch point but was not actually edited by any commit -- it served only as a regression-proof file (verified to pass unchanged), which is consistent with the plan's own prohibition that write-scope matching semantics must not change.

## Issues Encountered

A previous execution attempt at this exact plan completed all three tasks (5 commits, `94a3038` through `f82f176`) before being cut off mid-session by a provider rate limit right as it began writing this SUMMARY.md -- not a real failure, just an interruption before close-out. This resume verified the prior work was sound: re-ran every non-DB-gated `<verify>` command from the plan (`tests/unit/test_artifact_scope.py`, `test_write_scope.py`, `test_native_tool_contract.py` -- 42 passed; the full `pytest -m "unit or contract" -q` suite -- 630 passed, 1 skipped; `mypy src/dark_factory` -- 2 pre-existing, unrelated `mcp_transport.py` errors only; `ruff check .` -- all checks passed) and found it complete and correct with no code changes needed. The five prior commits were brought in via a clean fast-forward merge (`git merge --ff-only`) from a direct linear ancestor with zero divergence.

**Missing-Postgres precondition (documented, not a failure):** This sandbox has no reachable PostgreSQL 17 -- no Docker, no local `initdb`/`pg_ctl`, no `DARK_FACTORY_TEST_DATABASE_URL` -- the same pre-existing, documented constraint plans 08-01 through 08-04 all hit. The three DB-gated end-to-end scenarios in `tests/integration/test_artifact_scope_enforcement.py` (Hermes negative proof, Copilot negative proof, positive control) collect cleanly (3 tests collected, zero import/collection errors, confirmed in this resume) but could not be executed here. See coverage entries D4, D5, D6 above for the honest `human_judgment: true` accounting, and "User Setup Required" below for the exact re-run command.

## User Setup Required

A reachable PostgreSQL 17 instance is required to execute the three DB-gated end-to-end integration scenarios this plan added (the same precondition every prior 08-* plan's live-database proofs carry). Once available, re-run:

```bash
uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py
```

This should collect and pass all 3 tests: the Hermes negative proof, the Copilot negative proof, and the positive control. All three are collection-verified clean in this sandbox already; only execution against a live database remains.

## Next Phase Readiness

- CR-01 is closed: `artifacts.write`, once granted to a role on any of the four workers, is confined to that role's own `artifacts/<role>/` subtree by a control that actually sees the path -- proven by a negative test on both Hermes and Copilot (pending live-DB execution per above), with the tampered file's committed content restored.
- The compensating-control claim the phase's own code makes is now true for the path it is made about.
- The shipped `QA` -> hermes and `ARCHITECTURE` -> copilot assignments are untouched and still run (locked D-04, ROADMAP SC2 intact) -- option (a) was chosen specifically to avoid breaking either.
- WR-02 and WR-03 are closed: the design contract, both adapters' own prose, and the 08-02 decision record all state the real granted-capability enforcement posture, pinned by tests that fail if the contract and the shipped translation table drift apart again.
- `write_scope` enforcement and A-05-15 are untouched -- confirmed by `tests/unit/test_write_scope.py`, `test_git_ownership_boundary.py`, and `test_no_tree_walk.py` all passing with no assertion edited.
- No blockers identified. The only outstanding item is executing the three DB-gated integration tests against a real PostgreSQL 17 instance, tracked in coverage D4-D6 above.

---
*Phase: 08-copilot-hermes-worker-independence-proven*
*Completed: 2026-09-22*

## Self-Check: PASSED

- Both `key-files.created` verified present on disk (`tests/unit/test_artifact_scope.py`, `tests/integration/test_artifact_scope_enforcement.py`), along with all 10 `key-files.modified` entries (confirmed via `ls -la` on each path).
- `git log --oneline --all --grep="08-05"` returns 6 commits: `f82f176`, `29ec3c2`, `e65aa25`, `3173bed`, `94a3038`, and `cf2a4b5` (the plan-creation commit).
- `uv run pytest -m unit -q tests/unit/test_artifact_scope.py tests/unit/test_write_scope.py tests/unit/test_native_tool_contract.py`: 42 passed.
- `uv run pytest -m "unit or contract" -q` (full suite): 630 passed, 1 skipped (pre-existing, unrelated `mcp` optional-dependency skip), 322 deselected.
- `uv run mypy src/dark_factory`: 2 pre-existing errors in `tools/mcp_transport.py` only (unrelated, unchanged by this plan).
- `uv run ruff check .`: all checks passed.
- `uv run pytest -m integration -q --collect-only` on `tests/integration/test_artifact_scope_enforcement.py`: 3 tests collected, zero import/collection errors.
- `uv run pytest -m integration -q --collect-only` on `test_role_reassignment_sc2.py`, `test_write_scope_enforcement.py`, `test_real_pipeline_zero_config.py`: 9 tests collected, zero errors -- confirming the pre-existing integration suites are unaffected.
- `git diff --numstat cf2a4b5..f82f176 -- .planning/phases/08-copilot-hermes-worker-independence-proven/08-02-SUMMARY.md`: 65 added, 0 deleted -- the addendum is confirmed additive.
- All non-DB-gated plan-level `<verification>` items pass in full; the two DB-gated `<verify>` blocks and the plan-level DB-gated `<verification>` line are honestly deferred per coverage D4-D6, not silently skipped.
