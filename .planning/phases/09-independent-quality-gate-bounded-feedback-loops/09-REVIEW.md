---
phase: 09-independent-quality-gate-bounded-feedback-loops
reviewed: 2026-09-23T00:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - .dark-factory/roles/DEVELOPMENT.yaml
  - .dark-factory/roles/QA.yaml
  - src/dark_factory/actions/builtins.py
  - src/dark_factory/config/loader.py
  - src/dark_factory/context/builder.py
  - src/dark_factory/domain/signal.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/orchestrator/lifecycle.py
  - src/dark_factory/orchestrator/quality_gate.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/workflows/pipeline.py
  - tests/db/test_artifact_schema_violation_fails_role.py
  - tests/db/test_context_builder_retry_isolation.py
  - tests/db/test_feedback_reaches_developer.py
  - tests/db/test_iteration_cap_exhaustion.py
  - tests/db/test_qa_bounce.py
  - tests/db/test_quality_gate_gates_the_run.py
  - tests/support/fake_artifacts.py
  - tests/unit/test_context_builder.py
  - tests/unit/test_domain_enums.py
  - tests/unit/test_lifecycle.py
  - tests/unit/test_quality_gate.py
findings:
  critical: 2
  warning: 1
  info: 2
  total: 5
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-09-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

This phase adds the independent quality gate (`orchestrator/quality_gate.py`) and the
bounded feedback loop (`Signal.ROLE_BOUNCED`, the two iteration counters, and
`_bounce_or_fail` in `orchestrator/runner.py`). The pure pieces (`lifecycle.transition`,
`workflows/pipeline.previous_node`, `domain/signal`, `events/catalog`,
`context/builder`'s optional-input resolution) are well-covered by unit and db tests and
hold up under adversarial reading — the cap-at-zero edge case, the idempotent-redrive
case, and the fresh-process context-rebuild proof are all real and correctly reasoned.

However, the code that dispatches the bounce/fail decision inside `_run_current_role`
(`orchestrator/runner.py`) and the new quality-gate module introduce genuine defects the
existing test suite does not exercise — every db-tier fixture in this phase uses
`write_scope: []` combined with workers that only ever write inside the gitignored
`artifacts/<role>/` tree, and no scenario configures a quality-gate command that embeds a
secret, so both gaps below have zero test coverage:

1. `enforce_write_scope` — the ROLE-05 authorization boundary this project repeatedly
   documents as load-bearing ("write_scope is an authorization control, not a formatting
   nicety") — is silently skipped whenever the terminal role's attempt resolves to
   `Signal.ROLE_BOUNCED` instead of `Signal.ROLE_COMPLETED`, because the guard clause
   written in Phase 5, before `ROLE_BOUNCED` existed, was never updated to cover the new
   signal Phase 9 introduces.
2. `run_quality_gate` persists each configured command's literal, unredacted string into
   `verification/quality_gate.json`, a file that is force-added and committed onto the
   run's working branch — while `stdout`/`stderr` from the same commands are correctly
   redacted against known secret values. A credential embedded directly in a configured
   `quality_gate.commands` entry is therefore committed to git history in the clear,
   contradicting this project's own stated hard constraint that a credential must never
   reach "workers, artifacts, prompts, event payloads, comments, logs, or reports."

Both are true regressions/gaps introduced by this phase's own new code paths, not
pre-existing conditions carried over from earlier phases.

## Critical Issues

### CR-01: `enforce_write_scope` is skipped for a bounced terminal-role attempt, letting an out-of-scope write survive uncaught

**File:** `src/dark_factory/orchestrator/runner.py:1232-1246` (guard), with the bounce
assignment at `src/dark_factory/orchestrator/runner.py:1094-1104` (QA-verdict FAIL) and
`src/dark_factory/orchestrator/runner.py:1156-1170` (quality-gate FAIL)

**Issue:** The ROLE-05 write-scope enforcement block is gated on
`if signal is Signal.ROLE_COMPLETED:`:

```python
if signal is Signal.ROLE_COMPLETED:
    write_scope = (role_def.get("permissions") or {}).get(
        "write_scope", list(DEFAULT_WRITE_SCOPE)
    )
    try:
        enforce_write_scope(work_dir, write_scope=write_scope, role=node.name, attempt=latest.attempt)
    except WriteScopeViolation as exc:
        signal = Signal.ROLE_FAILED
        outcome = {**outcome, "error": str(exc)}
        artifact_writes = []
```

This guard predates Phase 9 (it was written in Phase 5 for the schema-violation /
commit-push-failure cases, where the run genuinely terminates and there is no
"next role" for a leftover out-of-scope change to bleed into). Phase 9 adds a third way
`signal` can leave `Signal.ROLE_COMPLETED` before this line is reached:
`_bounce_or_fail` (called inside the terminal-role gate block, *above* this guard) can
set `signal = Signal.ROLE_BOUNCED`. When that happens, this block's `if` condition is
now false, so `enforce_write_scope` **never runs** for that attempt.

Unlike a `ROLE_FAILED` attempt (which ends the run — nothing downstream can be
contaminated by the un-reverted change), a `ROLE_BOUNCED` attempt sends the run back to
an earlier role (`previous_node`) for a fresh attempt. `git/diff.py::commit_run_artifacts`
only ever commits the gitignored `.dark-factory/runs/<run_id>` bookkeeping tree — it
explicitly never touches actual repository source paths. Any source-code change a role
made during its attempt is left uncommitted in the worktree until the *next* role's
`ensure_clean_worktree` before-hook runs `wip_commit_if_dirty` and folds whatever is
sitting in the worktree into a WIP-recovery commit attributed to that next role/attempt.

Concretely: QA is the shipped pipeline's terminal role, with `write_scope: ["tests/**"]`
(`.dark-factory/roles/QA.yaml:30`). If a QA worker attempt also happens to write outside
`tests/**` (e.g. under `src/**`) and that same attempt's `verdict.json` is a
schema-valid FAIL under the configured `qa_developer_max_iterations` cap, the run takes
the `Signal.ROLE_BOUNCED` path: `enforce_write_scope` is skipped, the out-of-scope
write is never detected or reverted, and it survives to be silently folded into the
Developer's *next* attempt's own WIP-recovery commit — an authorization-boundary bypass
that the audit trail cannot distinguish from a legitimate Developer change. No test in
this phase (or the codebase generally) exercises a bounce combined with a real
out-of-scope write, because every fixture worker in this phase's db tests
(`AttemptAwareFourRoleWorker`, `LazyFourRoleWorker`) only ever writes inside the
gitignored `artifacts/<role>/` subtree, so `attempt_changed_paths` is always empty
regardless of whether `enforce_write_scope` runs at all.

**Fix:** Broaden the guard to cover both signals that still represent "this attempt's
changes are about to be durably retained" — `ROLE_COMPLETED` and `ROLE_BOUNCED` — so a
bounce is checked exactly like a completion:

```python
if signal in (Signal.ROLE_COMPLETED, Signal.ROLE_BOUNCED):
    write_scope = (role_def.get("permissions") or {}).get(
        "write_scope", list(DEFAULT_WRITE_SCOPE)
    )
    try:
        enforce_write_scope(work_dir, write_scope=write_scope, role=node.name, attempt=latest.attempt)
    except WriteScopeViolation as exc:
        signal = Signal.ROLE_FAILED
        outcome = {**outcome, "error": str(exc)}
        artifact_writes = []
        counter_increments = {}
        bounce_reason = None
```

(Note the violation path must also clear `counter_increments`/`bounce_reason` — mirroring
the existing `GitError` except-block a few lines above — since a scope violation turns a
would-be bounce into a genuine `ROLE_FAILED`, and the bounce decision's side effects must
not survive that downgrade.) Add a db-tier regression test that makes the terminal role
write outside its `write_scope` on an attempt whose verdict/gate also FAILs under cap,
asserting the offending path is reverted and the run still fails cleanly rather than
bouncing with the violation intact.

### CR-02: The quality gate's persisted `command` field is never redacted, leaking a secret embedded in a configured command into a committed git artifact

**File:** `src/dark_factory/orchestrator/quality_gate.py:152-172` (specifically the
`command=command` assignment at line 165)

**Issue:** `run_quality_gate` redacts `stdout` and `stderr` against `known_secrets`
before storing them, but stores the configured `command` string itself verbatim:

```python
for command in commands:
    argv = shlex.split(command)
    outcome = shell_execute(command=argv, cwd=cwd, role=_QUALITY_GATE_ROLE_LABEL, timeout=timeout)
    stdout = _cap_output(str(redact(outcome.stdout, known_secrets=known_secrets)))
    stderr = _cap_output(str(redact(outcome.stderr, known_secrets=known_secrets)))
    results.append(
        GateCommandResult(
            command=command,          # <-- never passed through redact()
            exit_code=outcome.exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=outcome.timed_out,
        )
    )
```

`QualityGateResult` is written verbatim to `verification/quality_gate.json`
(`write_quality_gate_result`), and `orchestrator/runner.py` then force-adds and commits
that file onto the run's working branch via `commit_run_artifacts` — a durable,
git-committed, eventually PR-visible artifact. `known_secrets` (from
`Settings.known_secret_values()`) exists precisely because a secret can appear in
subprocess output; it applies equally to a secret an operator embeds directly in a
`.dark-factory.yaml` `quality_gate.commands` entry (e.g. a `curl -H "Authorization:
Bearer <token>" ...` health-check command, or any command invoking a tool via an inline
API key) — a realistic authoring pattern for a lightweight gate command. This directly
contradicts the project's own stated hard constraint (`.claude/CLAUDE.md`, "Security"):
infrastructure/worker credentials "must never reach workers, artifacts, prompts, event
payloads, comments, logs, or reports." `verification/quality_gate.json` is exactly such
an artifact/report, and once committed the secret is in git history permanently, not
just in a transient log line.

No test in `tests/unit/test_quality_gate.py` or the db-tier gate tests configures a
command whose *literal text* contains a known secret (the one redaction test,
`test_a_known_secret_value_in_stdout_is_redacted`, only checks `stdout`), so this gap has
no coverage anywhere in the suite.

**Fix:** Redact the command string the same way stdout/stderr already are, before storing
it:

```python
results.append(
    GateCommandResult(
        command=str(redact(command, known_secrets=known_secrets)),
        exit_code=outcome.exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=outcome.timed_out,
    )
)
```

Add a unit test mirroring `test_a_known_secret_value_in_stdout_is_redacted` that embeds a
known secret directly in the *configured command string* (not just its output) and
asserts it is absent from `result.commands[0].command`.

## Warnings

### WR-01: `run_quality_gate` call is not exception-safe, unlike every other post-worker step in `_run_current_role`

**File:** `src/dark_factory/orchestrator/runner.py:1110-1115`

**Issue:** Every other post-worker operation in `_run_current_role`
(`enforce_artifact_scope`, `collect_role_artifacts`, `commit_run_artifacts` /
`push_working_branch`, `enforce_write_scope`) is wrapped in a `try`/`except` that
downgrades `signal` to `Signal.ROLE_FAILED` on failure, so the role/run fails cleanly and
observably. The quality-gate call has no such wrapping:

```python
gate_result = run_quality_gate(
    commands=gate_commands,
    cwd=work_dir,
    timeout=gate_settings.worker_timeout_seconds,
    known_secrets=gate_settings.known_secret_values(),
)
```

`run_quality_gate` calls `shlex.split(command)` and then
`dark_factory.tools.env.shell_execute`, which raises `InvalidShellCommandError` for an
empty argv (a configured `quality_gate.commands` entry that is an empty string, or one
that splits to nothing) and lets `subprocess.Popen` raise `FileNotFoundError`/`OSError`
outright for a command naming a binary that doesn't exist on `PATH` — a very plausible
misconfiguration (a typo'd command, or a command that isn't installed in the run's
environment). Neither is caught anywhere in `run_quality_gate`, `run_quality_gate`'s
caller, or `_advance_once`/`advance`/`drive`. The exception propagates out of the whole
`advance()` call, crashing the driving process instead of failing the role/run.

This also breaks resumability: because the exception is raised before `apply_transition`
ever runs, the QA `role_executions` row is never updated away from its in-flight state,
so the next `advance()` call re-enters `_run_current_role` and re-invokes the worker for
the *same* attempt from scratch — silently re-running QA's own work a second time rather
than failing the run the way a schema violation or a `GitError` does.

**Fix:** Wrap the gate call the same way every sibling operation in this function is
wrapped:

```python
try:
    gate_result = run_quality_gate(
        commands=gate_commands,
        cwd=work_dir,
        timeout=gate_settings.worker_timeout_seconds,
        known_secrets=gate_settings.known_secret_values(),
    )
except (InvalidShellCommandError, OSError) as exc:
    signal = Signal.ROLE_FAILED
    outcome = {**outcome, "error": f"quality gate could not run: {exc}"}
else:
    ...  # existing PASS/FAIL handling
```

Add a unit/db test that configures an unrunnable `quality_gate.commands` entry (e.g. a
nonexistent binary) and asserts the run ends `FAILED` with a persisted error rather than
raising out of `drive()`/`advance()`.

## Info

### IN-01: `_cap_output`'s reported "dropped bytes" count is inaccurate

**File:** `src/dark_factory/orchestrator/quality_gate.py:58-72`

**Issue:** `dropped = len(encoded) - _MAX_CAPTURED_OUTPUT_BYTES` is computed from the cap
before the marker's own byte cost is subtracted from the retained budget. The actual
number of bytes dropped from the final output is `dropped + len(marker_bytes)` (a few
tens of bytes more than reported), since the marker itself consumes part of the
`_MAX_CAPTURED_OUTPUT_BYTES` budget that would otherwise have held original content. The
function's own docstring promises "an explicit marker naming the dropped byte count,"
which is technically slightly wrong.

**Fix:** Compute `dropped` after determining `budget`, e.g.
`dropped = len(encoded) - budget` once `marker_bytes`/`budget` are known, or accept the
small inaccuracy and soften the docstring's wording (e.g. "an explicit marker naming
approximately how many bytes were dropped").

### IN-02: Quality-gate skip is silent if a future terminal role doesn't declare `verdict.json` as an output

**File:** `src/dark_factory/orchestrator/runner.py:1071-1078`

**Issue:** The terminal-role gate block only runs when
`next(w for w in artifact_writes if w.type == "verdict.json")` finds a match; if it
doesn't, the block is skipped entirely with no error, no event, and the attempt proceeds
straight to `commit_run_artifacts`/transition as an ordinary `ROLE_COMPLETED`. For the
shipped pipeline this is unreachable in practice (QA's `outputs: [test_report.json,
verdict.json]` in `.dark-factory/roles/QA.yaml:57` is enforced by
`collect_role_artifacts`'s "declared output not reported fails the role" check before
this point is ever reached), but a future or user-configured pipeline whose terminal role
doesn't declare `verdict.json` would have its run reach `COMPLETED` with the independent
quality gate never having run at all, and no audit trail indicating why.

**Fix:** Consider raising or logging a structured warning when the terminal role reaches
`ROLE_COMPLETED` without a `verdict.json` in its declared outputs, so a misconfigured
pipeline fails loudly (matching this codebase's stated "fail loud, never silently paper
over" convention) rather than silently shipping a run the gate never actually verified.

---

_Reviewed: 2026-09-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
