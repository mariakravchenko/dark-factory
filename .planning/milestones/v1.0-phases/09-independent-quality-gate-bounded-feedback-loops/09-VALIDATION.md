---
phase: "09"
slug: "independent-quality-gate-bounded-feedback-loops"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-22"
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (`uv run pytest`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`-equivalent `testpaths`/`markers` block) |
| **Quick run command** | `uv run python -m pytest -m "unit or contract" -q --tb=short` |
| **Full suite command** | `uv run pytest -q` (includes `db`-marked tests, which require a reachable real PostgreSQL) |
| **Estimated runtime** | ~quick unit/contract run is fast (no external services); full `db`-marked tier is materially slower (real PostgreSQL round-trips) — see Phase 08's ~260s quick / ~30min full `-m db` figures as the closest prior-phase baseline |

---

## Sampling Rate

- **After every task commit:** `uv run python -m pytest -m "unit or contract" -q --tb=short` (fast — covers `lifecycle.py`/`signal.py`/`pipeline.py` pure-function changes)
- **After every plan wave:** `uv run pytest -q` (full suite, including the new `db`-marked bounce/gate/exhaustion tests against real PostgreSQL)
- **Before `/gsd-verify-work`:** Full suite green, plus a manual/human check that a real `quality_gate.commands` failure (e.g., temporarily breaking a test) actually bounces rather than silently completing
- **Max feedback latency:** ~5 min for the standard per-task sampling loop; `db`-tier full-suite runs are reserved for wave/phase closure, not per-task sampling

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-TBD | TBD | TBD | LOOP-03, LOOP-04 | — | `transition()` correctly computes `ROLE_BOUNCED` target and rejects an out-of-range bounce | unit | `uv run pytest tests/unit/test_lifecycle.py -x -q` | ❌ W0 (extend existing file) | ⬜ pending |
| 09-TBD | TBD | TBD | GATE-01, GATE-02 | T-09-01 | Gate commands run via `shell_execute` with `shlex`-split argv; PASS iff all exit 0 | unit | `uv run pytest tests/unit/test_quality_gate.py -q` | ❌ W0 (new file) | ⬜ pending |
| 09-TBD | TBD | TBD | GATE-04 | T-09-02 | `verification/quality_gate.json` shape matches D-11 exactly (computed `status`, never hand-set) | unit + db | new unit test for the computed `status`; db test asserting the file on disk after a real `drive()` | ❌ W0 (new file) | ⬜ pending |
| 09-TBD | TBD | TBD | LOOP-01 | — | QA-FAIL bounces to Developer with a fresh attempt row; verdict issues resolvable as Developer's next input | db | `uv run pytest tests/db/test_qa_bounce.py -q` | ❌ W0 (new file, follows `tests/db/test_four_role_pipeline.py`'s idiom) | ⬜ pending |
| 09-TBD | TBD | TBD | LOOP-02 | — | Gate-FAIL bounces to Developer; gate re-runs after QA re-evaluates | db | `uv run pytest tests/db/test_quality_gate_bounce.py -q` | ❌ W0 (new file) | ⬜ pending |
| 09-TBD | TBD | TBD | LOOP-04 | — | Exhausting either iteration cap transitions the run to FAILED with full attempt history + reason persisted | db | `uv run pytest tests/db/test_iteration_cap_exhaustion.py -q` | ❌ W0 (new file) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Task IDs, plan numbers, and wave assignments are `TBD` — this table is seeded from 09-RESEARCH.md's requirement→test mapping at plan-phase time, before PLAN.md files exist. The planner must bind each row to a concrete task ID and either confirm or supersede the suggested automated command.

---

## Wave 0 Requirements

- [ ] `tests/unit/test_lifecycle.py` — extend with `Signal.ROLE_BOUNCED` legal/illegal parametrized cases (covers LOOP-03/04's transition correctness)
- [ ] `tests/unit/test_domain_enums.py` — update the `EventType` exact-count assertion (currently 12) once `QUALITY_GATE_STARTED`/`PASSED`/`FAILED` land
- [ ] `tests/support/fake_artifacts.py` — new FAIL-verdict fixture content, and a new **attempt-aware** fake worker (the current `LazyFourRoleWorker` ignores `context.attempt` and always returns identical content — it cannot simulate "fails then passes" across a bounce)
- [ ] `tests/db/test_qa_bounce.py`, `tests/db/test_quality_gate_bounce.py`, `tests/db/test_iteration_cap_exhaustion.py` — new db-tier test files; no existing file covers this behavior
- [ ] Framework install: none — pytest and all markers already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A real `quality_gate.commands` failure actually bounces the run rather than silently completing | GATE-02 | Automated tests exercise this via fakes/fixtures; a one-time human sanity check against a genuinely broken command in a real worktree catches integration gaps a fixture can hide | Temporarily break a configured gate command (e.g. introduce a failing assertion) in a real run's worktree, drive the pipeline past QA PASS, and confirm the run bounces to Developer instead of advancing — matches the precedent set by Phases 1/2's README-walkthrough-style human check |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5 min for the standard sampling loop
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

---

## Security Domain (carried from 09-RESEARCH.md)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase 9 has no auth surface |
| V3 Session Management | No | N/A |
| V4 Access Control | No | The gate is orchestrator-owned, not a role (D-01) — `ToolRegistry`/capability-grant checks (TOOL-03) don't apply to it by design |
| V5 Input Validation | Yes | `quality_gate.commands` come from `.dark-factory.yaml` (repo-controlled, trusted config, already schema-validated by `RepoConfig`) — not user/agent-controlled input. `shell_execute` avoids `shell=True` and passes an explicit argv list, so `shlex`-splitting a trusted config string introduces no shell-metacharacter injection risk |
| V6 Cryptography | No | N/A |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A malicious or buggy `quality_gate.commands` entry running with the same credential-bounded environment as role work | Elevation of Privilege (contained) | Already mitigated by the existing `build_worker_env` allowlist — `DATABASE_URL`/`GITHUB_TOKEN`/worker credentials are never in the allowlist. Confirm the gate call site reuses `shell_execute` (which threads through `build_worker_env`) rather than raw `subprocess` |
| A hung/runaway gate command (e.g. an infinite test loop) | Denial of Service | Already mitigated: `shell_execute`'s `timeout` + `os.killpg` process-group kill on `TimeoutExpired`, reused unmodified per D-10 |
| Gate command failure output (stdout/stderr) leaking a secret into `verification/quality_gate.json` or the new `run_events` payload | Information Disclosure | `apply_transition`'s `redact()` call site scrubs JSONB payloads written through it, but `verification/quality_gate.json` is a **filesystem** write outside that call site, and `read_artifact_text` performs no redaction on the way back into Developer's next `RoleContext`. **The plan must explicitly decide**: either redact `stdout`/`stderr` before writing `quality_gate.json` (reusing `dark_factory.events.redaction.redact` outside its current `mutations.py`-only call site) or explicitly accept and document this as a scoped, known risk. Do not ship this unredacted without a recorded decision either way. |

*(Full source citations for the above: see `09-RESEARCH.md` § Security Domain / Sources.)*
