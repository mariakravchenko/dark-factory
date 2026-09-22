---
phase: 08-copilot-hermes-worker-independence-proven
reviewed: 2026-09-22T00:00:00Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - .dark-factory/roles/ARCHITECTURE.yaml
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - src/dark_factory/config/settings.py
  - src/dark_factory/tools/env.py
  - src/dark_factory/tools/native.py
  - src/dark_factory/workers/claude_code.py
  - src/dark_factory/workers/cli_runtime.py
  - src/dark_factory/workers/copilot.py
  - src/dark_factory/workers/fake.py
  - src/dark_factory/workers/hermes.py
  - src/dark_factory/workers/registry.py
  - tests/contract/test_coding_worker_contract.py
  - tests/integration/test_claude_code_live.py
  - tests/integration/test_copilot_live.py
  - tests/integration/test_hermes_live.py
  - tests/integration/test_real_pipeline_zero_config.py
  - tests/integration/test_role_reassignment_sc2.py
  - tests/support/fake_claude_cli.py
  - tests/support/fake_cli.py
  - tests/support/fake_copilot_cli.py
  - tests/support/fake_hermes_cli.py
  - tests/support/live_runtime.py
  - tests/unit/test_claude_code_worker.py
  - tests/unit/test_copilot_worker.py
  - tests/unit/test_every_real_adapter_has_a_live_suite.py
  - tests/unit/test_fake_cli_declared_outputs.py
  - tests/unit/test_hermes_worker.py
  - tests/unit/test_native_tool_contract.py
  - tests/unit/test_worker_capabilities_match_behaviour.py
  - tests/unit/test_worker_registry_names.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-09-21
**Depth:** standard
**Files Reviewed:** 30
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

The one BLOCKER below is in the *granted* case that decision record never
examined: `artifacts.write`/`artifacts.read`, once granted to a
Hermes- or Copilot-run role, are not actually confined to that role's own
`artifacts/<role>/` subtree the way `NATIVE_TOOL_CONTRACT` and
`ClaudeCodeWorker` intend, and the fallback protection this phase's own
code cites as covering that gap (`enforce_write_scope`) provably does not
apply to that path at all, because the entire per-run tree is gitignored
and `attempt_changed_paths` explicitly (by prior, deliberate design,
A-05-15) excludes gitignored paths from its diff. This directly affects
the shipped `QA` role, which now runs on Hermes and holds
`artifacts.write`.

## Critical Issues

### CR-01: `artifacts.write`/`artifacts.read`, once granted, are unconfined for Copilot and Hermes, and the code's own claimed compensating control does not apply to that path

**File:** `src/dark_factory/tools/native.py:198-243`, `src/dark_factory/workers/copilot.py:88-110`, `src/dark_factory/workers/hermes.py:120-183`

**Issue:**

`NATIVE_TOOL_CONTRACT`'s `artifacts.write` entry states the intent
explicitly: a grant is supposed to be "a path-scoped rule specifier over
the run's own `artifacts/<role>/` subtree ... not a bare Write/Edit
grant" (`claude_code.py`'s `_TOOL_NAMES` comment says the same: the whole
point of the grant is a scope *narrower* than `repo.write`).
`ClaudeCodeWorker` honors this via `Edit(<artifacts_glob>/**)`. Neither
`CopilotWorker` nor `HermesWorker` do:

- `copilot.py`'s `_TOOL_NAMES` maps `artifacts.write` -> `("write",)` and
  `artifacts.read` -> `("read",)` -- the **identical bare, unscoped**
  tool names `repo.write`/`repo.read` use. The module's own comment
  acknowledges this (T-08-04/T-08-05, "accepted") and asserts:
  *"`enforce_write_scope` (ROLE-05) and the subprocess `cwd` remain the
  effective boundary."*
- `hermes.py` has no native narrowing mechanism for anything, by design;
  `spawn_is_permitted()` only refuses to spawn when `artifacts.write` is
  **denied** (08-02-SUMMARY.md's checkpoint record: "for the other five
  capabilities... no post-hoc control exists, so the refusal stands").
  It never addresses what happens when `artifacts.write` **is** granted.

Both of these rely, explicitly or implicitly, on `enforce_write_scope`
providing a fallback boundary. It does not, and cannot, for this path:
`.dark-factory/runs/` (which contains the entire per-run `artifacts/`
tree for every role) is listed in `.gitignore`, and
`attempt_changed_paths` (`src/dark_factory/git/scope.py:95-139`) computes
its change set from `git diff`/`git ls-files --others --exclude-standard`
-- its own docstring states plainly: *"A gitignored file the role
produced is deliberately absent: by construction it is not part of any
diff, so it is out of scope for enforcement (A-05-15)."*

Net effect: the shipped `QA` role (`.dark-factory/roles/QA.yaml`), which
now runs on `HermesWorker` and holds `artifacts.write` +
`artifacts.read`, can read or overwrite **any other role's** artifact
files in the same run -- `BA`'s `acceptance_criteria.json`,
`ARCHITECTURE`'s `design.md`, `DEVELOPMENT`'s
`implementation_summary.json` -- not just its own `artifacts/QA/`
subtree, with zero technical restriction (Hermes has no native
enforcement at all) and zero post-hoc detection (`enforce_write_scope`
never sees the change, by design). The same applies to `ARCHITECTURE`,
now running on `CopilotWorker` with `artifacts.write`/`artifacts.read`
granted. This is a real authorization gap in a project whose own
`git/scope.py` docstring states "`write_scope` is an authorization
control, not a formatting nicety" -- the same principle applies to the
`artifacts.*` capabilities, and it is not being honored for either of
this phase's two new adapters when the capability is present rather than
absent.

Separately, `NATIVE_TOOL_CONTRACT`'s prose for Copilot's `artifacts.read`
/`artifacts.write` ("a narrow `--allow-tool 'read'`/`'write'` entry,
**same scope as Claude Code**") is factually false given `copilot.py`'s
own implementation -- the contract document this project describes as
"concrete enough that Phase 7/8 implement... from" currently misrepresents
Copilot's actual enforcement posture.

**Fix:**

At minimum, correct `NATIVE_TOOL_CONTRACT`'s Copilot prose so it no
longer claims Claude-Code-equivalent scoping it does not have. For the
underlying gap, either (a) extend `enforce_write_scope` (or add a
sibling check) to also diff and revert out-of-role-subtree changes under
`.dark-factory/runs/<run_id>/artifacts/` for any capability this project
has decided needs post-hoc compensation, or (b) apply the same
"no-compensating-control -> refuse to spawn" rule `spawn_is_permitted`
already uses for `repo.read`/`repo.search`/`shell.execute` to the
*granted* case of `artifacts.write`/`artifacts.read` on Hermes and
Copilot too, until a real confinement mechanism exists -- i.e. do not
grant more filesystem reach than either adapter can actually restrict.

## Warnings

### WR-01: Role-name and attempt values are interpolated into filesystem paths with no character validation

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
`git/client.py`, and `HERMES_HOME` in particular is new code this phase.
A malformed or future user-influenced role name would silently place a
worker's config/cache/session directory outside the intended disposable
root.

**Fix:** Validate `role` (and reuse the same check everywhere a role name
becomes part of a path) against an allowlist charset (e.g.
`^[A-Za-z0-9_-]+$`) at the point it is read out of role config, or at
minimum inside `role_worker_root`/`attempt_log_paths`, raising rather
than silently building an escaping path.

### WR-02: `NATIVE_TOOL_CONTRACT`'s Copilot `artifacts.*` prose contradicts the shipped `copilot.py` implementation

**File:** `src/dark_factory/tools/native.py:208`, `:232`, `src/dark_factory/workers/copilot.py:88-110`

**Issue:** See CR-01 for the security consequence; called out again here
purely as a documentation-correctness defect, since it is independently
detectable and fixable even if CR-01's underlying enforcement gap takes
longer to close. `test_native_tool_contract.py`'s
`test_every_entry_is_complete_and_self_keyed` only checks the strings are
non-empty, so this mismatch is not caught by any existing test.

**Fix:** Update the `copilot=` prose for `artifacts.read`/`artifacts.write`
in `NATIVE_TOOL_CONTRACT` to state the actual, accepted deviation
(unscoped `--allow-tool 'read'`/`'write'`, identical breadth to
`repo.read`/`repo.write`) instead of claiming Claude-Code-equivalent path
scoping. Consider a test asserting the contract's Copilot prose and
`copilot.py`'s `_TOOL_NAMES` table cannot silently diverge on this axis.

### WR-03: `spawn_is_permitted`'s docstring and the 08-02 checkpoint record are both silent on the granted-capability enforcement gap

**File:** `src/dark_factory/workers/hermes.py:163-183`, `src/dark_factory/tools/native.py:38-59`

**Issue:** Both the module docstring and `spawn_is_permitted`'s own
docstring describe the checkpoint decision entirely in terms of *denial*
("the adapter may spawn Hermes for a role denied only this grant and let
that control hold the boundary instead"). Neither states -- and the
08-02-SUMMARY.md decision record does not appear to have considered --
what "that control" (`enforce_write_scope`) actually protects once the
capability *is* granted. For `repo.write`/`repo.write_tests` this
reasoning happens to be correct (git-tracked `src/**`/`tests/**` changes
are visible to `attempt_changed_paths`). For `artifacts.write` it is not
(see CR-01): there is no post-hoc control at all once the capability is
granted, only when it is denied.

**Fix:** Extend the design-contract prose and the 08-02 decision record
to state plainly that `artifacts.write`/`artifacts.read`, once granted to
Hermes or Copilot, carry no scope enforcement narrower than "everything
the CLI's own filesystem access can reach from `cwd`" -- so a future
reader evaluating whether to grant these to a new role on either
runtime is not misled by the "compensated" framing that legitimately
applies only to the two `repo.*` write capabilities.

## Info

### IN-01: `DEVELOPMENT.yaml` grants both `repo.write` and `artifacts.write`, making the latter's Claude Code path-scoped `Edit(...)` grant redundant

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

### WR-04: The per-run tree's `verification/`, `logs/`, and `input/` directories remain fully unenforced against tampering by any worker

**File:** `src/dark_factory/git/scope.py:157-210` (`attempt_changed_artifact_paths`'s own docstring, lines 197-200), `src/dark_factory/git/diff.py:61` (`ARTIFACT_EXCLUDE_PATHSPEC`)

**Issue:** `enforce_write_scope`'s diff excludes the entire
`.dark-factory/runs` pathspec (`ARTIFACT_EXCLUDE_PATHSPEC =
":(exclude).dark-factory/runs"`), and the new `enforce_artifact_scope`
is deliberately scoped only to the `artifacts/` subtree within that
tree -- its own docstring states explicitly: "This function never
reports a path under the same run's `verification/`, `logs/` or
`input/` directories". Any role holding `shell.execute` (or running on
an adapter, like Hermes or Copilot, whose native tools are not
worktree-subtree-scoped beyond `cwd`) can therefore overwrite
`verification/diff.patch` (the artifact Phase 9's quality gate and any
human reviewer will read as "the PR diff") or another role's captured
`logs/<role>/attempt-N.std{out,err}.log`, with zero detection by any
mechanism in this codebase -- the whole `.dark-factory/runs` tree is
gitignored, so none of it is visible to a `HEAD`-relative git diff
unless a function explicitly re-includes it the way
`attempt_changed_artifact_paths` does for `artifacts/` alone. This is
narrower than CR-01 (the highest-value target, `artifacts/`, is now
closed) but is the same class of gap CR-01 identified, left open by
design in this changeset.

**Fix:** Either extend `enforce_artifact_scope` (or add a further
sibling) to also enumerate and revert out-of-role changes under
`verification/`/`logs/`/`input/`, or, if those directories are judged
low-value enough to leave unenforced (e.g. `verification/diff.patch` is
regenerated by a trusted orchestrator action rather than the worker
itself under normal operation), state that judgment explicitly in a
docstring/decision record the way the 08-02 checkpoint did for the
`repo.write`/`repo.write_tests` narrowing, so a future reader does not
assume "the run tree is now covered" from CR-01's fix alone.

### IN-02: A multi-violation assertion in the new unit suite is weak enough to pass without proving what it claims

**File:** `tests/unit/test_artifact_scope.py:243-274` (`test_two_violating_paths_are_both_named_and_both_reverted`)

**Issue:** The test asserts `"3" in message` to prove the attempt number
(`attempt=3`) is named in the raised `ArtifactScopeViolation` message.
`run_id` is a random `uuid4()` whose canonical 32-hex-digit string
representation contains the digit `3` with very high probability on any
given test run (independent of whether `attempt=3` is actually rendered
correctly), and the violating paths embedded in the same message also
contain the run id. A regression that dropped the attempt number from
the message entirely (or rendered the wrong attempt) would very likely
still pass this assertion by coincidence, purely because `"3"` also
tends to appear somewhere inside the UUID substring already asserted
present a few lines above. This does not affect today's correctness
(the code does render the attempt correctly, confirmed by direct
reading of `enforce_artifact_scope`'s f-string), but the assertion does
not reliably guard against a future regression the way the test's own
name claims it does.

**Fix:** Assert a more specific substring that cannot be satisfied by
coincidence, e.g. `f"attempt {3}"` or the exact `f"role QA attempt 3
wrote outside"` prefix `enforce_artifact_scope` constructs, mirroring
how the same test already asserts the full path strings rather than a
single bare digit.

---

_Reviewed: 2026-09-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (incremental, wave-scoped)_
