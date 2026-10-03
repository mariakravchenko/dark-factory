# Phase 12: Observability & Audit Surface - Pattern Map

**Mapped:** 2026-10-03
**Files analyzed:** 9
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/dark_factory/cli.py` (+ `runs`, `artifacts`, `events` commands) | route/controller | request-response | `src/dark_factory/cli.py::status` (same file, existing command) | exact |
| `src/dark_factory/observability/run_detail.py` (new) | service/read-model | CRUD (read) | `src/dark_factory/observability/status.py::read_status` | exact |
| `src/dark_factory/events/reader.py` (new) | service/read-model | CRUD (read) | `tests/db/test_publish_step.py::_event_types` (query shape) + `observability/status.py` (module shape) | role-match |
| `src/dark_factory/git/committed.py` (new) | utility | file-I/O | `tests/support/git_repo.py::read_committed` / `run_artifact_text` | exact (promote test helper to production) |
| `src/dark_factory/events/catalog.py` (+3 `EventType` members) | config/enum | event-driven | `src/dark_factory/events/catalog.py` (existing Phase 9/10 additions) | exact |
| `src/dark_factory/orchestrator/runner.py` (`ARTIFACT_CREATED` emission) | controller/orchestrator | event-driven | `runner.py`'s existing `gate_events` splice pattern (ROLE_COMPLETED/ROLE_BOUNCED arms) | exact |
| `src/dark_factory/orchestrator/runner.py` (`QA_FAILED`/`QA_PASSED` emission) | controller/orchestrator | event-driven | `runner.py`'s existing `QUALITY_GATE_STARTED`/`gate_events` accumulator in the verdict block | exact |
| `src/dark_factory/orchestrator/runner.py` (redact clarification comment body) | controller/orchestrator | request-response | `orchestrator/quality_gate.py:172-177`'s redact-before-external-sink precedent | exact |
| `tests/integration/test_runs_cli.py`, `test_events_cli.py` (new) | test | request-response | `tests/integration/test_status_cli.py` | exact |
| `tests/db/test_artifact_created_event.py`, `test_qa_verdict_events.py` (new) | test | event-driven | `tests/db/test_publish_step.py` | exact |
| `tests/db/test_secret_redaction_e2e_full_pipeline.py` (new) | test | event-driven | `tests/db/test_publish_step.py` + `tests/integration/test_secret_redaction_e2e.py` | role-match (composite) |

## Pattern Assignments

### `src/dark_factory/cli.py` — new `runs`, `artifacts`, `events` commands (controller, request-response)

**Analog:** `src/dark_factory/cli.py::status` (lines 224-257, same file)

**Imports already present to reuse** (lines 22-54):
```python
import functools
from uuid import UUID
import typer
from dark_factory.config.settings import get_settings
from dark_factory.domain.status import RunStatus
from dark_factory.events.redaction import redact
from dark_factory.observability.status import UnknownRunError, read_status
```
Add: `from dark_factory.observability.run_detail import ...`, `from dark_factory.events.reader import read_events`, `from dark_factory.events.catalog import EventType`.

**Core thin-wrapper pattern to copy verbatim** (lines 224-257):
```python
@app.command()
def status(
    run_id: str,
    output_json: bool = typer.Option(False, "--json", ...),
) -> None:
    try:
        parsed = UUID(run_id)
    except ValueError as exc:
        typer.echo(f"not a run id: {run_id}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        view = read_status(parsed)
    except UnknownRunError as exc:
        typer.echo(f"unknown run: {run_id}", err=True)
        raise typer.Exit(code=2) from exc

    redactor = functools.partial(
        redact, known_secrets=get_settings().known_secret_values()
    )
    if output_json:
        _route_logs_to_stderr()
        typer.echo(view.as_json(redactor=redactor))
    else:
        typer.echo(view.as_text(redactor=redactor))
```
Apply this identical shape to `runs` (no `run_id` arg, `--status` option parsed via `RunStatus(value)` inside a `try/except ValueError -> exit 2`), `artifacts <run_id> [--show <artifact-id>]`, and `events <run_id> [--json] [--type ...]`. Rendering differs (rich Table/Console for `runs`; redacted text for `artifacts --show`) but the parse -> call read-function -> redact -> echo -> exit shape is identical. No lifecycle branching, no `RunStatus` comparison inside the command body (there's an AST guard: `tests/integration/test_status_cli.py::test_status_command_body_carries_no_lifecycle_logic` — replicate for new commands).

**Error handling pattern**: unknown run id and bad UUID both `typer.echo(..., err=True)` + `raise typer.Exit(code=2)`. Reuse verbatim for the new commands' id-parsing paths.

**`--status` / `--type` validation pattern** (new, not yet in cli.py, but mirrors the `UUID(run_id)` try/except shown above):
```python
try:
    status_filter = RunStatus(value)
except ValueError as exc:
    typer.echo(f"not a status: {value}", err=True)
    raise typer.Exit(code=2) from exc
```

---

### `src/dark_factory/observability/run_detail.py` (new) (service/read-model, CRUD-read)

**Analog:** `src/dark_factory/observability/status.py::read_status` (full file, 91 lines)

**Module-level architectural guard to copy into the new module's docstring and preserve in practice:**
```python
# Source: src/dark_factory/observability/status.py:1-21
"""... issues **no** query against run_events and this module imports
**nothing** from `dark_factory.events` -- tests/unit/test_status_import_graph.py
walks the transitive import closure and fails on a violation ... read_status
also performs **no write of any kind**."""
```
`run_detail.py` must carry the identical guard (no import of `dark_factory.events`, no write). It composes `Run` / `RoleExecution` (ALL rows, not just latest) / `HumanInteraction` / `ArtifactReference`.

**Session-factory + query pattern to copy** (lines 48-90):
```python
def read_status(
    run_id: UUID,
    *,
    session_factory: SessionFactory = new_session,
) -> RunView:
    session = session_factory()
    try:
        run = session.get(Run, run_id)
        if run is None:
            raise UnknownRunError(run_id)
        latest = session.scalar(
            select(RoleExecution)
            .where(RoleExecution.run_id == run_id)
            .order_by(RoleExecution.created_at.desc(), RoleExecution.attempt.desc(), RoleExecution.id.desc())
            .limit(1)
        )
        return RunView(...)
    finally:
        session.close()
```
For "per-role history" (OBS-01), drop `.limit(1)` and instead `select(RoleExecution).where(...).order_by(RoleExecution.created_at.asc(), RoleExecution.attempt.asc())` to get every attempt row; for artifacts, `select(ArtifactReference).join(RoleExecution).where(RoleExecution.run_id == run_id)`; for questions/answers, `select(HumanInteraction).where(HumanInteraction.run_id == run_id).order_by(HumanInteraction.created_at.asc())`. Same `UnknownRunError(LookupError)` type, same `session.close()` in `finally`, same `SessionFactory = Callable[[], Session]` type alias for test injection.

---

### `src/dark_factory/events/reader.py` (new) (service/read-model, CRUD-read, event-driven)

**Analog (query shape):** `tests/db/test_publish_step.py:224-232`
```python
def _event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )
```
Production version needs the full row (`seq`, `created_at`, `type`, `payload`, `role_execution_id`), still `.where(RunEvent.run_id == run_id).order_by(RunEvent.seq)` — never `.order_by(RunEvent.created_at)` (`RunEvent`'s own docstring at `persistence/models.py:209-215` forbids ordering by wall clock). Add a `event_types: Sequence[EventType] | None = None` filter param for `--type`, applied as `.where(RunEvent.type.in_([t.value for t in event_types]))`.

**Module shape (session-factory + `finally: session.close()`):** copy from `observability/status.py` (above) even though this module intentionally DOES import `dark_factory.events` (it's the one new module permitted to) — keep it a sibling, never merged into `observability/status.py` or `run_detail.py`.

---

### `src/dark_factory/git/committed.py` (new) (utility, file-I/O)

**Analog:** `tests/support/git_repo.py:58-91` (`read_committed`, `run_artifact_text`) — promote directly to production, reusing `run_git` from `src/dark_factory/git/client.py`.

```python
# Source: tests/support/git_repo.py:58-91 [promote to src/dark_factory/git/committed.py]
def read_committed(repo_root: Path, branch: str, relative_path: str) -> str:
    """``git show <branch>:<relative_path>``."""
    return run_git(["show", f"{branch}:{relative_path}"], cwd=repo_root).stdout

def run_artifact_text(
    repo_root: Path, run_id: UUID, working_branch: str, relative_path: str
) -> str:
    return read_committed(
        repo_root, working_branch, f".dark-factory/runs/{run_id}/{relative_path}"
    )
```
Must use the existing `run_git` wrapper (`src/dark_factory/git/client.py:74-117`) — explicit arg list, `cwd=`, the `GIT_ENV_ALLOWLIST`, never a second subprocess invocation helper (see Don't-Hand-Roll in RESEARCH.md). `artifacts --show` and the quality-gate-results read in `run_detail.py`/`status.py`-adjacent code both call this, keyed by `ArtifactReference.id` (never a free-text path) per the path-traversal mitigation in RESEARCH.md's Security Domain.

---

### `src/dark_factory/events/catalog.py` (+3 members) (config/enum, event-driven)

**Analog:** the existing Phase 9/10 additions in the same file (lines 75-86).

```python
# Source: src/dark_factory/events/catalog.py:75-86 (existing pattern to extend)
    # Phase 9 -- the independent quality-gate audit tie (D-02).
    QUALITY_GATE_STARTED = "QUALITY_GATE_STARTED"
    QUALITY_GATE_PASSED = "QUALITY_GATE_PASSED"
    QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
    ...
    # Phase 10 -- the idempotent-publishing audit tie (D-07).
    PUBLISH_STARTED = "PUBLISH_STARTED"
    PR_CREATED = "PR_CREATED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
```
Append, following the identical comment-block convention (name the phase, cite the decision, state why it's genuinely reachable now):
```python
    # Phase 12 -- the artifact-write and QA-verdict audit ties.
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    QA_FAILED = "QA_FAILED"
    QA_PASSED = "QA_PASSED"
```
**Also update** the module docstring's "not-yet-reachable types are deliberately not pre-declared" narrative (lines 32-34 currently say these three "still arrive in Phase 12") and grep for a catalog-cardinality unit test (RESEARCH.md Assumption A3) to bump its expected count in the same commit.

---

### `src/dark_factory/orchestrator/runner.py` — `ARTIFACT_CREATED` emission (orchestrator, event-driven)

**Analog:** the existing `gate_events` accumulator-and-splice pattern in the same file (verbatim, lines ~1518-1610):
```python
# ROLE_COMPLETED arm:
events = [EventWrite(type=EventType.ROLE_COMPLETED, payload={"role": node.name, "summary": result.summary})]
...
events.extend(gate_events)
# ROLE_BOUNCED arm:
events = [EventWrite(type=EventType.ROLE_COMPLETED, payload={"role": node.name, "summary": result.summary})]
events.extend(gate_events)
```
Build `artifact_events = [EventWrite(type=EventType.ARTIFACT_CREATED, role_execution_id=latest.id, payload={"role": node.name, "type": w.type, "path": w.path}) for w in artifact_writes]` **after** every point that can clear `artifact_writes` back to `[]` (the `GitError`/`WriteScopeViolation` catches), then `events.extend(artifact_events)` in the `ROLE_COMPLETED` and `ROLE_BOUNCED` arms only (not `ROLE_FAILED`, since `artifact_writes` is always `[]` there by construction).

**`EventWrite` shape to construct against:** `src/dark_factory/persistence/mutations.py:127-135`
```python
class EventWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: EventType
    role_execution_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
```

---

### `src/dark_factory/orchestrator/runner.py` — `QA_FAILED`/`QA_PASSED` emission (orchestrator, event-driven)

**Analog:** the existing structural (never role-name-literal) verdict-detection block and its `gate_events`-style accumulator (`runner.py:1233-1412`), governed by `tests/unit/test_no_role_name_literal.py` (forbids `"QA"`/`"BA"` literals under `orchestrator/`).

```python
# Pattern: accumulate, then extend into every arm the gate_events list already reaches.
qa_verdict_events: list[EventWrite] = []
if verdict.computed_status is VerdictStatus.FAIL:
    qa_verdict_events.append(EventWrite(
        type=EventType.QA_FAILED,
        payload={"role": node.name, "criteria_failed": [c.criterion_id for c in verdict.criteria if c.result is VerdictStatus.FAIL]},
    ))
else:
    qa_verdict_events.append(EventWrite(
        type=EventType.QA_PASSED,
        payload={"role": node.name},
    ))
# then, in all three arms, alongside `events.extend(gate_events)`:
events.extend(qa_verdict_events)
```
Detect the verdict role by artifact **type** (`w.type == "verdict.json"`), exactly as the existing block already does — never by role name.

---

### `src/dark_factory/orchestrator/runner.py` — redact clarification comment body (orchestrator, request-response)

**Analog:** `src/dark_factory/orchestrator/quality_gate.py:172-177`'s redact-before-external-sink precedent (redact the `GateCommandResult.command` string before it reaches a durable/external sink, not only before the DB write).

**Current buggy call site** (`runner.py:1662-1676`, `ROLE_NEEDS_INPUT` branch):
```python
comment_body = build_clarification_comment(result.questions)
client.create_comment(..., body=comment_body)   # no redact() call
```
**Fix, mirroring the existing `functools.partial(redact, known_secrets=...)` idiom** (`cli.py:249-251`):
```python
known = get_settings().known_secret_values()
comment_body = build_clarification_comment(
    [redact(q, known_secrets=known) for q in result.questions]
)
client.create_comment(..., body=comment_body)
```

---

### Tests

**`tests/integration/test_runs_cli.py`, `test_events_cli.py`** — analog `tests/integration/test_status_cli.py` (the `_cli()` subprocess helper, lines 33-57; env built from `pg_url`, `DARK_FACTORY_FAKE_SCRIPT`/`DARK_FACTORY_CRASH_AFTER` stripped). Copy the helper verbatim; add new test functions asserting stdout substrings (text) and `json.loads(stdout)` keys (`--json`), plus `proc.returncode`.

**`tests/db/test_artifact_created_event.py`, `test_qa_verdict_events.py`** — analog `tests/db/test_publish_step.py`'s `_event_types` helper (quoted above) and its `_write_github_four_role_tree` + `drive(...)` fixture composition.

**`tests/db/test_secret_redaction_e2e_full_pipeline.py`** — composite analog of `tests/db/test_publish_step.py` (FakeGitHubClient + `drive(..., github_client_factory=...)`) and `tests/integration/test_secret_redaction_e2e.py` (seeded secrets + `real_log_sink` + whole-table sweep). Build as `db`-tier, not `integration`, because injecting `FakeGitHubClient` requires driving through `drive()`/`start_run()` directly rather than the CLI subprocess (which always binds `default_github_client_factory`).

## Shared Patterns

### Redaction at every new sink
**Source:** `src/dark_factory/events/redaction.py::redact` + the `functools.partial(redact, known_secrets=get_settings().known_secret_values())` call-site idiom at `cli.py:249-251`.
**Apply to:** `runs`/`events`/`artifacts --show` CLI output, the clarification-comment body fix in `runner.py`. `redact()` is the only implementation in the codebase — never a second regex/substitution helper.

### One mutation path / EventWrite accumulate-then-extend
**Source:** `src/dark_factory/persistence/mutations.py` (`apply_transition` is the only writer of `run_events`/`artifacts`/`role_executions`) and `runner.py`'s existing `gate_events` splice across the `ROLE_COMPLETED`/`ROLE_FAILED`/`ROLE_BOUNCED` arms.
**Apply to:** `ARTIFACT_CREATED` and `QA_FAILED`/`QA_PASSED` emission — build the list once, splice into the arms already proven correct for `gate_events`, never open a second write path.

### Thin Typer command, no lifecycle logic in the body
**Source:** `cli.py::status` (and the AST guard `test_status_command_body_carries_no_lifecycle_logic`).
**Apply to:** `runs`, `artifacts`, `events` — parse args, call one read function, redact, render, exit.

### Read artifact/quality-gate content via git, never a live worktree path
**Source:** `tests/support/git_repo.py::read_committed`/`run_artifact_text`, promoted to `src/dark_factory/git/committed.py`, built on `src/dark_factory/git/client.py::run_git`.
**Apply to:** `artifacts --show`, quality-gate-results read inside the expanded `status`/`run_detail.py` report — a `COMPLETED` run's worktree is already removed by `_cleanup_run_worktree`.

### Architectural import-graph guard: `run_events` reads stay out of `observability/status.py`
**Source:** `observability/status.py`'s module docstring + `tests/unit/test_status_import_graph.py`.
**Apply to:** `run_detail.py` (must NOT import `dark_factory.events`) vs. `events/reader.py` (the one new module permitted to import it for a read path) — keep them separate sibling modules, never merged.

## No Analog Found

None — every new file in this phase has a strong existing analog (either production code from an earlier phase or a test-tier helper slated for promotion). RESEARCH.md's own framing confirms this: "this phase is wire up existing data into a new CLI surface, not new infrastructure."

## Metadata

**Analog search scope:** `src/dark_factory/cli.py`, `src/dark_factory/observability/status.py`, `src/dark_factory/events/{catalog,redaction}.py`, `src/dark_factory/persistence/{mutations,models}.py`, `src/dark_factory/git/client.py`, `src/dark_factory/orchestrator/runner.py`, `tests/support/git_repo.py`, `tests/db/test_publish_step.py`, `tests/integration/test_status_cli.py`
**Files scanned:** 9 read in full/targeted sections this session
**Pattern extraction date:** 2026-10-03
