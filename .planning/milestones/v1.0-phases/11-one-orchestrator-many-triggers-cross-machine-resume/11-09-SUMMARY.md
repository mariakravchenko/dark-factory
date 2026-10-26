---
phase: 11-one-orchestrator-many-triggers-cross-machine-resume
plan: 09
subsystem: testing
tags: [structlog, redaction, pydantic-settings, test-infrastructure, ci, gap-closure]

requires:
  - phase: 11-one-orchestrator-many-triggers-cross-machine-resume
    provides: "plan 11-08's production-sink fix (push_token threaded into run_publish_step), which closes the other 6 of G-11-3's 12 CI failures in the same wave"
provides:
  - "real_log_sink() constructible in a database-free process, fixed once at the shared-helper layer so all current and future unit-tier callers inherit the property"
  - "tests/unit/test_clarification_comment.py's driver overrides settings for all three of _run_current_role's conditionally-taken get_settings() reads, not only the one CI reported"
  - "credential_missing() degrades to a skip instead of aborting collection when Settings cannot be constructed, closing a latent sibling defect worse than the 12 reported failures"
affects: [11-10]

actuals:
  tokens: 3471
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Only-when-absent environment override: a shared test helper supplies a fake credential value only when the real environment has none, never overriding a value a test deliberately set (preserves live-value redaction assertions)"
    - "Module-attribute settings override: monkeypatch.setattr(<module_under_test>, 'get_settings', lambda: fake_settings) patches the name the module itself resolves, covering every branch of a function in one patch rather than one override per branch"
    - "Specific-exception-only credential probes: catch pydantic's ValidationError by name, never bare Exception, so a genuine misconfiguration still fails loudly instead of silently skipping"

key-files:
  created: []
  modified:
    - tests/support/log_sink.py
    - tests/unit/test_clarification_comment.py
    - tests/support/live_runtime.py

key-decisions:
  - "Two module-local fake constants in tests/support/log_sink.py (_FAKE_DATABASE_URL / _FAKE_DATABASE_URL_DIRECT), distinct from tests/conftest.py's own _FAKE_DB_URL / _FAKE_DB_URL_DIRECT -- a different test-support layer, so the two sets of fakes cannot be mistaken for each other in a future redaction assertion"
  - "tests/unit/test_webhook_signature.py needed no edit of its own -- all five of its real-sink failures closed purely because tests/support/log_sink.py was fixed at the shared layer"
  - "_drive_needs_input threads the shared conftest fake_settings fixture (not a fourth private copy of fake credentials) into all 7 of its calling tests, patching runner_module.get_settings directly -- src/dark_factory/orchestrator/runner.py is unmodified"
  - "skip_reason() was left at exactly two arms as instructed -- no third 'settings unconstructible' reason; an unconstructible Settings is folded into credential_missing()'s existing boolean contract"

patterns-established:
  - "Pattern: a shared test-support context manager that mutates process environment must record only the keys it itself set and restore exactly those in its existing finally, never copying the environment wholesale (T-11-37)"

requirements-completed: [QUAL-01]

coverage:
  - id: D1
    description: "real_log_sink() is constructible with no DATABASE_URL/DATABASE_URL_DIRECT and no readable .env, without weakening test_log_redaction.py's live-value assertions"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "sanitized subprocess run (no DATABASE_URL/DATABASE_URL_DIRECT, fresh CWD) of tests/unit/test_webhook_signature.py + tests/unit/test_log_redaction.py + tests/unit/test_settings.py"
        status: pass
      - kind: unit
        ref: "uv run pytest -m unit tests/unit/test_log_redaction.py tests/unit/test_webhook_signature.py tests/unit/test_settings.py tests/unit/test_no_environ_copy.py (55 passed)"
        status: pass
      - kind: other
        ref: "mypy tests/support/log_sink.py; ruff check .; ruff format --check tests/support/log_sink.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "tests/unit/test_clarification_comment.py's driver overrides settings for every branch of _run_current_role it drives, via the shared fake_settings fixture, with runner.py left unmodified"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "sanitized subprocess run of tests/unit/test_clarification_comment.py (11 passed)"
        status: pass
      - kind: unit
        ref: "uv run pytest -m unit tests/unit/test_clarification_comment.py tests/unit/test_redaction.py tests/unit/test_load_github.py (84 passed)"
        status: pass
      - kind: other
        ref: "ruff check .; ruff format --check tests/unit/test_clarification_comment.py (file-scoped, since the module carries 13 pre-existing mypy --strict errors CI does not gate on)"
        status: pass
    human_judgment: false
  - id: D3
    description: "credential_missing() reports an unconstructible Settings as credential-absent, so the three live-CLI integration modules collect with exit 0 on a machine with worker binaries on PATH, instead of aborting the whole selector"
    requirement: "QUAL-01"
    verification:
      - kind: unit
        ref: "sanitized --collect-only of tests/integration/test_claude_code_live.py + test_copilot_live.py + test_hermes_live.py -- exit 0, 3 tests collected (was: Interrupted, 2 errors, 0 run)"
        status: pass
      - kind: other
        ref: "mypy tests/support/live_runtime.py; ruff check .; ruff format --check tests/support/live_runtime.py"
        status: pass
      - kind: unit
        ref: "uv run pytest -m unit tests/unit/test_worker_registry_names.py tests/unit/test_claude_code_worker.py (56 passed, 1 pre-existing unrelated failure -- see Issues Encountered)"
        status: pass
    human_judgment: true
    rationale: "The property this task fixes (an unconstructible Settings degrades to a skip rather than propagating) is proven directly by the collection exit-code check above. The deeper claim that it never regresses the normal in-process credential-configured/absent paths is formally proven by plan 11-10's guard, which collects these exact two modules with a stub worker binary on PATH -- noted here per the plan's own output instruction rather than duplicated as a new unit test."

duration: ~25min task-commits + ~10min verification wait
completed: 2026-10-02
status: complete
---

# Phase 11 Plan 09: Test-Infrastructure Gap Closure for G-11-3 (Test-Layer Sinks) Summary

**Fixed three test-support settings-construction gaps at their shared-layer source (real_log_sink only-when-absent env supply, the clarification driver's all-three-branches settings patch, and credential_missing's validation-error-to-skip fallback), closing 6 of G-11-3's 12 CI failures plus a latent collection-abort sibling with zero production-code changes.**

## Performance
- **Duration:** ~25min task-commits + ~10min verification wait (sanitized full-tier collection check, the `unit or contract` regression run at 262.95s, and a 93.40s integration-tier redaction sweep against external Neon)
- **Started:** 2026-10-02T08:17Z (approx, first task commit 11:17:45+03:00)
- **Completed:** 2026-10-02T08:34Z
- **Tasks:** 3 completed
- **Files modified:** 3

## Accomplishments
- `real_log_sink()` now supplies `DATABASE_URL`/`DATABASE_URL_DIRECT` only when the environment doesn't already have them, fixing all five `tests/unit/test_webhook_signature.py` real-sink failures with zero edits to that module, while `tests/unit/test_log_redaction.py`'s three deliberate live-value redaction assertions remain unchanged and still pass.
- `tests/unit/test_clarification_comment.py`'s `_drive_needs_input` now patches `runner_module.get_settings` with the shared `fake_settings` fixture, covering all three of `_run_current_role`'s conditionally-taken settings reads (quality-gate timeout/redaction, push-token, clarification-failure redaction) with one patch instead of the one branch CI happened to report.
- `credential_missing()` catches pydantic's `ValidationError` specifically and reports an unconstructible `Settings` as the credential being absent, turning what was a total collection abort (`Interrupted: 2 errors during collection`, 0 tests run) on any machine with a worker CLI on `PATH` into a clean skip/run per the binary-first, two-arm `skip_reason` contract — unchanged.

## Task Commits
1. **Task 1: The shared real-sink helper works in a database-free process** - `3d7f459` (fix)
2. **Task 2: The clarification driver overrides settings for every branch it drives** - `48fc416` (fix)
3. **Task 3: An unconstructible settings object is a skip, not a collection abort** - `0470db7` (fix)
**Plan metadata:** commit pending (this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md)

## Files Created/Modified
- `tests/support/log_sink.py` - `real_log_sink()` supplies two fake, greppable DB URL constants only when the corresponding env var is absent; restores env and clears the `get_settings` cache in the existing `finally`
- `tests/unit/test_clarification_comment.py` - `_drive_needs_input` (and its 7 calling tests) threads the shared `fake_settings` fixture and patches `runner_module.get_settings`; module docstring corrected
- `tests/support/live_runtime.py` - `credential_missing()` catches `pydantic.ValidationError` and reports `True` (credential absent) instead of propagating

## Decisions Made
- `tests/support/log_sink.py` gets its own fake DB-URL constants rather than importing `tests/conftest.py`'s private `_FAKE_DB_URL`/`_FAKE_DB_URL_DIRECT` across the module boundary, per the plan's explicit instruction — keeps the two test-support layers independently greppable.
- `_drive_needs_input` reuses the existing `fake_settings` conftest fixture rather than minting a fourth set of fake credentials, directly addressing the root cause's "every new test file rediscovers the requirement" condition.
- `src/dark_factory/orchestrator/runner.py` left untouched, as the plan required — no settings-reads were hoisted and no new keyword seam was added; the fix stays entirely in the test-support layer.
- `skip_reason()` left at exactly two arms (binary, credential) — no third "settings unconstructible" reason was added, per the plan's explicit instruction; an unconstructible `Settings` is folded into the existing credential-missing boolean.

## Deviations from Plan
None — plan executed exactly as written. All three tasks' `<verify>` blocks ran and passed as specified; no Rule 1-4 fixes were required beyond the plan's own prescribed changes.

## Issues Encountered
- `tests/unit/test_worker_registry_names.py::test_claude_code_resolves_to_a_real_adapter_not_a_placeholder` failed in both the Task 3 verify run and the phase-level `unit or contract` regression run: the test expects a credential-gate `FAILED` result with no `ANTHROPIC_API_KEY` configured, but this execution machine's `.env` apparently carries a real, working Anthropic credential, so `ClaudeCodeWorker.execute({})` made a genuine live API call and returned `COMPLETED`. This is unrelated to this plan's scope: the failing test imports nothing from `tests/support/live_runtime.py` (the only file Task 3 touches), the failure reproduced identically before and after this plan's changes, and `git diff --stat` confirms only `tests/support/log_sink.py`, `tests/unit/test_clarification_comment.py`, and `tests/support/live_runtime.py` were modified. Logged as a pre-existing, machine-specific environment hazard — out of scope per the deviation rules' scope boundary (not caused by this plan's changes, and not one of G-11-3's 12 reported failures). Not fixed.
- The pre-existing 183s outlier (`tests/unit/test_claude_code_worker.py::test_missing_claude_binary_returns_failed_without_raising`) reproduced exactly as the plan's measured facts predicted: 183.39s in isolation, 262.95s total for the full `unit or contract` tier (vs. the plan's measured 4m31s / 830 passed baseline — this run: 835 passed, 1 failed [the hazard above], 1 skipped, 374 deselected in 262.95s / 4m22s). Unrelated to this plan; not fixed.
- `ruff format --check .` across the whole repo reports 19 pre-existing unformatted files, none of which this plan touched (confirmed via `git diff --stat` showing exactly 3 modified files, and `ruff format --check` scoped to each of those 3 files individually passing clean). `mypy src/dark_factory` reports 2 pre-existing `mcp.server` import-not-found errors in `src/dark_factory/tools/mcp_transport.py` (the optional `mcp` extra is not installed in this environment) — this plan touches zero production files, so this is unrelated and pre-existing.

## Next Phase Readiness
- `real_log_sink`'s only-when-absent fix and `_drive_needs_input`'s all-three-branches settings patch together close 6 of G-11-3's 12 reported CI failures (the test-layer half; plan 11-08's `push_token` threading in `run_publish_step` closes the other 6, the production half, in the same wave). The 12-to-6 accounting: this plan closed all five `tests/unit/test_webhook_signature.py` real-sink failures plus `tests/unit/test_clarification_comment.py::test_raising_create_comment_still_pauses_with_no_id_recorded` (6 total); plan 11-08 closed the remaining 6 production-sink failures.
- `credential_missing`'s fix additionally closes the latent sibling defect (a sanitized full-tier collection abort on any machine with a worker CLI on `PATH`) that was not among the 12 reported failures but was measured as strictly worse during planning. Measured before: `Interrupted: 2 errors during collection`, `1 skipped, 372 deselected, 2 errors in 0.75s`. Measured after: exit code 0, 3 tests collected, 0 errors.
- Plan 11-10 (the recurrence guard) can now proceed: both the production sink (11-08) and the test-layer sinks plus the latent sibling (this plan) are closed, and its own stub-worker-binary collection proof over `tests/support/live_runtime.py` has a stable, fixed target to guard.
- The `tests/support/log_sink.py`-dependent integration-tier redaction sweep was reachable in this execution sandbox (`DARK_FACTORY_TEST_DATABASE_URL` set, external Postgres rung) and was run: `tests/integration/test_redaction_interactions.py`, `test_secret_redaction_e2e.py`, and `test_capability_denial_no_secret_leak.py` — 14 passed in 93.40s. No deferred verification needed for that rung.
- No blockers for 11-10.

## Self-Check: PASSED

- FOUND: tests/support/log_sink.py
- FOUND: tests/unit/test_clarification_comment.py
- FOUND: tests/support/live_runtime.py
- FOUND: .planning/phases/11-one-orchestrator-many-triggers-cross-machine-resume/11-09-SUMMARY.md
- FOUND: commit 3d7f459 (Task 1)
- FOUND: commit 48fc416 (Task 2)
- FOUND: commit 0470db7 (Task 3)
- FOUND: commit a7d489a (plan metadata)

---
*Phase: 11-one-orchestrator-many-triggers-cross-machine-resume*
*Completed: 2026-10-02*
