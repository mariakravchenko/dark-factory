---
phase: "02"
slug: "pause-resume-single-owner-execution"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-10"
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register origin: **authored at plan time** — every one of the seven Phase 2
PLAN.md files carries a `<threat_model>` block with a STRIDE register. This audit
verifies each mitigation exists in the implementation; it does not scan for new
threats. ASVS level 1, `security_block_on: high`. All 41 threats resolve
(38 mitigated with named evidence, 3 accepted with documented rationale), so the
L1 short-circuit applies (`threats_open: 0`, register authored at plan time,
asvs_level == 1) and no separate auditor pass was required. The independently
regenerated `02-VERIFICATION.md` (5/5 success criteria + 4 invariants, including
the credential boundary and redaction invariants, each tied to a passing named
test) corroborates the mitigation evidence below.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Parent process → spawned orchestrator subprocess | Child environment built from an explicit allowlist in `tests/support/subprocess_runner.py::child_env`; nothing outside it crosses | `PATH`, `HOME`, provisioned test `DATABASE_URL`, named non-secret test knobs — **no** infrastructure credential |
| Operator `argv` (`resume --answer "…"`) → orchestrator → `human_interactions.answer` → future worker prompt | Principal new untrusted-input surface for the phase; text is persisted and later fed to role context | Free-form operator text (may contain a pasted secret) |
| Worker result (`questions[]`) → orchestrator → `human_interactions.question` | Question text originates outside orchestrator control, persisted verbatim-shaped | Free-form worker text (may echo a connection string) |
| Persisted rows → structlog sink → operator terminal | Third surface a credential could reach; covered by the production redaction processor chain | JSONB event payloads, `role_executions.result`, interaction columns |
| Process A ↔ Process B, sharing only PostgreSQL | Single-owner boundary; neither process observes the other except through committed rows | `runs.owner_token` (opaque uuid4 fence), `runs.lock_expires_at` (server clock) |
| Main thread ↔ daemon heartbeat thread | Two threads, one process, each its own DB session; the lease-loss `Event` is the only shared mutable state | in-memory `Event`; per-beat `renew_lease` UPDATE |
| Alembic → PostgreSQL (DDL) | Schema change applied through the **direct**, non-pooled endpoint | `0003_pause_resume_lease` migration; no credential written to any tracked file |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-01 | Tampering | `human_interactions.status` accepting a value outside WAITING/ANSWERED/CANCELLED | medium | mitigate | Named DB `CHECK` `interaction_status` (`create_constraint=True`) in `models.py` + migration `0003`; `tests/db/test_human_interactions_schema.py` | closed |
| T-02-02 | Tampering | Two open questions for one run → answer applied to wrong question | medium | mitigate | Partial unique index `uq_one_waiting_interaction_per_run` (migration `0003`); schema test asserts 2nd WAITING rejected, 2nd ANSWERED accepted | closed |
| T-02-03 | Tampering | `lock_expires_at` written from a process clock | high | mitigate | `lease.py` uses only `func.now()` / `func.now() + timedelta(...)`; grep-proven no `datetime.now`/`utcnow`/`time.time`; invariant in `02-VERIFICATION.md` | closed |
| T-02-04 | Denial of Service | `alembic check` proposing to drop `human_interactions` every run | medium | mitigate | `_OWNED_TABLES` includes the new table; `tests/db/test_migrations.py` runs `alembic check`, fails on new upgrade ops | closed |
| T-02-05 | Denial of Service | Irreversible migration | medium | mitigate | `0003.downgrade()` reverses all four operations; migration test runs full down→up round trip | closed |
| T-02-06 | Information Disclosure | Raw connection string committed while wiring the migration | high | mitigate | `alembic.ini` `sqlalchemy.url` blank; `migrations/env.py` resolves URL from env at runtime; no new URL handling, no credential in any test file | closed |
| T-02-07 | Information Disclosure | Lifted subprocess harness widening child env, leaking a credential to a spawned orchestrator | high | mitigate | `child_env` built from explicit allowlist tuple + DB URL + named knobs only; `tests/unit/test_no_environ_copy.py` fails on any wholesale copy | closed |
| T-02-08 | Tampering | Heartbeat interval ≥ lease TTL → owner loses its own lease mid-step | high | mitigate | `Settings` `model_validator(mode="after")` rejects `lease_heartbeat_seconds >= lease_ttl_seconds` and non-positive TTL at load, naming both fields; `tests/unit/test_settings.py` | closed |
| T-02-09 | Tampering | Interaction row written outside the single mutation path | high | mitigate | `_LIFECYCLE_CTORS = {"RunEvent","RoleExecution","HumanInteraction"}` AST source-tree guard confines construction to `persistence/mutations.py`; `tests/unit/test_single_mutation_path.py` | closed |
| T-02-10 | Repudiation | Pre-declaring unused audit event types | medium | mitigate | Exactly four `EventType` members added; `tests/unit/test_domain_enums.py` pins member count at ten | closed |
| T-02-11 | Denial of Service | Test-only `FakeWorker` sleep knob left armed on a real run | low | mitigate | Env var read inside `execute` per call, never cached at import; unset ⇒ no delay; `tests/unit/test_workers.py` asserts unset case performs no delay | closed |
| T-02-12 | Information Disclosure | `application_name` label leaking deployment detail into the DB activity view | low | **accept** | Fixed literal `dark-factory`, no host/user/credential component; it is the diagnostic identity the HITL-08 proof needs. See Accepted Risks. | closed |
| T-02-13 | Tampering | Stale/killed process resurrecting after a long pause and double-writing | high | mitigate | `apply_transition(expected_owner_token=…)` compares against the row locked `FOR UPDATE`, raises `LeaseLost`, commits nothing; every in-lease call site passes the token; `tests/db/test_lease_lost_aborts_step.py` | closed |
| T-02-14 | Tampering | SQL injection via `--answer` or worker question text | high | mitigate | All statements in `lease.py`/`answers.py`/`mutations.py`/`repositories.py` use SQLAlchemy Core/ORM bound parameters; no string-built SQL; answer never reaches a shell; no `shell=True` in phase | closed |
| T-02-15 | Information Disclosure | Credential pasted into `--answer` or echoed in a question landing unredacted in DB/event/log | high | mitigate | `redact()` applied inside `_write_human_interaction` / `apply_transition` at the single mutation-path call site; AST guard confines construction; end-to-end sweep in `tests/integration/test_redaction_interactions.py` | closed |
| T-02-16 | Denial of Service | Second live process stealing an in-flight run's lease mid-step | high | mitigate | Daemon heartbeat renews expiry at TTL/3 while the worker call runs, so a competing `claim_lease` matches zero rows; `tests/integration/test_heartbeat_slow_step.py` | closed |
| T-02-17 | Denial of Service | Heartbeat that keeps renewing after the owner has logically aborted | high | mitigate | `run_lease` context-manager exit path always sets the stop `Event`, joins bounded, best-effort releases — on every path incl. exception; `tests/db/test_lease_lost_aborts_step.py` / `test_heartbeat_slow_step.py` | closed |
| T-02-18 | Elevation of Privilege | Guessing an `owner_token` to hijack a run | low | **accept** | 122-bit `uuid4` used purely as an opaque mutual-exclusion fence, not a credential; a successful guess only permits what any process may already do to a claimable run in this single-tenant local tool. See Accepted Risks. | closed |
| T-02-19 | Repudiation | Pause that persists the status change but loses one of the other four writes | high | mitigate | All five writes are arguments to one `apply_transition` inside one `with session.begin()`; `tests/integration/test_pause_exit_zero.py` asserts the block; crash-injected atomicity in `tests/db/test_pause_path_atomic.py` | closed |
| T-02-20 | Denial of Service | Unbounded `--answer` inflating a row and every downstream prompt | low | **accept** | ASVS L1, single local operator; a length bound belongs at Phase 10's GitHub-comment intake. Recorded as a decision. See Accepted Risks. | closed |
| T-02-21 | Tampering | Permissive claim predicate letting a live process steal an unexpired lease | high | mitigate | `claim_lease` conditional `UPDATE … WHERE owner_token IS NULL OR lock_expires_at < func.now()`; SC4 test asserts field-by-field the run is untouched by an early resume; 16-thread test asserts exactly one token; `tests/db/test_lease_claim_atomic.py` | closed |
| T-02-22 | Denial of Service | Restrictive claim predicate leaving a crashed owner's run permanently unclaimable | high | mitigate | SC4 test asserts reclaim succeeds once expiry passes, with both a forced expiry and a genuine short TTL; `tests/integration/test_lease_expiry_reclaim.py` | closed |
| T-02-23 | Repudiation | Race producing two role-execution rows or two ROLE_COMPLETED events | high | mitigate | Both race scenarios assert exactly one role-execution row per role/attempt and exactly one ROLE_COMPLETED; `tests/integration/test_single_owner_race.py` | closed |
| T-02-24 | Information Disclosure | New race tests' child env widening beyond the allowlist | high | mitigate | Every child spawned through `tests/support/subprocess_runner.py` allowlist builder; guarded by `tests/unit/test_no_environ_copy.py` | closed |
| T-02-25 | Denial of Service | Timing-dependent test that passes fast / hangs slow | medium | mitigate | Synchronisation by polling an observable DB condition via the shared wait helper, never a fixed sleep; every child carries a bounded timeout | closed |
| T-02-26 | Denial of Service | Long step falsely stolen because the heartbeat did not fire | high | mitigate | SC5 proof runs a step 3× its TTL, asserts expiry strictly advances ≥3×, owner token never changes, competitor fails every claim; `tests/integration/test_heartbeat_slow_step.py` | closed |
| T-02-27 | Denial of Service | Transaction held open across the worker call | high | mitigate | `_advance_once` closes the read session before the worker call, opens the write session only for the commit; `tests/integration/test_no_txn_across_worker.py` asserts zero idle-in-transaction backends during the call | closed |
| T-02-28 | Tampering | Two owners writing the same attempt, protected only by an in-memory flag | high | mitigate | Commit independently fenced on `expected_owner_token` against the `FOR UPDATE`-locked row; dedicated tests prove the flag alone and the fence alone each abort the step | closed |
| T-02-29 | Denial of Service | Heartbeat thread surviving its owner, holding the run unclaimable | high | mitigate | Lease context exit always stops/joins/releases; a test raises inside the context and asserts the run is immediately claimable | closed |
| T-02-30 | Repudiation | Partially-written aborted step leaving a role-execution row that says something happened | high | mitigate | The abort writes nothing; re-runnability test asserts same attempt number, one role-execution row, one completion event after retry | closed |
| T-02-31 | Denial of Service | Heartbeat renewals themselves becoming long-lived transactions | medium | mitigate | Each `renew_lease` opens a sub-second `with session.begin()` on its own session; activity-view sampling across the step would observe any such transaction | closed |
| T-02-32 | Information Disclosure | Credential pasted into `--answer` persisting unredacted into `answer` and a later prompt | high | mitigate | Scrubbed at the one mutation-path call site; `tests/integration/test_redaction_interactions.py` sweeps every interaction column, event payload, stored result and a real log sink, and asserts the replacement marker is present | closed |
| T-02-33 | Information Disclosure | Worker echoing a connection string inside question text | high | mitigate | Same single scrubbing call site covers `question`; the sweep includes `role_executions.result` (serialised needs-input outcome) | closed |
| T-02-34 | Tampering | Pause path that works only because the pipeline has one role | high | mitigate | `_run_current_role` branches on `signal_from_result(result)`, never a role name; `tests/db/test_pause_mechanism_generic.py` injects a two-node pipeline, asserts structurally identical outcomes | closed |
| T-02-35 | Repudiation | Half-committed pause: status says waiting, no recorded question | high | mitigate | Crash injection at each sub-write boundary of both pause and answer transitions asserting all-or-nothing and continued resumability; `tests/db/test_pause_path_atomic.py` | closed |
| T-02-36 | Tampering | Adapter producing a needs-input result with no question | medium | mitigate | Boundary model rejects it at construction; `tests/contract/test_coding_worker_contract.py` pins the guard for every present/future worker | closed |
| T-02-37 | Information Disclosure | Redaction test passing vacuously because the field was never written | medium | mitigate | Every absence assertion paired with a presence assertion (replacement marker in the stored value; lines actually reaching the log sink for the run) | closed |
| T-02-38 | Repudiation | A success-criterion proof file deleted/emptied in a later refactor, leaving the phase looking verified | high | mitigate | `tests/integration/test_phase2_acceptance.py` maps every SC and requirement id to named files, asserts each exists, is non-empty, contains tests, and is grep-proven unable to pass by skipping | closed |
| T-02-39 | Information Disclosure | Real connection string/token pasted into `.env.example` while documenting new vars | high | mitigate | The two new vars are non-secret integers documented with genuine defaults; existing entries untouched; visibly-fake-placeholder header rule restated | closed |
| T-02-40 | Tampering | Documented exit codes not matching the implementation | medium | mitigate | Exit-code section written from `cli.py` as implemented; every documented command executed once before commit so output is observed, not predicted | closed |
| T-02-41 | Repudiation | Documentation describing intended rather than shipped behaviour | medium | mitigate | Each documented command run and its actual output transcribed; production-TTL default reflects the recorded operator answer to the 02-05 human check | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` (high) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

Supply chain: no package-manager install occurs anywhere in Phase 2 (`02-RESEARCH.md` § "Package Legitimacy Audit"), so `T-02-SC` is not applicable.
External API: the deterministic detector was run over the full Phase 2 scope and returned no detection — the phase touches PostgreSQL via SQLAlchemy (existing stack), the local CLI, and the in-process fake worker. No coverage matrix required.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-12 | `application_name` is the fixed literal `dark-factory` with no host/user/credential component; it is the diagnostic identity the HITL-08 "no transaction across worker" proof relies on to distinguish this application's backends in `pg_stat_activity`. | Operator | 2026-09-10 |
| AR-02-02 | T-02-18 | `owner_token` is a 122-bit `uuid4` used only as an opaque mutual-exclusion fence, not an authentication credential. A guessed token only lets a process do what any process may already do to a claimable run in this single-tenant local tool; ASVS V3/V6 do not apply. | Operator | 2026-09-10 |
| AR-02-03 | T-02-20 | No length bound on `--answer`. ASVS L1 with a single local operator; multi-tenant answer intake (and the right place for a bound) arrives with Phase 10's GitHub comments. Recorded as a decision, not an oversight. | Operator | 2026-09-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-10 | 41 | 41 | 0 | Claude (gsd-secure-phase, L1 short-circuit — register authored at plan time, asvs_level 1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-10
