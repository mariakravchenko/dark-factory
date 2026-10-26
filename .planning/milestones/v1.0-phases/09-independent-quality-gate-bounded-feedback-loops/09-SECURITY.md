---
phase: "09"
slug: "independent-quality-gate-bounded-feedback-loops"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-09-26"
---

# Phase 09 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| repo config → orchestrator subprocess | `quality_gate.commands` strings from `.dark-factory.yaml` become argv for a spawned child (`shell_execute`) | operator-authored command text |
| gate child process → persisted artifact tree | captured stdout/stderr crosses into `verification/quality_gate.json`, which is git-committed | command output, potentially secret-bearing |
| `.dark-factory.yaml` `quality_gate.commands` → persisted artifact | the command string itself is copied verbatim into a model field serialised to disk | operator config text, potentially secret-bearing |
| persisted artifact → the Developer's next `RoleContext` | `read_artifact_text` returns gate/QA output into a later role's prompt, crossing the orchestrator→worker credential boundary | gate/QA output, redacted |
| repo config → orchestrator control flow | `retry.*_max_iterations` bounds how many times the orchestrator re-dispatches a worker | operator-authored retry budget |
| concurrent processes → `runs` counter columns | two processes may attempt the same run's step; the iteration counters are mutable shared state | counter integers, row-locked |
| worker outcome → run direction | a worker's own result now indirectly influences whether the run moves backwards (bounce) | signal/counter state |
| worker attempt → repository source tree | an agent runtime writes files into the run's worktree; `write_scope` decides which writes persist | file writes, authorization-gated |
| one role's attempt → the next role's attempt | uncommitted worktree changes can survive a role transition via WIP-recovery commit | uncommitted diffs, attribution-sensitive |
| repo role config → context assembly | `optional_inputs` filenames from a role YAML select which files are read from the run tree | filenames, path-traversal-checked |
| test fixture → the run it observes (09-06) | `_CapturingWorker` executes inside the runner's own `worker.execute()` call | worktree path resolution |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-09-01 (09-01) | Elevation of Privilege | `run_quality_gate` child processes | medium | mitigate | Spawned only via `shell_execute`, whose env comes from `build_worker_env`'s allowlist (no `DATABASE_URL`/`GITHUB_TOKEN`/worker creds). Verified: zero raw `subprocess` imports in `orchestrator/quality_gate.py`. | closed |
| T-09-02 (09-01) | Denial of Service | a hung or runaway gate command | medium | mitigate | `shell_execute`'s `timeout` + `start_new_session=True` + `os.killpg`. Verified present in `actions/builtins.py`. | closed |
| T-09-03 (09-01) | Information Disclosure | gate stdout/stderr → `quality_gate.json` → committed tree → agent prompt | high | mitigate | `redact()` applied to both streams before the model is built. Verified: `redact(outcome.stdout/stderr, known_secrets=...)` present in `orchestrator/quality_gate.py`. | closed |
| T-09-04 (09-01) | Tampering | a worker planting its own `quality_gate.json` to fake a PASS | high | mitigate | Transition decision computed from the in-process `QualityGateResult`, never re-read from disk. Verified: `run_quality_gate` call feeds `gate_result` directly into transition logic in `runner.py`. | closed |
| T-09-05 (09-01) | Repudiation | a gate run leaving no auditable trace | medium | mitigate | Purpose-built `QUALITY_GATE_STARTED`/`PASSED`/`FAILED` events in the same transaction as the transition. Verified present in `events/catalog.py` and wired in `runner.py`. | closed |
| T-09-06 (09-01) | Denial of Service | unbounded gate output exceeding the artifact size cap | medium | mitigate | 16 KiB tail-preserving per-stream cap with explicit dropped-byte marker. Verified: `_cap_output` applied in `orchestrator/quality_gate.py`. Residual risk (>8 maximal-output commands) accepted and documented in-plan. | closed |
| T-09-07 (09-02) | Denial of Service | the feedback loop re-dispatching a worker forever | high | mitigate | Cap read from persisted snapshot and compared before the signal is chosen; at/over cap yields `ROLE_FAILED` never `ROLE_BOUNCED`; cap of 0 has no special case. Verified: `tests/db/test_iteration_cap_exhaustion.py` exists. | closed |
| T-09-08 (09-02) | Tampering | double-incrementing an iteration counter under a race | high | mitigate | Increment rides `apply_transition`'s `counter_increments` inside the same transaction, under the same row lock and `expected_status`/`expected_owner_token` fences. Verified: `with_for_update`, `expected_status`, `expected_owner_token` present in `persistence/mutations.py`. | closed |
| T-09-09 (09-02) | Repudiation | a bounce indistinguishable from completion or a dead run | medium | mitigate | Purpose-built `ROLE_BOUNCED` event carrying reason/counter/pre-increment value/cap, emitted alongside (never instead of) `ROLE_COMPLETED`/`ROLE_FAILED`. | closed |
| T-09-10 (09-02) | Information Disclosure | `ROLE_BOUNCED`/`RUN_FAILED` payloads carrying run detail into `run_events` | low | mitigate | Payloads carry only role name, reason token, counter name, two integers — no captured output or free text; `apply_transition` also applies `redact()` to every payload as defence in depth. | closed |
| T-09-11 (09-02) | Elevation of Privilege | repo config setting an enormous retry cap to run up cost | low | accept | `.dark-factory.yaml` is repo-controlled, already schema-validated (`ge=0`); a repo that can set this can already control worse. No upper bound added — operator owns the cost. | closed |
| T-09-12 (09-03) | Information Disclosure | gate stdout/stderr reaching the Developer's prompt / an external AI runtime | high | mitigate | Already closed upstream by T-09-03 (09-01); this task adds no second copy and no un-redaction. | closed |
| T-09-13 (09-03) | Tampering | path-traversal filename in a role's `optional_inputs` | medium | mitigate | Resolves via `resolve_under_run_root`, raising `ArtifactPathError` on absolute path, parent-escape, or symlink escape. Verified: present in `artifacts/paths.py`. | closed |
| T-09-14 (09-03) | Tampering | a worker-authored artifact injecting instructions into the next role's prompt | medium | accept | Pre-existing, out of Phase 9 scope; bounded upstream by Phase 4's T-04-19/T-04-21 identifier-extraction work. | closed |
| T-09-15 (09-03) | Denial of Service | an oversized feedback artifact stalling the loop | medium | mitigate | The 16 KiB cap (T-09-06) keeps the file well under the 262144-byte reader limit; an exceedance still raises loudly (`ArtifactTooLargeError`) rather than silently dropping feedback. | closed |
| T-09-16 (09-03) | Spoofing | `produced_by` mislabelling gate output as role-authored (or vice versa) | low | mitigate | The `"quality_gate"` producer label is set only when no role in the snapshot declares the filename as an output. Verified: `_producing_role` / `produced_by` present in `context/builder.py`. | closed |
| T-09-12 (09-04) | Elevation of Privilege | `enforce_write_scope` guard scoped only to `ROLE_COMPLETED`, bypassable via a bounce | critical | mitigate | Gap CR-01. Guard widened to cover `Signal.ROLE_COMPLETED` **and** `Signal.ROLE_BOUNCED`. Verified: `tests/unit/test_write_scope_guard_covers_bounce.py` and `tests/db/test_write_scope_enforced_on_bounce.py` both exist. | closed |
| T-09-13 (09-04) | Tampering / Repudiation | an un-reverted out-of-scope write folded into a later role's WIP commit | high | mitigate | Reverted at the violating attempt (`revert_paths`); that attempt downgrades to `ROLE_FAILED` so the change never reaches a later role. | closed |
| T-09-14 (09-04) | Denial of Service (budget) | a downgraded-to-`ROLE_FAILED` attempt still consuming a retry via a populated `counter_increments` | medium | mitigate | Violation handler clears `counter_increments` and `bounce_reason`. | closed |
| T-09-15 (09-04) | Repudiation | gate events surviving on a write-scope-downgraded path | low | accept | Deliberately not cleared — the gate run genuinely happened and is committed before the write-scope check runs; accepting reflects the true audit trail. | closed |
| T-09-16 (09-05) | Information Disclosure | `run_quality_gate`'s command-text field left unredacted | critical | mitigate | Gap CR-02. `redact(command, known_secrets=...)` applied before `GateCommandResult` is constructed. Verified: present in `orchestrator/quality_gate.py`. | closed |
| T-09-17 (09-05) | Information Disclosure | the same unredacted command string reaching a later role's prompt | high | mitigate | Redacted at construction (single choke point) — every downstream reader inherits the redacted form; no second redaction call site introduced. | closed |
| T-09-18 (09-05) | Repudiation / transparency | over-redaction making a failing command unidentifiable | low | accept | `redact` substitutes only exact ≥8-char registered secrets and narrow pattern shapes; a credential-free command round-trips byte-identically. An unidentifiable command is recoverable from repo config; a committed credential is not. | closed |
| T-09-19 (09-05) | Tampering | redaction influencing the gate's PASS/FAIL decision | low | mitigate | `QualityGateResult.status` is a `computed_field`, cannot be hand-set (`extra="forbid"`, no declared `status` field). Verified: `computed_field`/`extra="forbid"` present in `orchestrator/quality_gate.py`. | closed |
| T-09-20 (09-06) | Tampering | `ensure_worktree` newly called inside the test-fixture worker hook, mid-run | medium | mitigate | `ensure_worktree`'s same-disk-reuse path returns the existing directory with zero git invocations when `<target>/.git` exists; the runner already created that worktree before the worker ran. | closed |
| T-09-21 (09-06) | Repudiation | an unconditionally-red db-tier test mistaken for an environment problem | high | mitigate | New DB-free AST guard (`tests/unit/test_role_context_rebuild_uses_the_worktree.py`) runs on every push with no database, converting a silent environment-gated defect into a fast always-available signal. Verified: file exists, 3/3 passing this session. | closed |
| T-09-22 (09-06) | Information Disclosure | credential surfaces touched by the fix | low | accept | No credential surface touched — the change moves a `Path` value between two locals inside a test helper. | closed |
| T-09-23 (09-06) | Tampering | a "fix" that edits production code or weakens an assertion to make red go green | high | mitigate | Debug session's differential experiment pinned the fault to the test's own root argument. Verified this session: zero `src/` files changed by 09-06 (`git diff --name-only` empty). | closed |
| T-09-SC (all plans) | Tampering | npm/pip/cargo/package-manager installs | high | accept | No plan in this phase installs a package. `09-RESEARCH.md`'s Package Legitimacy Audit records "not applicable" throughout; `pyproject.toml`/`uv.lock` untouched across all six plans. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `high` (this project's `workflow.security_block_on`) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Note on ID reuse:** Plans 09-03, 09-04, and 09-05 independently reused threat IDs `T-09-12` through `T-09-16` for unrelated threats (each plan's author numbered forward from what they believed was the last-used ID, without cross-checking sibling plans). This is a documentation bookkeeping gap, not a security gap — every entry above is individually verified regardless of its ID. Disambiguated here by originating plan; a future phase should number threat IDs from a single running counter across all of a phase's plans.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-09-01 | T-09-11 | Repo-controlled retry-cap config; operator who owns the repo owns the cost; no worse than existing `workflow.roles`/`quality_gate.commands` trust | plan author (09-02) | 2026-09-23 |
| R-09-02 | T-09-14 (09-03) | Prompt-injection-via-artifact-content is pre-existing and out of Phase 9 scope; bounded upstream by Phase 4 | plan author (09-03) | 2026-09-23 |
| R-09-03 | T-09-15 (09-04) | Gate events on a downgraded path reflect a real, already-committed gate run — accepting is the accurate audit trail, not a gap | plan author (09-04) | 2026-09-23 |
| R-09-04 | T-09-18 | Over-redaction residual: an unidentifiable command is recoverable from repo config; a committed credential is not | plan author (09-05) | 2026-09-23 |
| R-09-05 | T-09-22 | No credential surface touched by the 09-06 test-fixture fix | plan author (09-06) | 2026-09-26 |
| R-09-06 | T-09-SC | No package installs anywhere in this phase | plan authors (all) | 2026-09-23/26 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-26 | 29 (28 distinct + 5 duplicate T-09-SC collapsed to 1) | 29 | 0 | /gsd-secure-phase (grep-level, ASVS L1; register authored at plan time across all 6 plans) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-26
