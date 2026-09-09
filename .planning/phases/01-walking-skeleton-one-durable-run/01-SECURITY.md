---
phase: "1"
slug: "walking-skeleton-one-durable-run"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on (high) severity — the blocking gate
threats_open: 0
asvs_level: 1
created: "2026-09-09"
verified: "2026-09-09"
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register = union of the `<threat_model>` blocks in `01-01-PLAN.md` … `01-09-PLAN.md`
> (`register_authored_at_plan_time: true`). Verified by `gsd-security-auditor` at ASVS L1,
> `block_on: high` — each threat checked by grep against the cited implementation file plus
> live execution of the security-guard test suites (70 guard tests + 169 unit tests green).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| PyPI → `uv` resolution → `uv.lock` | Third-party code enters the build; the only place Phase 1 installs anything | Package names + versions (supply-chain tamper surface) |
| Developer environment / `.env` → repository | A real connection string or token could be committed before any app code exists | `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN` (infrastructure credentials) |
| Test Postgres instance → test process | A provisioning route (`DARK_FACTORY_TEST_DATABASE_URL`) may carry a real credential into the test env | Connection URL with credentials |
| Operator task text → persisted `runs.normalized_task` / `run_events.payload` / `role_executions` JSONB | Arbitrary operator input reaches Neon and the audit trail | Free-form text, possibly containing credential-shaped strings |
| Worker result → orchestrator | A worker's typed output must never directly drive a lifecycle transition | `WorkerResult` (frozen, `extra="forbid"`) → `Signal` |
| CLI stdout (machine-facing) vs stderr (logs) | The `run`/`resume`/`status --json` output contract must stay parseable; logs (redacted) go to stderr | Run id + transition lines + JSON on stdout; structlog JSON on stderr |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-01-01 | Info Disclosure | redaction wired at both sinks | high | mitigate | `logging.py:55` processor after `merge_contextvars`, before `JSONRenderer`; `mutations.py` `redact()` before every `session.add`/assignment; `cli.py` redactor passed to both `status` render modes; `test_secret_redaction_e2e.py` | closed |
| T-01-02 | Tampering | SQL injection via task text | high | mitigate | `mutations.py` Core `select` w/ bound params; repo-wide grep — no f-string/`%`/concatenated SQL in `persistence/`; task text only ever a JSONB value | closed |
| T-01-03 | Info Disclosure | committed connection string | medium | mitigate | `config/settings.py` `SecretStr` fields; `alembic.ini` `sqlalchemy.url =` blank; `migrations/env.py` reads env | closed |
| T-01-04 | Repudiation | state change without its audit row | high | mitigate | `mutations.py` rejects status-change w/ empty events; single `with session.begin():`, no `session.commit()`; `test_transition_atomic.py`, `test_state_event_pairing.py` | closed |
| T-01-05 | Repudiation/Tampering | task text leaking into transition output | low | mitigate | `logging.py` `JSONRenderer`; `cli.py` transition line built from `RunStatus.value`, never task text | closed |
| T-01-06 | Tampering | worker-name branching in orchestrator | medium | mitigate | `runner.py` `registry.get(node.worker)`; `test_no_worker_name_leak.py` (exempts only `workers/`, `config/`) — executed green | closed |
| T-01-07 | Elevation of Privilege | wholesale `os.environ` copy into a worker | medium | mitigate | `test_no_environ_copy.py` — nine copy forms — executed green | closed |
| T-01-08 | Info Disclosure | `.env` / `.env.example` at repo root | medium | mitigate | `.gitignore:17`; `.env.example` all `EXAMPLE_*` placeholders; `git grep` credential-shape sweep of tracked files — only fixture tokens | closed |
| T-01-09 | Spoofing | authentication surface | low | accept | No auth surface in `src/` (grep `login`/`authenticate`/`jwt`/`oauth`: none). See Accepted Risks | closed |
| T-01-10 | Denial of Service | unbounded JSONB growth (Neon as doc store) | low | accept | `models.py` no artifact-content column (D-21); backstop `test_schema_shape.py`. See Accepted Risks | closed |
| T-01-11 | Info Disclosure | `DARK_FACTORY_TEST_DATABASE_URL` rung | medium | mitigate | `conftest.py` value read from `os.environ` only, no fixture default; pytest header renders `_RUNG_LABELS[rung]`, never the URL; tracked-file sweep clean | closed |
| T-01-12 | Tampering | silent SQLite/mock fallback | high | mitigate | `conftest.py` rung 4 = `pytest.UsageError`; zero `sqlite` in `conftest.py`/`src/`; demonstrated live — DB tier hard-stopped in the audit shell rather than degrading | closed |
| T-01-13 | Tampering | unsafe deserialization of the fake script | low | mitigate | `workers/fake.py` `json.loads` → `WorkerResult.model_validate`; no `eval`/`pickle` | closed |
| T-01-14 | Tampering | mutable `WorkerResult` driving a transition | medium | mitigate | `domain/worker.py` `frozen=True, extra="forbid"`; `domain/signal.py` reads only `result.status` | closed |
| T-01-15 | Repudiation | `NEEDS_INPUT` without its question | low | mitigate | `domain/worker.py` `model_validator` rejects `NEEDS_INPUT` w/ empty `questions` | closed |
| T-01-16 | Info Disclosure | multiple / bypassed redaction paths | high | mitigate | `logging.py` sole `structlog.configure`; `events/redaction.py` sole implementation; called at both sinks | closed |
| T-01-17 | Info Disclosure | log-capture helper masking real behavior | high | mitigate | `tests/support/log_sink.py` real `StringIO` via `configure_logging`; AST guards in `test_log_redaction.py` / `test_secret_redaction_e2e.py`; no `structlog.testing` import anywhere | closed |
| T-01-18 | Denial of Service | over-redaction destroying legit task text | medium | mitigate | `events/redaction.py` `patterns` kwarg + `scrub_known_values` (D-18 split) + `_GIT_OBJECT_CONTEXT` scoping the 40-hex heuristic. See Accepted Risks re: third-party secrets in prose | closed |
| T-01-19 | Tampering | Alembic DDL through the pooled endpoint | medium | mitigate | `migrations/env.py` resolves `DATABASE_URL_DIRECT` first and contains no `-pooler` host literal; `01-04-SUMMARY` §deviation. **Partial:** fallback chain (`DATABASE_URL_DIRECT → DATABASE_URL → DARK_FACTORY_TEST_DATABASE_URL`) has no host-shape guard, so with `DATABASE_URL_DIRECT` unset, DDL could run through PgBouncer silently. Operator-approved deviation. Cheapest full close = a Phase 2 guard rejecting a resolved `-pooler` host on the fallback rung. | open — below `high` threshold (non-blocking) |
| T-01-20 | Repudiation | event ordering derived from `created_at` | medium | mitigate | `models.py` `run_events.seq` = `BigInteger` + `sa.Identity(always=False)` + composite `(run_id, seq)` index; `test_schema_shape.py` asserts strictly increasing `seq` | closed |
| T-01-21 | Tampering | ORM ↔ migration drift | high | mitigate | `migrations/env.py` `target_metadata = Base.metadata`, `compare_type=True`; `test_migrations.py` `alembic check` gate | closed |
| T-01-22 | Tampering | a second lifecycle writer bypassing the mutation path | high | mitigate | `test_single_mutation_path.py` AST walk, allowlist `{mutations.py}` — executed green | closed |
| T-01-23 | Tampering | lost-update on a concurrent transition | medium | mitigate | `mutations.py` `with_for_update=True`; `ConcurrentTransition` raised before any write | closed |
| T-01-24 | Denial of Service | worker call inside the DB transaction | medium | mitigate | `runner.py` has zero `session.begin()`; `worker.execute` outside any transaction; `apply_transition` opens its own afterwards | closed |
| T-01-25 | Tampering | path traversal via a source locator | medium | mitigate | `input/loaders.py` `SourceNotSupportedError` before any path use; no `open`/`Path`/`read_text`; `input/resolver.py` imports no I/O module | closed |
| T-01-26 | Repudiation | run id not surfaced before work begins | medium | mitigate | `cli.py` `typer.echo(str(run_id))` immediately after `start_run`, before the drive loop | closed |
| T-01-27 | Repudiation | wrong exit code / partial persistence on bad input | medium | mitigate | `cli.py` exit 2 only in the classify/load and id-parse/unknown-run blocks, before any view; all messages `err=True` | closed |
| T-01-28 | Denial of Service | unbounded drive loop / illegal transition | medium | mitigate | `runner.py` `_MAX_DRIVE_ITERATIONS = 1000` + `DriveLoopExhausted`; `lifecycle.py` `IllegalTransitionError` on every out-of-graph pair | closed |
| T-01-29 | Elevation of Privilege | crash hook active on a real run | medium | mitigate | `runner.py` `DARK_FACTORY_CRASH_AFTER` read via `os.environ.get` inside the function (not cached), docstring marks it test-only; `test_fresh_process_resume.py` asserts single-site | closed |
| T-01-30 | Tampering | test event-listener left registered | medium | mitigate | `test_transition_atomic.py` `event.listen` / `event.remove` both inside the test body | closed |
| T-01-31 | Repudiation | resume proven only in-process | high | mitigate | `test_fresh_process_resume.py` two real `subprocess.run` processes; asserts `DARK_FACTORY_CRASH_AFTER` absent from the resume env | closed |
| T-01-32 | Tampering | read model folding the event log | high | mitigate | `observability/status.py` selects only `Run` + `RoleExecution`; `test_status_import_graph.py` transitive-closure guard — executed green | closed |
| T-01-33 | Tampering | read model acquiring the ability to write | medium | mitigate | No `session.add`/`commit`/`begin` and no attribute assignment anywhere in `observability/` | closed |
| T-01-34 | Repudiation | logs corrupting the `--json` / `run` stdout contract | medium | mitigate | `cli.py` `_route_logs_to_stderr()` before `status --json` echo; also on `run`/`resume` (WR-01 fix) | closed |
| T-01-35 | Info Disclosure | SC5 redaction proof passing by accident | high | mitigate | `test_secret_redaction_e2e.py` `COMPLETED` + `[redacted:` presence asserts run before the absence sweep | closed |
| T-01-36 | Repudiation | acceptance gate silently skipping a criterion | medium | mitigate | `test_phase_acceptance.py` explicit SC1–SC5 map + "This is a failure, not a skip"; all 8 mapped proof files resolve on disk | closed |
| T-01-SC | Tampering | slopsquat / hallucinated package into `uv.lock` | high | mitigate | `01-RESEARCH.md` § Package Legitimacy Audit (zero SLOP); `01-01-PLAN.md` `gate="blocking-human"` checkpoint performed by the operator; `uv.lock` committed (`b72cb7a`) | closed |

*Status: open · closed · open — below `high` threshold (non-blocking)*
*Only open threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`. T-01-19 is `medium` → non-blocking.*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-09 | T-01-09 | No user-authentication surface exists in Phase 1 — a single-operator local CLI. ASVS L1 V2/V3/V4 are not applicable per `01-RESEARCH.md` § "Security Domain". | plan-time disposition (`01-01-PLAN.md`) | 2026-09-09 |
| AR-01-10 | T-01-10 | Phase 1 payloads are small explicit dicts; D-21 keeps artifact content on the filesystem and out of the database by design (recorded in both the models and the `0001` revision docstring). The 100 KB `normalized_task` round-trip is a backstop assertion, not an enforced ceiling — no size limit is specified for Phase 1. | plan-time disposition (`01-04-PLAN.md`) | 2026-09-09 |
| AR-01-18 | T-01-18 | Residual after D-18: a **third-party** credential pasted into operator task prose can persist in `runs.normalized_task` (pattern redaction is deliberately not applied there, to preserve legitimate task wording). Dark Factory's **own** infrastructure credentials are still scrubbed everywhere via `scrub_known_values()` exact-substring matching against `Settings.known_secret_values()` (`mutations.py`), so the CLAUDE.md credential-boundary constraint holds. Accepted by code-review sign-off (`01-REVIEW.md` IN-01). | code-review sign-off | 2026-09-09 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-09 | 37 | 36 | 1 (T-01-19, medium — non-blocking) | gsd-security-auditor (opus), ASVS L1, block_on=high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed (no open threat at or above `high`)
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-09

---

## Carry-forward (Phase 2)

- **T-01-19** — add a host-shape guard: reject a resolved DDL URL whose host contains `-pooler` unless it came from `sqlalchemy.url` injection, or emit a loud warning on the `DATABASE_URL` fallback rung in `migrations/env.py`.
- Three plan SUMMARYs (`01-02`, `01-03`, `01-07`) omitted a `## Threat Flags` section entirely; their threats were verified directly against code and all closed, but executors should always emit the section.
