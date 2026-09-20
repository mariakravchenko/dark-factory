---
phase: "07"
slug: "claude-code-the-first-real-worker"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-20"
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
| 07-01-T1 | 01 | 1 | WORK-04 | V5/V6 | `ClaudeCodeWorker.execute()` spawns `claude` non-interactively via explicit argv list, returns normalized `WorkerResult` | unit + contract | `uv run pytest tests/unit/test_claude_code_worker.py tests/contract/test_coding_worker_contract.py -m "unit or contract"` | ❌ W0 | ⬜ pending |
| 07-03-T2 | 03 | 2 | WORK-07 | — | `WorkerCapabilities` for `ClaudeCodeWorker` declares `native_resume=True, session_id=True` accurately | unit | `uv run pytest tests/unit/test_claude_code_worker.py::test_capabilities -m unit` | ❌ W0 | ⬜ pending |
| 07-03-T2 | 03 | 2 | HITL-04 | — | Resume through `worker_session_id` uses `--resume <id>`; orchestrator never inspects the id | unit (fake-`claude` asserts `--resume <id>` in observed argv) | `uv run pytest tests/unit/test_claude_code_worker.py::test_resume_uses_native_session_id -m unit` | ❌ W0 | ⬜ pending |
| 07-03-T2 | 03 | 2 | HITL-05 | — | Identical `worker.resume(...)` call shape works when `native_resume=False` (existing `FakeWorker` behavior, unaffected) | contract | `uv run pytest tests/contract/test_coding_worker_contract.py -m contract` | ✅ existing | ⬜ pending |
| 07-03-T3 | 03 | 2 | QUAL-02 | — | Shared `CodingWorker` contract suite passes against both `FakeWorker` and `ClaudeCodeWorker` | contract | `uv run pytest tests/contract/test_coding_worker_contract.py -m contract` | ⚠️ existing file, needs `ClaudeCodeWorker` appended to `WORKER_FACTORIES` | ⬜ pending |
| 07-02-T1/T2 | 02 | 1 | QUAL-04 | — | CI fails the build on a worker-name leak outside adapter modules | unit (guard exists) + new CI wiring | `uv run pytest tests/unit/test_no_worker_name_leak.py -m unit` | ✅ guard exists; ❌ no `.github/workflows/*.yml` in repo | ⬜ pending |
| 07-01-T2 | 01 | 1 | SC5 (timeout/streaming/kill) | V5 | Hung subprocess killed by process-group timeout; output streamed to `logs/<role>/`; failure persisted with captured (redacted) output | unit (fake `claude` script sleeping past an injected short timeout) | `uv run pytest tests/unit/test_claude_code_worker.py::test_timeout_kills_process_group_and_persists_output -m unit` | ❌ W0 | ⬜ pending |
| 07-01-T3 | 01 | 1 | SEC (redaction-before-commit) | V6 | Captured subprocess transcript is redacted via `Settings.known_secret_values()` before being persisted/returned, since `git.diff.commit_run_artifacts` force-commits the whole run tree including `logs/<role>/` | unit | `uv run pytest tests/unit/test_claude_code_worker.py::test_captured_output_is_redacted -m unit` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/support/` — a fake-`claude`-executable helper (script content + a `PATH`-prepending fixture reusing `build_worker_env()`'s PATH passthrough) — no existing precedent for faking an external CLI binary on PATH
- [ ] `tests/unit/test_claude_code_worker.py` — the new adapter's own unit suite (argv construction, timeout/kill, redaction-before-return, `NEEDS_INPUT` marker parsing, never-raises invariant)
- [ ] `tests/contract/test_coding_worker_contract.py` — append `ClaudeCodeWorker` to `WORKER_FACTORIES` (existing file, one-line addition plus whatever fixture wiring the fake binary needs)
- [ ] `.github/workflows/ci.yml` (or equivalent) — this repository has **no CI workflow at all** yet; SC4 ("A CI check fails the build when a worker name appears outside the adapter modules") requires an actual CI pipeline running at least `uv run pytest -m unit`, not just a passing local test

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
