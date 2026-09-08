---
phase: 01-walking-skeleton-one-durable-run
reviewed: 2026-09-08T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - src/dark_factory/cli.py
  - src/dark_factory/__main__.py
  - src/dark_factory/config/settings.py
  - src/dark_factory/domain/signal.py
  - src/dark_factory/domain/status.py
  - src/dark_factory/domain/task.py
  - src/dark_factory/domain/views.py
  - src/dark_factory/domain/worker.py
  - src/dark_factory/events/catalog.py
  - src/dark_factory/events/redaction.py
  - src/dark_factory/input/loaders.py
  - src/dark_factory/input/resolver.py
  - src/dark_factory/logging.py
  - src/dark_factory/observability/status.py
  - src/dark_factory/orchestrator/lifecycle.py
  - src/dark_factory/orchestrator/runner.py
  - src/dark_factory/persistence/engine.py
  - src/dark_factory/persistence/models.py
  - src/dark_factory/persistence/mutations.py
  - src/dark_factory/persistence/repositories.py
  - src/dark_factory/roles/registry.py
  - src/dark_factory/workers/base.py
  - src/dark_factory/workers/fake.py
  - src/dark_factory/workers/registry.py
  - src/dark_factory/workflows/pipeline.py
  - migrations/env.py
  - migrations/versions/0001_walking_skeleton.py
findings:
  critical: 0
  warning: 8
  info: 9
  total: 17
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-09-08
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

The walking skeleton is well-factored and the two reachable paths in Phase 1 (happy
path `CREATED -> BA -> COMPLETED` and failure arm `CREATED -> BA -> FAILED`) are
correct. Session lifetimes are disciplined (fresh session per mutation, `finally:
close()` on every read), the single-mutation-path contract holds, the pure
`transition()` takes no `Session`, the read model imports nothing from
`dark_factory.events`, migration `0001` is symmetric with the ORM models, and no
`shell=True` / `os.environ.copy()` appears (Phase 1 spawns no subprocess).

No BLOCKER-class defect was found: nothing in the code as shipped produces an
incorrect persisted state, a crash mid-transaction, or an active credential leak.

The warnings cluster in three areas, all of which touch stated project invariants
and should be fixed before Phase 2 code lands on top of them:

1. **The structlog redaction processor is never installed on the `run` / `resume`
   paths.** No leak today because those paths emit zero log lines, but the
   credential-boundary invariant is one `log.info()` away from being violated, and
   unconfigured structlog also writes to stdout, which would corrupt the parseable
   `run` output contract.
2. **Redaction regex gaps** for bare 40-hex PATs, DB URIs with special-character
   passwords, and base64 bearer tokens — exact-value scrubbing covers the
   *configured* secrets, but the pattern table is the only defense for third-party
   credentials that appear in worker output.
3. **Two pieces of logic silently assume a single-role pipeline** (`RUN_COMPLETED`
   emitted unconditionally on any role completion; "latest execution" resolved by
   `MAX(attempt)` which stops being "most recent" once every role starts at
   attempt 1). Both directly contradict the "never encode a role count" directive
   in `workflows/pipeline.py` and both break in Phase 4, which is one phase away.

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review. No structural
pre-pass substrate to incorporate.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: structlog redaction processor is never wired on the `run` / `resume` code paths

**File:** `src/dark_factory/cli.py:68-92` (and `src/dark_factory/logging.py:33-53`)
**Issue:** `configure_logging()` is only ever called from `_route_logs_to_stderr()`
(`cli.py:95-99`), which runs *exclusively* in the `status --json` branch
(`cli.py:130-131`). The `run` and `resume` commands — the primary lifecycle
drivers — execute with structlog in its library-default configuration, which has
**no `_redaction_processor`** and renders to **stdout**. `advance()` already binds
`run_id` / `role` / `attempt` via `bind_contextvars` (`runner.py:206`), so the
infrastructure to emit context-bearing log lines is in place; the first
`structlog.get_logger().info(...)` added anywhere on the advance path in Phase 2+
will (a) bypass `redact()` entirely — a direct violation of the CLAUDE.md
"credentials must never reach logs" invariant — and (b) interleave JSON/console
output into the `run` stdout stream that Plans 07-09 parse for the run id and the
`PREVIOUS -> NEXT` lines.
**Fix:** Call `configure_logging()` once at the top of both `run` and `resume`
(and route it to stderr the same way `status --json` does, so stdout stays a clean
contract stream):
```python
@app.command()
def run(source: str) -> None:
    _route_logs_to_stderr()
    try:
        run_id = start_run(source)
    ...
```
Consider installing it in a Typer `@app.callback()` so every subcommand is covered
by construction.

### WR-02: `LOG_LEVEL` setting is dead — `configure_logging` hardcodes `logging.INFO`

**File:** `src/dark_factory/logging.py:48` (field declared at `src/dark_factory/config/settings.py:42`)
**Issue:** `Settings.log_level` exists for exactly one purpose — to drive the
structlog level filter — but `configure_logging()` passes
`structlog.make_filtering_bound_logger(logging.INFO)` with a literal. Setting
`LOG_LEVEL=DEBUG` or `LOG_LEVEL=WARNING` in the environment / `.env` has no effect.
An operator debugging a stuck resume cannot raise verbosity.
**Fix:**
```python
import logging
_level = logging.getLevelNamesMapping().get(
    get_settings().log_level.upper(), logging.INFO
)
structlog.configure(
    ...
    wrapper_class=structlog.make_filtering_bound_logger(_level),
    ...
)
```
Validate the string in `Settings` (a `field_validator` or `Literal[...]`) so a
typo fails loudly rather than silently falling back to INFO.

### WR-03: `RUN_COMPLETED` event is emitted on *every* role completion, not only on run completion

**File:** `src/dark_factory/orchestrator/runner.py:278-284`
**Issue:** In `_run_current_role`, the `signal is Signal.ROLE_COMPLETED` branch
unconditionally appends `EventWrite(type=EventType.RUN_COMPLETED, ...)` alongside
`ROLE_COMPLETED`, without checking `next_status`. `transition()` only returns
`RunStatus.COMPLETED` when the completed role is the *last* node
(`lifecycle.py:88-96`); for any earlier role it returns the next role status. This
is correct in Phase 1 only because `DEFAULT_PIPELINE` has length 1, so "role
completed" always equals "run completed". The moment Phase 4 adds Architect /
Developer / QA, completing BA will write a false `RUN_COMPLETED` audit row while
the run continues. This is precisely the "encode a role count / assume exactly one
entry" hazard `workflows/pipeline.py:1-7` warns against.
**Fix:** Gate the terminal event on the computed next status:
```python
events = [
    EventWrite(type=EventType.ROLE_COMPLETED,
               payload={"role": node.name, "summary": result.summary}),
]
if next_status is RunStatus.COMPLETED:
    events.append(EventWrite(type=EventType.RUN_COMPLETED,
                             payload={"role": node.name}))
```

### WR-04: "latest execution" is resolved by `MAX(attempt)`, which is not "most recent" once a pipeline has more than one role

**File:** `src/dark_factory/persistence/repositories.py:95-99` and `src/dark_factory/observability/status.py:69-74`
**Issue:** Both read paths select the "single latest `role_executions` row" with
`ORDER BY attempt DESC LIMIT 1`. `attempt` restarts at 1 for each role
(`models.py:120-122`, and `_write_role_execution` computes `MAX(attempt)+1`
*scoped to `run_id` AND `role`*, `mutations.py:245-250`). With a multi-role
pipeline, BA attempt 1, Architect attempt 1, Developer attempt 1 all tie at
`attempt = 1`, and `LIMIT 1` returns an arbitrary row — so `RunState.current_role`
disagreement aside, `latest_execution` / `latest_attempt` become nondeterministic.
`load_run_state` feeds `advance()`'s resume reconstruction, so this is
resume-correctness, not just display. The docstrings ("the single latest
`role_executions` row", `repositories.py:20-22`) assert a guarantee the query does
not provide.
**Fix:** Add a deterministic tiebreaker that does not depend on cross-machine wall
clock. Ordering by the run's own progress is safest — e.g. join/filter to
`current_role`, or add a monotonic per-run `role_executions.seq` identity column
(same pattern as `run_events.seq`) and `ORDER BY seq DESC`. At minimum, for
Phase 1, document that this holds only while the pipeline has one role and add the
tiebreaker before Phase 4.

### WR-05: `FakeWorker` script position does not advance across `advance()` calls — multi-result scripts silently always yield element 0

**File:** `src/dark_factory/workers/fake.py:53-71`, `src/dark_factory/workers/registry.py:34` + `:38`, consumed at `src/dark_factory/orchestrator/runner.py:268`
**Issue:** `default_registry.register("fake", FakeWorker)` registers the **class**;
`WorkerRegistry.get()` returns `factory()`, i.e. a **fresh `FakeWorker`** on every
call. `_run_current_role` calls `registry.get(node.worker)` inside each `advance()`,
so `self._index` is reset to `0` every step and `execute()` always returns
`self._script[0]`. `FakeWorker`'s own docstring ("Returns a fixed sequence of
`WorkerResult`s, one per `execute()` call") and the `ScriptExhaustedError`
machinery imply sequential consumption across the lifecycle. Harmless in Phase 1
(one role, one `execute` per run) but it means a `DARK_FACTORY_FAKE_SCRIPT` with
two entries — the natural way to script "NEEDS_INPUT then COMPLETED" for the
Phase 2 resume tests — will replay entry 0 forever and never exhaust. This will
produce confusing green-then-broken behavior across the phase boundary.
**Fix:** Register a single long-lived instance as the factory
(`default_registry.register("fake", lambda _inst=FakeWorker(): _inst)`), or have
`WorkerRegistry` cache instances, or make `FakeWorker` resolve its cursor from a
persisted/worker-session-keyed position rather than instance state. Document the
chosen semantics.

### WR-06: redaction pattern table misses bare 40-hex PATs and mangles some real secret shapes

**File:** `src/dark_factory/events/redaction.py:61-89`
**Issue:** Several gaps in the D-15 pattern table, which is the only scrub for
credentials that are *not* the configured `DATABASE_URL` / `GITHUB_TOKEN` (e.g. a
third-party token echoed in a `WorkerResult.summary`, which is dumped into
`run_events.payload` and `role_executions.result`):
1. **Bare 40-hex classic PAT (rule 3c, lines 71-76):** only redacted when the
   literal substring `github` appears within 40 chars before the hex. A 40-hex
   token in prose like `"auth failed with 0123...cdef"` or `"key: <40hex>"`
   (space-separated, so rule 2's `[:=]` does not match either) is persisted
   verbatim. The task prompt explicitly lists "40-hex PAT" as a required catch.
2. **DB URI (rule 1, lines 63-66):** password is `[^\s:/@]+`, so a connection
   string whose password contains a raw `/`, `@` or `:` (unencoded) fails to match
   and the whole URI leaks. Neon passwords are usually alphanumeric, and
   exact-value scrubbing covers the configured URL, but the pattern is brittle for
   any other embedded-credential URI.
3. **`Authorization: Bearer` (rule 4, lines 78-81):** token class
   `[A-Za-z0-9._\-]+` excludes standard-base64 `+`, `/`, `=`, so a base64 bearer
   value is only partially redacted, leaving a trailing fragment in the sink.
**Fix:** Add an unconditional 40-hex rule that excludes obvious git SHA contexts
by *key* rather than proximity (e.g. redact 40/64-hex only when it is a standalone
token not preceded by `commit`/`sha`/`revision`), widen the bearer token class to
`[A-Za-z0-9._\-+/=]+`, and for URIs fall back to redacting `://.*@` whenever a
`postgres`/`postgresql` scheme is present. Keep the exact-value pass as the
primary guarantee and treat patterns as belt-and-suspenders — but close the
enumerated gaps the phase brief calls out.

### WR-07: orchestration exceptions surface as raw tracebacks with exit code 1, colliding with the "1 = persisted FAILED" contract

**File:** `src/dark_factory/cli.py:62-65` (`_drive_and_exit`), reachable from `src/dark_factory/orchestrator/lifecycle.py:101` and `src/dark_factory/orchestrator/runner.py:271`
**Issue:** `_drive_and_exit` calls `drive()` with no exception handling.
`ConcurrentTransition`, `IllegalTransitionError`, `DriveLoopExhausted`,
`RunNotFoundError` and `ScriptExhaustedError` all propagate out as uncaught
exceptions; Typer prints a traceback and exits **1**. Per the documented contract
(`cli.py:15-17`) exit 1 means "a persisted FAILED" — an operator scripting against
that contract will read exit 1 and believe the run failed and was recorded, when
in fact nothing was persisted and the run is stranded mid-role (status `BA`,
`role_executions.status = "RUNNING"`, no `RUN_FAILED` event). The most reachable
case in Phase 1: a scripted `WorkerResult(status=NEEDS_INPUT, questions=[...])` is
a *valid* model instance (`domain/worker.py:69-75`), and
`signal_from_result` -> `Signal.ROLE_NEEDS_INPUT` -> `transition()` raises
`IllegalTransitionError` (`lifecycle.py:101`) *before* the runner's own
`else`/`pragma: no cover` guard is reached.
**Fix:** Catch orchestration errors in `_drive_and_exit` (or `drive`), emit a
one-line diagnostic to stderr, and exit with a code that is not 0 or 1 — 2 fits
"nothing was persisted / bad state" and is already the "not a clean terminal
outcome" code. Alternatively, have Phase 1 explicitly reject a `NEEDS_INPUT`
result at the runner boundary and persist a `FAILED` transition so exit 1 is
truthful.

### WR-08: `runs.workflow` JSONB is written without passing through `redact()`

**File:** `src/dark_factory/persistence/mutations.py:127` (`workflow=workflow`)
**Issue:** `mutations.py`'s module docstring states redaction "is applied *inside*
this module immediately before each `session.add` ... so no caller can persist an
unredacted JSONB payload." Every JSONB write honors that except `create_run`'s
`workflow=workflow`, which stores the caller-supplied dict verbatim. In Phase 1
the value is the static `{"roles": ["BA"]}` snapshot from `_workflow_snapshot`
(`runner.py:104-106`), so there is no live exposure — but Phase 3 loads this
snapshot from a repository `.dark-factory.yaml`, and the "single scrubbing call
site" invariant should hold by construction now rather than be re-litigated then.
**Fix:** `workflow=redact(workflow, known_secrets=known)` in `create_run`, matching
every other JSONB write in the function.

## Info

### IN-01: `runs.normalized_task` persists third-party credentials pasted into task text

**File:** `src/dark_factory/persistence/mutations.py:123-126`
**Issue:** By design (D-18), `normalized_task` / `source_ref` go through
`scrub_known_values` (exact-value only, no pattern table) so a task that discusses
connection-string syntax keeps its wording. The documented cost: a real
third-party credential (not the configured `DATABASE_URL` / `GITHUB_TOKEN`) pasted
into a `text:` body lands in Neon unredacted and, being one-way, is unrecoverable.
Flagging so the tradeoff is a conscious sign-off, not a surprise.
**Fix:** None required if the D-18 decision stands. Optionally run the pattern
table over task text too and accept occasional over-redaction of prose.

### IN-02: no DB-level uniqueness on `role_executions (run_id, role, attempt)`

**File:** `src/dark_factory/persistence/models.py:120-147`, `migrations/versions/0001_walking_skeleton.py:102-127`
**Issue:** `attempt` is computed as `MAX(attempt)+1` under a `runs`-row lock
(`mutations.py:198-199`, `:245-250`), so within the single mutation path duplicates
cannot occur. There is no defense-in-depth constraint if a future writer forgets
the lock. Cheap to add now.
**Fix:** `sa.UniqueConstraint("run_id", "role", "attempt", name="uq_role_exec_attempt")`
in `RoleExecution.__table_args__` and the migration.

### IN-03: `_RUN_STATUS` Enum definition duplicated between model and migration

**File:** `src/dark_factory/persistence/models.py:65-72` and `migrations/versions/0001_walking_skeleton.py:49-56`
**Issue:** The two blocks carry a "must stay byte-for-byte equivalent" comment but
are maintained by hand. A future edit to one (e.g. `length`, `name`,
`values_callable`) that misses the other drifts silently until `alembic check`
runs.
**Fix:** Import `_RUN_STATUS` from `dark_factory.persistence.models` into the
migration instead of redefining it (migrations already import `RunStatus` from
`dark_factory.domain.status`, so importing from the models module is consistent).

### IN-04: `new_session()` returns `object`, forcing `cast(Session, ...)` at every call site

**File:** `src/dark_factory/persistence/engine.py:104-106` (casts at `orchestrator/runner.py:101` and `observability/status.py:49`)
**Issue:** `SessionLocal(bind=get_engine())` is statically a `Session`; annotating
the return as `object` discards that and pushes an unchecked `cast` onto every
caller, weakening `mypy --strict` coverage on the persistence boundary.
**Fix:** `def new_session() -> Session:` and drop the casts.

### IN-05: `_default_session` helper duplicated verbatim

**File:** `src/dark_factory/orchestrator/runner.py:99-101` and `src/dark_factory/observability/status.py:47-49`
**Issue:** Identical function (docstring included) in two modules.
**Fix:** Move to `dark_factory.persistence.engine` (e.g. export a typed
`new_session`) and import it in both.

### IN-06: `_kv_replacement` drops the closing quote of a quoted secret

**File:** `src/dark_factory/events/redaction.py:50-52`
**Issue:** The kv regex captures an optional opening quote as group 3 and requires
a matching closing quote via `\3`, but `_kv_replacement` returns
`group(1)+group(2)+[redacted:...]` without re-emitting group 3. `token="abc"`
becomes `token=[redacted:token]` (unbalanced), which can invalidate a JSON string
embedded in a log line. Not a leak.
**Fix:** `return f"{m.group(1)}{m.group(2)}[redacted:{m.group(1).lower()}]{m.group(3)}"`.

### IN-07: `redact()` passes `set` / `bytes` / other containers through unchanged

**File:** `src/dark_factory/events/redaction.py:116-152`
**Issue:** Only `Mapping`, `list`/`tuple` and `str` are recursed/scrubbed;
anything else is returned as-is. JSONB payloads are JSON-typed so `set`/`bytes`
are not reachable in practice, but a `set` of secret strings or a `bytes`
credential would pass through untouched.
**Fix:** Either coerce unknown iterables (`isinstance(value, (set, frozenset))`)
or assert/log on unexpected types at the persistence boundary.

### IN-08: `current_node` does an index lookup and then re-indexes

**File:** `src/dark_factory/workflows/pipeline.py:44-53`
**Issue:** `pipeline.nodes[pipeline.index_of(current_role)]` walks the tuple to
find the index, then indexes back into it. Minor; correctness is fine.
**Fix:** Return the node directly from the `index_of` scan, or
`next(n for n in pipeline.nodes if n.name == current_role)` with the same
`LookupError` on miss.

### IN-09: role status is derived from the role *name* via `RunStatus(node.name)` — closed enum vs open role names

**File:** `src/dark_factory/orchestrator/lifecycle.py:74`, `:93`
**Issue:** `RunStatus(first.name)` / `RunStatus(following.name)` assume every
pipeline role name is also a member value of the closed 10-value `RunStatus` enum.
True for Phase 1 (`"BA"`) and the pre-declared role statuses, but a custom role
name from a Phase 3 `.dark-factory.yaml` pipeline would raise `ValueError` (not
`IllegalTransitionError`) from the pure transition function. Out of Phase 1 scope;
noted because CLAUDE.md requires the workflow definition to accept new entries
without core changes.
**Fix:** Decide explicitly whether custom role names are representable as run
statuses; if not, map role -> status through an indirection rather than string
identity, and convert the `ValueError` to `IllegalTransitionError`.

---

_Reviewed: 2026-09-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
