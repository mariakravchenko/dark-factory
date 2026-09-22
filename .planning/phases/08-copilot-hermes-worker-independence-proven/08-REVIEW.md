---
phase: 08-copilot-hermes-worker-independence-proven
reviewed: 2026-09-22T00:00:00Z
depth: standard
files_reviewed: 47
files_reviewed_list:
  - .dark-factory/roles/ARCHITECTURE.yaml
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - src/dark_factory/config/loader.py
  - src/dark_factory/config/settings.py
  - src/dark_factory/git/__init__.py
  - src/dark_factory/git/scope.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/tools/env.py
  - src/dark_factory/tools/native.py
  - src/dark_factory/workers/claude_code.py
  - src/dark_factory/workers/cli_runtime.py
  - src/dark_factory/workers/copilot.py
  - src/dark_factory/workers/fake.py
  - src/dark_factory/workers/hermes.py
  - src/dark_factory/workers/registry.py
  - tests/contract/test_coding_worker_contract.py
  - tests/db/test_artifact_persistence.py
  - tests/db/test_capability_denied_fails_role.py
  - tests/db/test_four_role_pipeline.py
  - tests/integration/test_artifact_scope_enforcement.py
  - tests/integration/test_claude_code_live.py
  - tests/integration/test_copilot_live.py
  - tests/integration/test_hermes_live.py
  - tests/integration/test_phase6_acceptance.py
  - tests/integration/test_real_pipeline_zero_config.py
  - tests/integration/test_role_reassignment_sc2.py
  - tests/support/fake_artifacts.py
  - tests/support/fake_claude_cli.py
  - tests/support/fake_cli.py
  - tests/support/fake_copilot_cli.py
  - tests/support/fake_hermes_cli.py
  - tests/support/live_runtime.py
  - tests/unit/test_artifact_scope.py
  - tests/unit/test_ci_enforces_worker_name_guard.py
  - tests/unit/test_claude_code_worker.py
  - tests/unit/test_copilot_worker.py
  - tests/unit/test_every_real_adapter_has_a_live_suite.py
  - tests/unit/test_fake_cli_declared_outputs.py
  - tests/unit/test_hermes_worker.py
  - tests/unit/test_mcp_adapter.py
  - tests/unit/test_native_tool_contract.py
  - tests/unit/test_no_mcp_import_in_core.py
  - tests/unit/test_tool_registry.py
  - tests/unit/test_tool_registry_extensibility.py
  - tests/unit/test_worker_capabilities_match_behaviour.py
  - tests/unit/test_worker_registry_names.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-09-22 (three passes: initial full review, wave-scoped CR-01 re-review, this G-08-2 incremental)
**Depth:** standard
**Files Reviewed:** 47 (cumulative across all passes)
**Status:** issues_found

## Summary

This phase adds `CopilotWorker` and `HermesWorker`, extracts the shared
spawn/timeout/redact/NEEDS_INPUT pipeline into `cli_runtime.py`, and
reassigns the shipped `ARCHITECTURE`/`DEVELOPMENT`/`QA` roles onto
Copilot/Claude-Code/Hermes respectively. The credential-isolation
discipline in `tools/env.py` (`build_worker_env`, additive-from-empty
allowlist) is sound and consistently applied by all three adapters; the
`NEEDS_INPUT` extraction, timeout/process-group-kill handling, and
attempt-log redaction ordering (`scrub_log_in_place` always runs in
`finally`, before any later read of the same file) are all correct and
well covered by tests across `claude_code.py`, `copilot.py`, and
`hermes.py`. `HermesWorker.spawn_is_permitted()`'s refusal-on-denial logic
matches its own documented rule and the 08-02 checkpoint decision record
exactly for the *denied* case.

The original BLOCKER (CR-01) and its two documentation-correctness
companions (WR-02, WR-03) were closed by plan 08-05 and confirmed closed
by the 2026-09-22 wave-scoped re-review below. This third pass (this
session, plan 08-06 plus user-directed follow-on work) closes gap G-08-2
in the CR-01 test harness itself, executes the previously-never-run
DB-gated proofs for real, and fixes an unrelated test-fixture regression
(`LazyFourRoleWorker`) plus a whole-repo `ruff format` pass. No new
Critical or Warning-grade defect was introduced by this session's changes;
one new minor (Info) code-quality item was found. The four findings that
were open at the end of the prior pass (WR-01, WR-04, IN-01, IN-02) are
**untouched by this session's changes** and remain open — see "Carried-Forward
Open Findings" below.

## Critical Issues

None currently open. (CR-01, originally filed here, was closed by plan
08-05 and confirmed closed by the 2026-09-22 wave-scoped re-review — see
that section below for the full verdict.)

## Warnings

### WR-01: Role-name and attempt values are interpolated into filesystem paths with no character validation

**Status: OPEN — carried forward, not addressed by this session.**

**File:** `src/dark_factory/tools/env.py:70-79` (`role_worker_root`), `src/dark_factory/workers/hermes.py:262-283` (`role`/`HERMES_HOME`), `src/dark_factory/workers/cli_runtime.py:118-128` (`attempt_log_paths`)

**Issue:** `role_worker_root(role)` builds `tempfile.gettempdir() /
"dark-factory-worker-xdg" / role` and `attempt_log_paths` builds `root /
"logs" / role / f"attempt-{attempt}.stdout.log"` directly from the
`role` string carried on `context`, with no check that it contains no
`..`/`/` path-traversal segments. In practice `role` currently only ever
originates from `.dark-factory/roles/*.yaml`'s trusted `name:` field
(and `config/loader.py` already guards the *role-file* path against
escape), so this is low likelihood today, but `cli_runtime.py` is
explicitly documented as sharing the "credential boundary" discipline of
`git/client.py`, and `HERMES_HOME` in particular is new code from this
phase. A malformed or future user-influenced role name would silently
place a worker's config/cache/session directory outside the intended
disposable root.

This session touched `tools/env.py` and `workers/hermes.py` only for a
whole-repo `ruff format` pass (line-reflow only, verified byte-identical
under whitespace stripping); no logic in either function changed.
`cli_runtime.py` was not touched at all.

**Fix:** Validate `role` (and reuse the same check everywhere a role name
becomes part of a path) against an allowlist charset (e.g.
`^[A-Za-z0-9_-]+$`) at the point it is read out of role config, or at
minimum inside `role_worker_root`/`attempt_log_paths`, raising rather
than silently building an escaping path.

### WR-04: The per-run tree's `verification/`, `logs/`, and `input/` directories remain fully unenforced against tampering by any worker

**Status: OPEN — carried forward, not addressed by this session.**

**File:** `src/dark_factory/git/scope.py:157-210` (`attempt_changed_artifact_paths`'s own docstring, lines 197-200), `src/dark_factory/git/diff.py:61` (`ARTIFACT_EXCLUDE_PATHSPEC`)

**Issue:** `enforce_write_scope`'s diff excludes the entire
`.dark-factory/runs` pathspec (`ARTIFACT_EXCLUDE_PATHSPEC =
":(exclude).dark-factory/runs"`), and `enforce_artifact_scope` (added by
plan 08-05 to close CR-01) is deliberately scoped only to the
`artifacts/` subtree within that tree -- its own docstring states
explicitly: "This function never reports a path under the same run's
`verification/`, `logs/` or `input/` directories". Any role holding
`shell.execute` (or running on an adapter, like Hermes or Copilot, whose
native tools are not worktree-subtree-scoped beyond `cwd`) can therefore
overwrite `verification/diff.patch` (the artifact Phase 9's quality gate
and any human reviewer will read as "the PR diff") or another role's
captured `logs/<role>/attempt-N.std{out,err}.log`, with zero detection by
any mechanism in this codebase.

Neither `git/scope.py` nor `git/diff.py` is in this session's changed-file
set at all; this gap is untouched.

**Fix:** Either extend `enforce_artifact_scope` (or add a further
sibling) to also enumerate and revert out-of-role changes under
`verification/`/`logs/`/`input/`, or, if those directories are judged
low-value enough to leave unenforced, state that judgment explicitly in a
docstring/decision record the way the 08-02 checkpoint did for the
`repo.write`/`repo.write_tests` narrowing, so a future reader does not
assume "the run tree is now covered" from CR-01's fix alone.

## Info

### IN-01: `DEVELOPMENT.yaml` grants both `repo.write` and `artifacts.write`, making the latter's Claude Code path-scoped `Edit(...)` grant redundant

**Status: OPEN — carried forward, not addressed by this session.**

**File:** `.dark-factory/roles/DEVELOPMENT.yaml:13-22`

**Issue:** `DEVELOPMENT` holds both `repo.write` (unscoped
`Write,Edit` over the whole worktree, later narrowed only by
`write_scope: ["src/**"]`) and `artifacts.write` (adds a second,
narrower `Edit(.dark-factory/runs/<run_id>/artifacts/DEVELOPMENT/**)`
specifier on Claude Code). Since `repo.write` already grants the broader
access, the `artifacts.write` grant contributes nothing extra for this
role/worker combination -- harmless today, but a role-config smell that
could mask a future reviewer's expectation that `artifacts.write` is
meaningfully narrower here.

**Fix:** No functional change needed; consider a comment in
`DEVELOPMENT.yaml` noting that `artifacts.write` is redundant given
`repo.write`'s broader unscoped grant, so a future editor does not assume
removing `repo.write` alone would still let Claude Code write outputs
under `artifacts/DEVELOPMENT/`.

### IN-02: A multi-violation assertion in the new unit suite is weak enough to pass without proving what it claims

**Status: OPEN — carried forward, not addressed by this session (file not
in this session's changed-file list).**

**File:** `tests/unit/test_artifact_scope.py:243-274` (`test_two_violating_paths_are_both_named_and_both_reverted`)

**Issue:** The test asserts `"3" in message` to prove the attempt number
(`attempt=3`) is named in the raised `ArtifactScopeViolation` message.
`run_id` is a random `uuid4()` whose canonical 32-hex-digit string
representation contains the digit `3` with very high probability on any
given test run (independent of whether `attempt=3` is actually rendered
correctly), and the violating paths embedded in the same message also
contain the run id. A regression that dropped the attempt number from
the message entirely (or rendered the wrong attempt) would very likely
still pass this assertion by coincidence.

**Fix:** Assert a more specific substring that cannot be satisfied by
coincidence, e.g. `f"attempt {3}"` or the exact `f"role QA attempt 3
wrote outside"` prefix `enforce_artifact_scope` constructs, mirroring
how the same test already asserts the full path strings rather than a
single bare digit.

### IN-03: `four_role_script` is now dead code, duplicating fixture content that also lives in `LazyFourRoleWorker`'s `_FOUR_ROLE_FILES`

**Status: NEW — found this session.**

**File:** `tests/support/fake_artifacts.py:51`, `:163-273` (`four_role_script`); `tests/support/fake_artifacts.py:59-106` (`_FOUR_ROLE_FILES`)

**Issue:** This session's `LazyFourRoleWorker` fix (closing the G-08-2
follow-on defect where `four_role_script` front-loaded all four roles'
artifact files before a run started, tripping `enforce_artifact_scope`)
replaced `four_role_script` + `FakeWorker` at both of its call sites
(`tests/db/test_artifact_persistence.py`, `tests/db/test_four_role_pipeline.py`).
Confirmed by search: `four_role_script(` now has **zero** call sites
anywhere in the tracked source tree — every remaining reference to the
name is a docstring/comment, not an invocation.

`four_role_script` is still defined (`tests/support/fake_artifacts.py:163-273`,
~110 lines), still exported via `__all__`, and its four `write_role_artifacts(...)`
call bodies are a byte-for-byte duplicate of the content now also encoded
in the new `_FOUR_ROLE_FILES` module-level dict (`:59-106`), which
`LazyFourRoleWorker` reads from. No test asserts the two stay in sync. A
future edit to one (e.g. adding a fifth QA output file, or fixing a typo
in the fixture content) has no mechanism forcing the other to follow,
so the two can silently drift — at which point `four_role_script`, if
ever reintroduced or copy-pasted from, would produce content
inconsistent with what `LazyFourRoleWorker`-driven tests actually
exercise.

Both `ruff check` and `mypy --strict` pass clean on this file — neither
tool detects an unused, exported-but-uncalled module-level function, so
this was not caught by any automated gate.

**Fix:** Delete `four_role_script` (and its `__all__` entry) now that
`LazyFourRoleWorker` is the only fixture used by the codebase's db tests,
per the module's own new docstring recommendation ("Prefer it over
`four_role_script` for any db test..."). If a caller-facing reason exists
to keep both (e.g. `four_role_script` is intentionally kept as a
simpler/non-lazy alternative for a future test that doesn't drive
`enforce_artifact_scope`), derive `_FOUR_ROLE_FILES` from
`four_role_script`'s per-role dicts (or vice versa) so the content has a
single source of truth instead of two hand-maintained copies.

---

_Reviewed: 2026-09-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---

## Incremental Re-Review — 2026-09-22 (wave-scoped, CR-01 fix)

**Base of comparison:** commit `fecd6e20d788d568a57eb55822f62f2f7173292f` (the review above)
**Scope:** `src/dark_factory/git/__init__.py`, `src/dark_factory/git/scope.py`,
`src/dark_factory/orchestrator/runner.py`, `src/dark_factory/tools/native.py`,
`src/dark_factory/workers/copilot.py`, `src/dark_factory/workers/hermes.py`,
`tests/integration/test_artifact_scope_enforcement.py`,
`tests/support/fake_claude_cli.py`, `tests/support/fake_cli.py`,
`tests/support/fake_copilot_cli.py`, `tests/support/fake_hermes_cli.py`,
`tests/unit/test_artifact_scope.py`, `tests/unit/test_native_tool_contract.py`

**CR-01 verdict: CLOSED.** `enforce_artifact_scope()` (new,
`src/dark_factory/git/scope.py:374-439`) is wired into
`orchestrator/runner.py::_run_current_role` (lines 908-920)
unconditionally for every role/worker -- there is no `if worker == ...`
branch anywhere in the call path -- and it runs strictly before
`collect_role_artifacts`, `commit_run_artifacts`, and
`push_working_branch` (confirmed by reading the ordering in
`runner.py:896-981`, not just trusting the docstring). It correctly
reverts both tracked modifications/deletions (`git restore
--source=HEAD`) and newly-created foreign paths (`git clean --force -x`
via the new `revert_paths(..., include_ignored=True)` parameter), because
the run's whole `artifacts/` subtree is force-added and committed by
`commit_run_artifacts` (`git/diff.py:91-153`), which is what makes the
"tracked" branch of `attempt_changed_artifact_paths`'s `git diff
--name-only HEAD` see a later role's overwrite of an earlier role's
already-committed artifact file. Deny-by-default polarity is verified
both by direct code inspection (`allowed = []` when
`ARTIFACTS_WRITE_CAPABILITY not in granted`, then handed to the same
zero-tolerance `is_out_of_scope` D-14 relies on) and by an explicit unit
test (`test_no_artifacts_write_grant_is_zero_tolerance_for_the_roles_own_subtree`)
that proves a role's *own* subtree is not exempted when the capability
is absent. `role` is passed through `glob.escape()` before being
interpolated into the `fnmatch` pattern (`scope.py:424`), closing the
metacharacter-widening risk, and is exercised end-to-end by two real
subprocess integration tests (`test_artifact_scope_enforcement.py`) that
drive the shipped `.dark-factory/` config through fake `hermes` and
`copilot` binaries that tamper with a *different* role's committed
artifact file, plus a positive control proving the check does not
false-positive on the legitimate happy path. WR-02 and WR-03 are also
**CLOSED**: `NATIVE_TOOL_CONTRACT`'s Copilot `artifacts.*` prose no
longer claims Claude-Code-equivalent path scoping (verified both by
reading the corrected text and by the new regression test
`test_no_copilot_entry_claims_scope_equivalence_with_claude_code`, which
pins the retired claim string so it cannot silently return), and
`hermes.spawn_is_permitted`'s docstring, plus the module docstrings in
both `native.py` and `hermes.py`, now state plainly that a *granted*
`artifacts.write` is confined only after the fact by
`enforce_artifact_scope` and that a granted `artifacts.read` has no
narrowing mechanism at all -- accurately describing the shipped
behaviour, not over- or under-claiming it. No regression was found in
`enforce_write_scope`/`attempt_changed_paths`/A-05-15: both functions are
byte-for-byte unchanged, `revert_paths`'s new `include_ignored` parameter
defaults to `False` and every existing call site (`enforce_write_scope`)
is unmodified, so write-scope enforcement's existing behaviour is
untouched. The `granted` read in `runner.py` was correctly hoisted to a
single call site shared by both the new artifact-scope check and the
existing capability-gated artifact collection, eliminating the
possibility of the two computing different grant lists.

One genuine, narrower gap remains and is worth recording as a new
finding below (WR-04): the fix is deliberately scoped to the
`artifacts/` subtree only, and by its own design explicitly does not
cover the sibling `verification/`, `logs/`, and `input/` directories
inside the same gitignored per-run tree -- those remain reachable by any
worker with native filesystem/shell access and are invisible to both
`enforce_write_scope` (which excludes the whole `.dark-factory/runs`
pathspec) and the new `enforce_artifact_scope` (which is deliberately
scoped to `artifacts/` alone, per its own docstring). This is not a
regression and not part of what CR-01 promised to fix, but it is an
adjacent, currently-undetected tamper surface a reader evaluating "is
the per-run tree now safe" should know about.

(WR-04 and IN-02 filed by this pass are consolidated into the top-level
Warnings/Info sections above, marked OPEN, so the whole file has one
current status per finding rather than duplicate entries.)

---

_Reviewed: 2026-09-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (incremental, wave-scoped)_

---

## Incremental Re-Review — 2026-09-22 (G-08-2 exit-code repair + user-directed follow-on)

**Base of comparison:** commit `99e9152326c731e346f87ea8479f540548f97820` (this file's prior state)

**Scope (21 files, per plan 08-06 and its two user-directed follow-on
commits):** `tests/integration/test_artifact_scope_enforcement.py`,
`tests/support/fake_artifacts.py`, `tests/db/test_artifact_persistence.py`,
`tests/db/test_four_role_pipeline.py`, `src/dark_factory/config/loader.py`,
`src/dark_factory/tools/env.py`, `src/dark_factory/workers/claude_code.py`,
`src/dark_factory/workers/copilot.py`, `src/dark_factory/workers/hermes.py`,
`tests/db/test_capability_denied_fails_role.py`,
`tests/integration/test_phase6_acceptance.py`,
`tests/integration/test_role_reassignment_sc2.py`,
`tests/unit/test_ci_enforces_worker_name_guard.py`,
`tests/unit/test_claude_code_worker.py`, `tests/unit/test_copilot_worker.py`,
`tests/unit/test_hermes_worker.py`, `tests/unit/test_mcp_adapter.py`,
`tests/unit/test_no_mcp_import_in_core.py`, `tests/unit/test_tool_registry.py`,
`tests/unit/test_tool_registry_extensibility.py`,
`tests/unit/test_worker_capabilities_match_behaviour.py`

**Verification performed independently by this review** (not just trusting
the SUMMARY): re-ran `git diff --ignore-all-space` and a whitespace-stripped
byte comparison against the base commit for every file claimed as
"formatting-only" in 08-06-SUMMARY.md; re-ran
`uv run pytest -m integration -q tests/integration/test_artifact_scope_enforcement.py`
(3 passed) and
`uv run pytest -m db -q tests/db/test_artifact_persistence.py tests/db/test_four_role_pipeline.py tests/db/test_artifact_commit_per_role.py`
(8 passed) against a live PostgreSQL instance; re-ran `mypy`/`ruff check`/`ruff format --check`
on the files with real logic changes.

**18 of 21 files: confirmed formatting-only, no hidden logic changes.**
`src/dark_factory/config/loader.py`, `src/dark_factory/tools/env.py`,
`src/dark_factory/workers/claude_code.py`, `src/dark_factory/workers/copilot.py`,
`src/dark_factory/workers/hermes.py`, `tests/db/test_capability_denied_fails_role.py`,
`tests/integration/test_phase6_acceptance.py`, `tests/integration/test_role_reassignment_sc2.py`,
`tests/unit/test_ci_enforces_worker_name_guard.py`, `tests/unit/test_claude_code_worker.py`,
`tests/unit/test_copilot_worker.py`, `tests/unit/test_hermes_worker.py`,
`tests/unit/test_mcp_adapter.py`, `tests/unit/test_no_mcp_import_in_core.py`,
`tests/unit/test_tool_registry.py`, `tests/unit/test_tool_registry_extensibility.py`,
`tests/unit/test_worker_capabilities_match_behaviour.py` — every diff is
line-reflow (long lines joined/split by `ruff format`), string-literal
concatenation reflow, or trailing-comma insertion from multi-lining a call.
Whitespace-stripped content is byte-identical to the pre-08-06 version in
every case except the few noted, whose only non-whitespace token changes
are joining two adjacent string-literal halves back into one literal
(semantically identical) — confirmed by direct reading of each diff, not
inferred from the SUMMARY's claim.

**3 files carry real logic changes, reviewed in full:**

`tests/integration/test_artifact_scope_enforcement.py` (G-08-2 repair
itself) — `_drive_shipped_config` now takes a required keyword-only
`expected_exit: int` with no default; the harness's `assert
proc.returncode == 0` was replaced with `assert proc.returncode ==
expected_exit`; a new `_D05_SUCCESS_STATUSES = frozenset({"COMPLETED",
"WAITING_HUMAN"})` and a cross-check assert
(`(status_value in _D05_SUCCESS_STATUSES) == (expected_exit == 0)`) were
added inside the existing `Session(engine)` block; all three call sites
were updated (`expected_exit=1` for both tamper tests, `expected_exit=0`
for the positive control). Traced the cross-check logic by hand: it is
correctly biconditional (fires if either side disagrees with the other,
in both directions), placed after `status_value` is read and before the
function returns, and does not weaken any of the pre-existing assertions
in the three test bodies (confirmed line-by-line against the prior
version — the only other changes in the two tamper tests are `mypy`
narrowing (`isinstance(status_by_role, dict)` /
`isinstance(error_by_role, dict)`) added because `result` is typed
`dict[str, object]`, which is a correctness improvement, not a
weakening). Independently re-ran the 3-test integration file plus the
associated D-05 guard against a live PostgreSQL instance: passes.
`src/dark_factory/cli.py` is confirmed untouched
(`git diff --numstat 99e9152..HEAD -- src/dark_factory/cli.py` empty).

`tests/support/fake_artifacts.py`, `tests/db/test_artifact_persistence.py`,
`tests/db/test_four_role_pipeline.py` (`LazyFourRoleWorker` fix) — a new
`LazyFourRoleWorker(CodingWorker)` writes each role's fixture files from
inside `execute()`/`resume()` at call time (via a new `_FOUR_ROLE_FILES`
dict keyed by role) instead of `four_role_script` pre-staging all four
roles' files before the run starts; both affected db tests were switched
from `FakeWorker(four_role_script(run_dir))` to
`LazyFourRoleWorker(run_dir)`. Confirmed `LazyFourRoleWorker` correctly
implements all three `CodingWorker` abstract methods
(`execute`/`resume`/`capabilities`), that `resume` and `execute` are
behaviourally identical (both write the same role's files, which is
correct for a fixture whose scripted roles never actually pause), and
that the per-role file content in `_FOUR_ROLE_FILES` is a faithful,
order-preserving copy of what `four_role_script` used to write inline
(confirmed by direct text comparison, not just by the passing test
re-run). `mypy --strict`, `ruff check`, and `ruff format --check` all
pass clean on all three files (re-run independently). Independently
re-ran `tests/db/test_artifact_persistence.py`,
`tests/db/test_four_role_pipeline.py`, and the untouched
`tests/db/test_artifact_commit_per_role.py` (the file this fix's pattern
was lifted from) together against a live PostgreSQL instance: 8 passed,
matching the SUMMARY's claim.

**No new Critical or Warning-grade defect was introduced by this
session's changes.** One new Info-grade code-quality finding was found
and is filed above as **IN-03**: `four_role_script` now has zero callers
anywhere in the tracked source tree (confirmed by exhaustive grep — every
remaining reference is a comment/docstring) but was left in place,
exported, and now duplicates fixture content that also lives in the new
`_FOUR_ROLE_FILES` dict, with nothing enforcing the two stay in sync.

**Findings from the prior two passes not touched by this session's file
set — WR-01, WR-04, IN-01, IN-02 — remain OPEN**, consolidated into the
top-level Warnings/Info sections above rather than re-stated verbatim a
third time. None of this session's 21 files overlap with the specific
lines those findings cite (`cli_runtime.py`, `git/scope.py`,
`git/diff.py`, `DEVELOPMENT.yaml`, `test_artifact_scope.py` were not
touched; `tools/env.py` and `workers/hermes.py` were touched but only for
whitespace, confirmed above), so none of the four could have been
addressed incidentally.

**08-05-SUMMARY.md addendum:** reviewed the additive addendum appended by
this session (lines 261-312 as of this review) — confirmed additive only
(`git diff --numstat 99e9152..HEAD -- .planning/phases/08-copilot-hermes-worker-independence-proven/08-05-SUMMARY.md`
shows only added lines), does not edit or contradict the original D4/D5/D6
"collection-verified only" entries it appends to, and accurately
describes both the exit-code repair and the `LazyFourRoleWorker` fix. No
issue found with this file.

---

_Reviewed: 2026-09-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (incremental, G-08-2 gap closure + user-directed follow-on)_
