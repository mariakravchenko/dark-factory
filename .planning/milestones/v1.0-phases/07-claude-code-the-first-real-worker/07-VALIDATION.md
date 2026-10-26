---
phase: "07"
slug: "claude-code-the-first-real-worker"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-20"
validated: "2026-09-20"
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.x [VERIFIED: pyproject.toml — `pytest>=9,<10`] |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -m unit` |
| **Full suite command** | `uv run pytest` (includes `db`/`integration`/`contract` tiers per the existing probe-ladder `conftest.py`) |
| **Estimated runtime** | ~30-60 seconds (unit tier); full suite longer with `db`/`integration` tiers |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m unit`
- **After every plan wave:** Run `uv run pytest -m "unit or contract"`
- **Before `/gsd-verify-work`:** Full suite (`uv run pytest`) must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-T1 | 01 | 1 | WORK-04 | V5/V6 | `ClaudeCodeWorker.execute()` spawns `claude` non-interactively via explicit argv list, returns normalized `WorkerResult` | unit + contract | `uv run pytest tests/unit/test_claude_code_worker.py tests/contract/test_coding_worker_contract.py -m "unit or contract"` | ✅ | ✅ green (61 passed) |
| 07-03-T2 | 03 | 2 | WORK-07 | — | `WorkerCapabilities` for `ClaudeCodeWorker` declares `native_resume=True, session_id=True` accurately | unit | `uv run pytest tests/unit/test_claude_code_worker.py -k capabilities -m unit` | ✅ `test_capabilities_reports_native_resume_and_all_expected_flags` | ✅ green (1 passed) |
| 07-03-T2 | 03 | 2 | HITL-04 | — | Resume through `worker_session_id` uses `--resume <id>`; orchestrator never inspects the id | unit (fake-`claude` asserts `--resume <id>` in observed argv) | `uv run pytest tests/unit/test_claude_code_worker.py::test_resume_uses_native_session_id -m unit` | ✅ | ✅ green (8 passed) |
| 07-03-T2 | 03 | 2 | HITL-05 | — | Identical `worker.resume(...)` call shape works when `native_resume=False` (existing `FakeWorker` behavior, unaffected) | contract | `uv run pytest tests/contract/test_coding_worker_contract.py -m contract` | ✅ existing | ✅ green (13 passed) |
| 07-03-T3 | 03 | 2 | QUAL-02 | — | Shared `CodingWorker` contract suite passes against both `FakeWorker` and `ClaudeCodeWorker` | contract | `uv run pytest tests/contract/test_coding_worker_contract.py -m contract` | ✅ `WORKER_FACTORIES = [FakeWorker, ClaudeCodeWorker]` | ✅ green (13 passed) |
| 07-02-T1/T2 | 02 | 1 | QUAL-04 | — | CI fails the build on a worker-name leak outside adapter modules | unit (guard exists) + new CI wiring | `uv run pytest tests/unit/test_no_worker_name_leak.py -m unit` | ✅ guard exists; ✅ `.github/workflows/ci.yml` added | ✅ green (2 passed) |
| 07-01-T2 | 01 | 1 | SC5 (timeout/streaming/kill) | V5 | Hung subprocess killed by process-group timeout; output streamed to `logs/<role>/`; failure persisted with captured (redacted) output | unit (fake `claude` script sleeping past an injected short timeout) | `uv run pytest tests/unit/test_claude_code_worker.py::test_timeout_kills_process_group_and_persists_output -m unit` | ✅ | ✅ green (3 passed) |
| 07-01-T3 | 01 | 1 | SEC (redaction-before-commit) | V6 | Captured subprocess transcript is redacted via `Settings.known_secret_values()` before being persisted/returned, since `git.diff.commit_run_artifacts` force-commits the whole run tree including `logs/<role>/` | unit | `uv run pytest tests/unit/test_claude_code_worker.py::test_captured_output_is_redacted -m unit` | ✅ | ✅ green (6 passed) |
| 07-04-T1 | 04 | 3 | WORK-04 | — | Spawned `claude` process receives `--allowedTools` narrowed to exactly the role's `tools:` grant | unit | `uv run pytest tests/unit/test_claude_code_worker.py -k allowed_tools -m unit` | ✅ `allowed_tools_for()` | ✅ green |
| 07-04-T2 | 04 | 3 | — | — | Native-tool contract prose names the real worktree-confinement mechanism (no false claims about unimplemented sandboxing) | unit | `uv run pytest tests/unit/test_native_tool_contract.py -m unit` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/support/` — a fake-`claude`-executable helper (script content + a `PATH`-prepending fixture reusing `build_worker_env()`'s PATH passthrough) — no existing precedent for faking an external CLI binary on PATH
- [x] `tests/unit/test_claude_code_worker.py` — the new adapter's own unit suite (argv construction, timeout/kill, redaction-before-return, `NEEDS_INPUT` marker parsing, never-raises invariant)
- [x] `tests/contract/test_coding_worker_contract.py` — append `ClaudeCodeWorker` to `WORKER_FACTORIES` (existing file, one-line addition plus whatever fixture wiring the fake binary needs)
- [x] `.github/workflows/ci.yml` (or equivalent) — this repository has **no CI workflow at all** yet; SC4 ("A CI check fails the build when a worker name appears outside the adapter modules") requires an actual CI pipeline running at least `uv run pytest -m unit`, not just a passing local test

**Wave 0 ownership (set by plan-phase):** the fake-`claude` helper and the adapter unit suite
are created inside 07-01 Task 1 (the tracer), so the tracer's own `<automated>` verify is
runnable the moment it lands. The `WORKER_FACTORIES` append is 07-03 Task 3. The CI workflow
is 07-02 Task 1, paired with `tests/unit/test_ci_enforces_worker_name_guard.py` (07-02 Task 2)
so the wiring itself is locally verifiable while the repo still has no GitHub remote.

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification (fake `claude` CLI on PATH removes the need for a real Anthropic API key in the test suite).*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated — all 9 mapped requirements COVERED, 0 gaps

---

## Validation Audit 2026-09-20

Post-execution audit (all 4 plans complete). Every requirement in the Per-Task Verification Map
was re-run against the actual command in its `Automated Command` column.

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Full `unit or contract` suite: 512 passed, 0 failed (`uv run pytest -q -m "unit or contract"`).
`db`/`integration` tiers require a reachable PostgreSQL 17 and were not run in this environment
(pre-existing infra constraint, not a Phase 7 gap — see `07-USER-SETUP.md`).
