---
phase: quick
plan: 261030-o5x
subsystem: worker-adapters
tags: [claude-code, allowedTools, permissions, native-tool-contract, tdd]

requires:
  - phase: 07
    provides: ClaudeCodeWorker's allowed_tools_for() translation (07-04) that this plan corrects
provides:
  - "artifacts.write now grants both Write(<glob>/**) and Edit(<glob>/**) over one identical glob, so a role's first artifact write (which always creates a new file) is permitted by the real claude CLI instead of silently denied under --permission-mode dontAsk"
affects: [claude-code-worker, native-tool-contract, future-worker-adapters]

actuals:
  tokens: 2428
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A capability-to-native-tool translation that is additive (two names.add() calls over one glob variable) rather than a second glob expression, closing an elevation-of-privilege/under-grant gap without widening scope"

key-files:
  created: []
  modified:
    - tests/unit/test_claude_code_worker.py
    - src/dark_factory/workers/claude_code.py
    - src/dark_factory/tools/native.py

key-decisions:
  - "Neither existing test was renamed, per the plan's resolved-during-planning note -- both are cited as validation proof refs in 07-04-SUMMARY.md and the `_is_path_scoped_not_bare` name remains accurate (both specifiers are path-scoped)"
  - "The new regression test names Write specifically in its name and assertions so an Edit-only regression cannot pass it silently"
  - "docs/CONFIGURATION.md needed no change -- it lists capability names only, never the --allowedTools specifier shape"

requirements-completed: [QUICK-O5X]

coverage:
  - id: D1
    description: "allowed_tools_for({'artifacts.write'}, glob) returns both Edit(<glob>/**) and Write(<glob>/**), sorted, over the identical glob"
    requirement: "QUICK-O5X"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_allowed_tools_for_artifacts_write_is_path_scoped_not_bare"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_artifacts_write_grants_the_new_file_tool_not_only_the_edit_tool"
        status: pass
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py#test_artifacts_write_grant_produces_path_scoped_edit_in_execute_argv"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every unrelated translation (repo.write, repo.write_tests, artifacts.read, no-glob artifacts.write, deny-by-omission) stays byte-identical to before"
    requirement: "QUICK-O5X"
    verification:
      - kind: unit
        ref: "tests/unit/test_claude_code_worker.py -k \"allowed_tools or artifacts_write_grant or artifacts_read_grant or tool_names_cover or ungranted_capability\" -> 18 passed"
        status: pass
    human_judgment: false
  - id: D3
    description: "allowed_tools_for() docstring and NATIVE_TOOL_CONTRACT['artifacts.write'].claude_code prose both describe the two-specifier grant and the CLI behaviour that requires it"
    requirement: "QUICK-O5X"
    verification:
      - kind: unit
        ref: "tests/unit/test_native_tool_contract.py -> 9 passed (unchanged); inline gate script asserting both specifiers + WORKTREE_CONFINEMENT_NOTE appear in the contract field"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-10-30
status: complete
---

# Quick Task 261030-o5x: Fix the missing Write specifier in artifacts.write's --allowedTools grant Summary

**`allowed_tools_for()` now grants both `Write(<glob>/**)` and `Edit(<glob>/**)` for `artifacts.write`, closing a gap where the real `claude` CLI silently denied every role's first artifact write under `--permission-mode dontAsk`.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 (TDD RED -> GREEN)
- **Files modified:** 3 (1 test file, 2 production files)

## Accomplishments

- `allowed_tools_for()`'s `artifacts.write` branch now adds `Write({artifacts_glob}/**)` alongside the pre-existing `Edit({artifacts_glob}/**)` call, both built from the one caller-supplied `artifacts_glob` variable -- never a second glob expression, never a bare tool name.
- The joined `--allowedTools` argv value for a role granted only `artifacts.write` is now `Edit(<glob>/**),Write(<glob>/**)` (sorted, Edit first) -- deterministic across spawns.
- `allowed_tools_for()`'s docstring and `NATIVE_TOOL_CONTRACT['artifacts.write'].claude_code`'s `--allowedTools` example both now describe and show the two-specifier grant, explain why both are required (the CLI permission-gates its new-file and existing-file tools separately, and a role's first write to any declared output always creates a new file), and keep the `--permission-mode dontAsk` deny-by-omission rationale and the "not a bare Write/Edit grant" invariant intact.
- Added a Write-named regression test (`test_artifacts_write_grants_the_new_file_tool_not_only_the_edit_tool`) whose assertions and docstring record the real target-repository CI failure that motivated this fix, so an Edit-only regression cannot pass it silently in the future.

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: Pin the two-specifier artifacts.write grant in tests (RED)** - `593048e` (test)
2. **Task 2: Grant the new-file tool over the same glob and correct both pieces of prose (GREEN)** - `d7e2bb5` (fix)

_Note: this was a TDD task pair -- commit 1 is test-only and intentionally ends red (15 passed, 3 failed); commit 2 makes all three expectations pass with zero other change in status._

## Files Created/Modified

- `tests/unit/test_claude_code_worker.py` - Widened two existing assertions to the two-specifier shape (kept both test names unchanged per the plan's resolved-during-planning constraint) and added one new Write-named regression test with a docstring recording the live CI failure.
- `src/dark_factory/workers/claude_code.py` - `allowed_tools_for()`'s `artifacts.write` branch gained one additive `names.add(f"Write({artifacts_glob}/**)")` call; the function's docstring rewritten to describe the two-specifier grant, why both are needed, the invariant that neither name is ever emitted unscoped or broader than the other, and the `--permission-mode dontAsk` deny-by-omission rationale.
- `src/dark_factory/tools/native.py` - `NATIVE_TOOL_CONTRACT['artifacts.write'].claude_code`'s `--allowedTools` example extended to show both specifiers over the same `<run_id>`/`<role>` placeholder path, with a clause explaining the CLI's create-vs-modify permission split; the "not a bare Write/Edit grant" clause and the trailing `WORKTREE_CONFINEMENT_NOTE` interpolation both survived verbatim.

## Decisions Made

- Neither existing test (`test_allowed_tools_for_artifacts_write_is_path_scoped_not_bare`, `test_artifacts_write_grant_produces_path_scoped_edit_in_execute_argv`) was renamed. Both names are cited as validation proof refs in `.planning/milestones/v1.0-phases/07-claude-code-the-first-real-worker/07-04-SUMMARY.md` (lines 90 and 96); renaming would silently orphan a shipped validation record for zero behavioural gain. The `..._is_path_scoped_not_bare` name also remains accurate -- both specifiers are path-scoped, neither is a lone edit grant.
- The new regression test's name and assertions deliberately name `Write` specifically (not just "the grant" or "the pair"), so a future Edit-only regression fails this test by construction rather than by coincidence.
- `docs/CONFIGURATION.md` needed no change -- it lists capability names only (`artifacts.write` et al.) and never shows the `--allowedTools` specifier shape, confirmed by the planning-phase grep sweep.

## Deviations from Plan

None - plan executed exactly as written. Both tasks landed with the exact pass/fail counts predicted during planning (Task 1: 18 collected, 15 passed, 3 failed; Task 2: 18 passed / 9 passed for the two gates).

## Issues Encountered

None related to this plan's scope. Two pre-existing, unrelated conditions were observed and left untouched (out of scope per the executor's scope-boundary rule):

- `tests/unit/test_claude_code_worker.py` has 10 pre-existing mypy `--strict` errors (`Argument 2 to "resume"... incompatible type "object"; expected "WorkerResult"`) at lines unrelated to this plan's edits -- confirmed identical before and after this change via `git stash`/`git stash pop`.
- `tests/unit/test_webhook_signature.py` and two tests in `tests/unit/test_webhook_import_needs_no_database.py` / `test_unit_tier_needs_no_database.py` fail to collect/run in this environment because the `starlette` optional extra is not installed (`ModuleNotFoundError: No module named 'starlette'`) -- an environment gap, not a code defect, and outside this plan's files. A full `tests/unit` sweep (ignoring that one collection error) otherwise reported 824 passed, 1 skipped.

## User Setup Required

None - no external service configuration required.

## Follow-ups Surfaced While Reading (not in this plan's scope -- carried verbatim for the user)

These were deliberately NOT folded into this plan. Flagged here so they reach the user, as instructed:

1. **The fake CLI enforces no permissions at all, so this bug class stays undetectable.**
   `tests/support/fake_cli.py`'s generated script never reads `--allowedTools` /
   `--allow-tool`; its `_DECLARED_OUTPUTS_STEP` and `_RUN_ROOT_WRITES_STEP` write wherever
   they are told. Closing the "never caught by our own tests" gap properly means giving
   that generated script a real permission simulator -- parse the granted specifier list,
   distinguish create-new-file from modify-existing-file per target path, and refuse
   anything unmatched. That template is shared by the fake claude, copilot and hermes
   binaries, each with a different flag shape, and several existing negative proofs
   (`run_root_writes`, the write-scope violation tests) depend on the fake writing
   out-of-scope paths *successfully* -- a simulator would have to be opt-in per call site
   to avoid breaking them. That is a real piece of work with its own blast radius, not a
   small addition, so it belongs in its own task rather than here.

2. **Adjacent, already-known, same family.** STATE.md's Blockers section carries a
   Phase 10 UAT finding with the identical shape: `context_prompt_sections`'s "Expected
   outputs" prompt section tells a role to write under `artifacts/<ROLE>` while the
   permitted path requires the `.dark-factory/runs/<run-id>/` prefix, so a role must
   discover its real destination by trial and error against denials. That gap and this one
   compound -- a role fighting both gets no useful signal. Worth fixing in the same pass as
   follow-up 1, and explicitly out of scope here.

3. **Observation, unverified against the real CLI.** A role holding only `artifacts.read`
   receives a scoped Read specifier and no directory-listing or search tool scoped to the
   same subtree. Whether the real CLI needs a separately-gated listing tool to enumerate a
   prior role's outputs was not established during this planning pass and is not part of
   the reported failure. Mentioned only so it is not mistaken for a silent omission.

## Next Phase Readiness

- `ClaudeCodeWorker`'s `artifacts.write` grant is now usable against the real `claude` CLI -- every role's first artifact write under `--permission-mode dontAsk` is permitted, not silently denied.
- No blockers introduced. The three follow-up items above remain open and unassigned; follow-up 1 (fake CLI permission simulator) is the one that keeps this exact bug class invisible to the test suite until fixed in its own task.

---
*Phase: quick*
*Completed: 2026-10-30*

## Self-Check: PASSED

All claimed files found on disk (`tests/unit/test_claude_code_worker.py`,
`src/dark_factory/workers/claude_code.py`, `src/dark_factory/tools/native.py`) and both
commit hashes (`593048e`, `d7e2bb5`) found in `git log --oneline --all`.
