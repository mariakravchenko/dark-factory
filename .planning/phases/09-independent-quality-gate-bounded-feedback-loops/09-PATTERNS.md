# Phase 9: Independent Quality Gate & Bounded Feedback Loops - Pattern Map

**Mapped:** 2026-09-22
**Files analyzed:** 13 (5 modified core modules, 2 modified config, 3 modified tests, 3 new test files + fixture extension)
**Analogs found:** 13 / 13 (all have a same-file "extend in place" analog or a strong same-repo precedent)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/dark_factory/domain/signal.py` (add `ROLE_BOUNCED`) | domain enum | event-driven | same file, `Signal` enum + `_RESULT_STATUS_TO_SIGNAL` | exact (extend in place) |
| `src/dark_factory/orchestrator/lifecycle.py` (add `ROLE_BOUNCED` arm) | orchestrator / pure state machine | transform | same file, `ROLE_COMPLETED`/`ROLE_FAILED` arms (lines 100-111) | exact (extend in place) |
| `src/dark_factory/workflows/pipeline.py` (add `previous_node`) | utility | transform | same file, `next_node` (lines 95-101) | exact (mirror existing function) |
| `src/dark_factory/orchestrator/runner.py` (gate + verdict-routing block, `ROLE_BOUNCED` dispatch arm) | orchestrator / controller | request-response + event-driven | same file: write-scope-violation block (lines 1004-1019) for the "signal override before transition()" pattern; `ROLE_FAILED`/capability-denial arm (lines 1042-1067) for the "extend the elif ladder" pattern | exact (extend in place) |
| `src/dark_factory/context/builder.py` (optional-input resolution + verification-file resolution) | service (context assembly) | CRUD / request-response | same file, `_resolve_input`/`_producing_role` (lines 140-197) | exact (extend in place) |
| `src/dark_factory/events/catalog.py` (add `QUALITY_GATE_*` event types) | domain enum / config | event-driven | same file, `CAPABILITY_DENIED` addition (Phase 6, lines 51-52) + its docstring precedent (lines 13-19) | exact (copy precedent) |
| `.dark-factory/roles/DEVELOPMENT.yaml` (new feedback `inputs`) | config | CRUD | `.dark-factory/roles/QA.yaml` `inputs:` declaration (line 51) | exact |
| `src/dark_factory/actions/builtins.py` (`collect_test_results` — likely stays no-op, comment updated) | action / hook | event-driven | same file, `collect_diff` (lines 84-116) if the plan chooses the hook-writes/runner-decides split; otherwise just a docstring update | role-match (or exact if hook approach chosen) |
| `tests/unit/test_lifecycle.py` (add `ROLE_BOUNCED` cases) | test | transform | same file, existing parametrized legal/illegal tables (lines 50-141) | exact (extend in place) |
| `tests/unit/test_domain_enums.py` (update count assertion) | test | transform | same file, `test_event_type_has_exactly_twelve_members...` (lines 114-129) | exact (extend in place) |
| `tests/support/fake_artifacts.py` (FAIL-verdict content + attempt-aware worker) | test fixture | CRUD | same file, `_FOUR_ROLE_FILES["QA"]["verdict.json"]` (lines 86-105) + `LazyFourRoleWorker` (lines 122-160) | exact (extend in place) |
| `tests/db/test_qa_bounce.py` (new) | test (db-tier pipeline) | event-driven | `tests/db/test_four_role_pipeline.py` (full file) | exact |
| `tests/db/test_quality_gate_bounce.py` (new) | test (db-tier pipeline) | event-driven | `tests/db/test_four_role_pipeline.py` (full file) | exact |
| `tests/db/test_iteration_cap_exhaustion.py` (new) | test (db-tier pipeline) | event-driven | `tests/db/test_four_role_pipeline.py` (full file), `tests/db/test_artifact_schema_violation_fails_role.py` (failure-shape idiom) | exact |
| `tests/unit/test_quality_gate.py` (new, Claude's discretion in RESEARCH) | test (pure unit) | transform | `tests/unit/test_lifecycle.py` (pure-function, no-DB idiom) | exact |

## Pattern Assignments

### `src/dark_factory/domain/signal.py`

**Analog:** same file (this is a 3-line addition to an existing enum + dict)

**Current shape** (lines 22-35):
```python
class Signal(StrEnum):
    """What just happened, as the orchestrator sees it. Value equals name."""

    ENTER = "ENTER"
    ROLE_COMPLETED = "ROLE_COMPLETED"
    ROLE_FAILED = "ROLE_FAILED"
    ROLE_NEEDS_INPUT = "ROLE_NEEDS_INPUT"


_RESULT_STATUS_TO_SIGNAL: dict[WorkerResultStatus, Signal] = {
    WorkerResultStatus.COMPLETED: Signal.ROLE_COMPLETED,
    WorkerResultStatus.FAILED: Signal.ROLE_FAILED,
    WorkerResultStatus.NEEDS_INPUT: Signal.ROLE_NEEDS_INPUT,
}
```

**Pattern to copy:** Add `ROLE_BOUNCED = "ROLE_BOUNCED"` as a new member. **Do not** add it to `_RESULT_STATUS_TO_SIGNAL` — `signal_from_result` maps only `WorkerResult.status`, and `ROLE_BOUNCED` is never a direct mapping of a worker's own status; it is computed in `runner.py` by overriding an already-computed `Signal.ROLE_COMPLETED` (or `ROLE_FAILED`) after inspecting `Verdict.computed_status` / gate output and the iteration-cap counters — mirroring the existing write-scope-violation override pattern in `runner.py` (see below), which also overrides an already-computed signal rather than adding a new dict entry.

---

### `src/dark_factory/orchestrator/lifecycle.py`

**Analog:** same file, the `ROLE_COMPLETED` and `ROLE_FAILED` arms

**Core pattern** (lines 100-111, the exact shape to mirror):
```python
if signal is Signal.ROLE_COMPLETED:
    following = next_node(pipeline, role)
    if following is None:
        return RunStatus.COMPLETED, role, state.current_step
    return (
        RunStatus(following.name),
        following.name,
        pipeline.index_of(following.name),
    )

if signal is Signal.ROLE_FAILED:
    return RunStatus.FAILED, role, state.current_step
```

**New arm to add** (guard-compliant — no role-name literal; uses the new `previous_node` helper):
```python
if signal is Signal.ROLE_BOUNCED:
    target = previous_node(pipeline, role)
    if target is None:
        raise IllegalTransitionError(
            f"{status.value} has no earlier role to bounce a signal to"
        )
    return RunStatus(target.name), target.name, pipeline.index_of(target.name)
```
Add `previous_node` to the `from dark_factory.workflows.pipeline import ...` line (currently `Pipeline, current_node, next_node` at line 31).

**Critical constraint:** `tests/unit/test_no_role_name_literal.py` AST-walks this file and forbids the six `RunStatus` string literals outside docstrings — never write `"DEVELOPMENT"` here. `tests/unit/test_lifecycle.py::test_lifecycle_module_has_no_persistence_import_and_no_session` also AST-walks this file for `Session`/persistence imports — `previous_node` must stay a pure `pipeline.py` function with no persistence import, exactly like `next_node`.

---

### `src/dark_factory/workflows/pipeline.py`

**Analog:** same file, `next_node` (lines 95-101)

**Exact pattern to mirror:**
```python
def next_node(pipeline: Pipeline, current_role: str) -> RoleNode | None:
    """Return the node after ``current_role``, or ``None`` when it is the last one."""
    idx = pipeline.index_of(current_role)
    following = idx + 1
    if following >= len(pipeline.nodes):
        return None
    return pipeline.nodes[following]
```

**New function:**
```python
def previous_node(pipeline: Pipeline, current_role: str) -> RoleNode | None:
    """Return the node before ``current_role``, or ``None`` when it is the first one."""
    idx = pipeline.index_of(current_role)
    preceding = idx - 1
    if preceding < 0:
        return None
    return pipeline.nodes[preceding]
```
Add `"previous_node"` to `__all__` (currently `["DEFAULT_PIPELINE", "Pipeline", "RoleNode", "current_node", "next_node", "pipeline_from_snapshot"]`, line 19-26).

---

### `src/dark_factory/orchestrator/runner.py`

**Analog 1 — "override an already-computed signal before `transition()`"**: the write-scope-violation block, lines 1004-1019:
```python
if signal is Signal.ROLE_COMPLETED:
    write_scope = (role_def.get("permissions") or {}).get(
        "write_scope", list(DEFAULT_WRITE_SCOPE)
    )
    try:
        enforce_write_scope(
            work_dir,
            write_scope=write_scope,
            role=node.name,
            attempt=latest.attempt,
        )
    except WriteScopeViolation as exc:
        signal = Signal.ROLE_FAILED
        outcome = {**outcome, "error": str(exc)}
        artifact_writes = []

next_status, next_role, next_step = transition(state, signal, pipeline)
```
Insert the new verdict/gate block in this same style, **after** this block and still **before** `transition()` is called (line 1020) — read `verdict.json` back out of `artifact_writes`, compute PASS/FAIL, run the gate via `shell_execute` if verdict PASSes, and reassign `signal` to `Signal.ROLE_BOUNCED` or `Signal.ROLE_FAILED` as appropriate, gated on `next_node(pipeline, node.name) is None` (never a role-name literal — see RESEARCH Critical Mechanics Gap 3).

**Analog 2 — "extend the signal-dispatch elif ladder"**: the `ROLE_FAILED` arm with capability-denial prepend, lines 1042-1067:
```python
elif signal is Signal.ROLE_FAILED:
    re_status = _ROLE_FAILED
    re_result = None
    re_error = outcome
    events = [
        EventWrite(
            type=EventType.ROLE_FAILED,
            payload={
                "role": node.name,
                "error": outcome.get("error") or result.summary,
            },
        ),
        EventWrite(type=EventType.RUN_FAILED, payload={"role": node.name}),
    ]
    if capability_denial is not None:
        events.insert(
            0,
            EventWrite(type=EventType.CAPABILITY_DENIED, payload=capability_denial),
        )
```
Add a new `elif signal is Signal.ROLE_BOUNCED:` arm in the identical shape: `re_status = _ROLE_COMPLETED` (per RESEARCH Assumption A3 — a bounced attempt genuinely completed; only run-level routing differs, and `_resolve_input`'s `status == "COMPLETED"` filter in `context/builder.py` depends on this), `re_result = outcome`, and a new gate/QA-specific `EventType` (not `ROLE_FAILED`/`RUN_FAILED` — see Pitfall 4 in RESEARCH). Then pass `counter_increments={"qa_developer_iterations": 1}` or `{"quality_gate_iterations": 1}` into the `apply_transition(...)` call at line 1092-1113 (parameter already exists and is atomic under `with_for_update`; no new locking code needed).

**Gate command execution — new code, no existing exact analog, but a clear composition of two existing calls:**
```python
import shlex
from dark_factory.tools.env import shell_execute

commands: list[str] = state.workflow.get("quality_gate", {}).get("commands", [])
results = [
    {
        "command": cmd,
        **shell_execute(
            command=shlex.split(cmd),
            cwd=work_dir,
            role="quality_gate",  # not a RunStatus value -- guard-safe
            timeout=get_settings().worker_timeout_seconds,
        ).model_dump(),
    }
    for cmd in commands
]
```
Config reads follow `_role_definition`'s existing raw-dict idiom (`state.workflow["roles"]`, `state.workflow.get("quality_gate")` already used in `context/builder.py:272-274`) — **never** import `dark_factory.config.loader`/`RepoConfig` into `runner.py` (enforced by `tests/unit/test_orchestrator_no_live_config_read.py`).

**Verification-file write pattern** — copy `collect_diff`'s exact precedent (`src/dark_factory/actions/builtins.py:84-116`):
```python
from dark_factory.artifacts.paths import resolve_under_run_root

destination = resolve_under_run_root(run_dir, "verification/quality_gate.json")
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(gate_result.model_dump_json(), encoding="utf-8")
```

**Reading QA's verdict back out** (no existing call does this today — new code, composition of existing helpers):
```python
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.domain.artifacts import Verdict
from dark_factory.domain.status import VerdictStatus
import json

verdict_write = next((w for w in artifact_writes if w.type == "verdict.json"), None)
if verdict_write is not None:
    verdict = Verdict.model_validate(json.loads(read_artifact_text(run_dir, verdict_write.path)))
```

---

### `src/dark_factory/context/builder.py`

**Analog:** same file, `_resolve_input`/`_producing_role` (lines 140-197)

**Current mandatory-resolution pattern** (lines 259-262, the crash point Pitfall 2 warns about):
```python
inputs = [
    _resolve_input(session, repo_root, run_id, state, filename)
    for filename in role_def.get("inputs", [])
]
```

**Required new mechanism** (open design point per RESEARCH — plan must pick direction (a) or (b), but (a) is recommended and has the clearer analog): add an optional-input escape hatch that catches `MissingArtifactContentError` for declared-optional feedback inputs (`verdict.json` on Developer's first attempt, before QA has ever run) and simply omits them from `RoleContext.inputs`, plus a **second, distinct resolution path** for `verification/quality_gate.json` that bypasses `_producing_role`/`ArtifactReference` entirely — a direct, tolerant read:
```python
def _read_verification_file(run_dir: Path, filename: str) -> ArtifactInput | None:
    """Read an orchestrator-written verification/ file directly -- bypasses
    _producing_role/ArtifactReference because this file has no role_executions
    row to attach to (D-01)."""
    path = f"verification/{filename}"
    try:
        content = read_artifact_text(run_dir, path)
    except FileNotFoundError:
        return None
    return ArtifactInput(filename=filename, produced_by="quality_gate", path=path, content=content)
```
Reuses `read_artifact_text` (`src/dark_factory/artifacts/store.py`) exactly as `_resolve_input` already does at line 191.

---

### `src/dark_factory/events/catalog.py`

**Analog:** same file, Phase 6's `CAPABILITY_DENIED` addition — both the docstring precedent (lines 13-19) and the enum addition (lines 51-52):
```python
# Phase 6 -- the capability-denial audit tie (D-07, D-08).
CAPABILITY_DENIED = "CAPABILITY_DENIED"
```

**Pattern to copy:** add a new docstring paragraph (matching the existing per-phase paragraph style at lines 1-25) explaining what Phase 9 adds and why, then add the new members, e.g.:
```python
# Phase 9 -- the independent quality-gate and bounce audit trail (D-02).
QUALITY_GATE_STARTED = "QUALITY_GATE_STARTED"
QUALITY_GATE_PASSED = "QUALITY_GATE_PASSED"
QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
```
**Must also update** the docstring's line 19-21 ("QUALITY_GATE_FAILED/PASSED... still arrive in Phase 12") — this is stale the moment Phase 9 ships these members; see RESEARCH Pitfall 5.

---

### `.dark-factory/roles/DEVELOPMENT.yaml`

**Analog:** `.dark-factory/roles/QA.yaml`'s `inputs:` declaration style (line 51):
```yaml
inputs: [acceptance_criteria.json, implementation_summary.json]
```
**Current DEVELOPMENT.yaml** (line 46): `inputs: [design.md, constraints.json]`
**Change:** append the new feedback filenames, e.g. `inputs: [design.md, constraints.json, verdict.json, quality_gate.json]` — **must land in the same change as the `context/builder.py` optional-input fix** (Pitfall 2 in RESEARCH: landing the config change alone crashes every Developer attempt 1, not just bounces).

---

### `src/dark_factory/actions/builtins.py`

**Analog:** `collect_diff` (lines 84-116) if the plan splits gate-execution (hook) from bounce-decision (runner); otherwise this file needs only a docstring/comment update leaving `collect_test_results` (lines 136-138) a permanent no-op, matching the existing style of `prepare_role_context`/`store_role_artifacts`'s "permanent no-op" docstrings (lines 48-55, 119-133). RESEARCH recommends keeping gate logic inline in `runner.py` and updating this stub's comment plus `QA.yaml`'s `after:` list comment (lines 36-37, 47) rather than making the hook real.

---

## Shared Patterns

### "Compute-then-override signal before transition()" (runner.py)
**Source:** `src/dark_factory/orchestrator/runner.py:1004-1020` (write-scope-violation block)
**Apply to:** the new QA-verdict / quality-gate routing block — reassign the local `signal` variable and mutate `outcome`/`artifact_writes` exactly as this existing block does, keeping `transition()` itself untouched and called exactly once per attempt.

### "Extend an elif ladder with a new signal arm, mirroring the existing shape" (runner.py)
**Source:** `src/dark_factory/orchestrator/runner.py:1023-1088` (`ROLE_COMPLETED`/`ROLE_FAILED`/`ROLE_NEEDS_INPUT`/else)
**Apply to:** the new `elif signal is Signal.ROLE_BOUNCED:` arm — same four locals (`re_status`, `re_result`, `re_error`, `events`), same `apply_transition(...)` call site at the bottom (line 1092), extended with `counter_increments`.

### Config reads via raw `state.workflow` dict, never live config import
**Source:** `src/dark_factory/context/builder.py:268-274` (`state.workflow.get("quality_gate")`, `state.workflow.get("repository")`); `src/dark_factory/orchestrator/runner.py`'s `_role_definition` (`state.workflow["roles"]`)
**Apply to:** all new `runner.py` reads of `quality_gate.commands`, `retry.qa_developer_max_iterations`, `retry.quality_gate_max_iterations` — never `from dark_factory.config.loader import ...` inside `runner.py`/`lifecycle.py`/`pipeline.py`/`answers.py` (enforced by `tests/unit/test_orchestrator_no_live_config_read.py`'s AST closure guard).

### Filesystem write under `verification/`, riding the role's own artifact commit
**Source:** `src/dark_factory/actions/builtins.py:84-116` (`collect_diff`)
**Apply to:** the new `verification/quality_gate.json` write — same `resolve_under_run_root` + `mkdir(parents=True, exist_ok=True)` + `write_text(..., encoding="utf-8")` shape.

### Role-name-literal guard compliance
**Source:** `tests/unit/test_no_role_name_literal.py` (guard test, not modified by this phase)
**Apply to:** every new line in `runner.py`, `lifecycle.py`, `workflows/pipeline.py` — use `next_node(...)`/`previous_node(...) is None` structural checks, never `if node.name == "QA"` or a literal `"DEVELOPMENT"`.

### Redaction gap — filesystem writes bypass `apply_transition`'s `redact()`
**Source:** `src/dark_factory/persistence/mutations.py:29-33,319,354-361` (`redact()` call site, JSONB-only)
**Apply to:** `verification/quality_gate.json`'s `stdout`/`stderr` fields and any `QUALITY_GATE_FAILED` event payload that embeds them — the JSONB event payload passes through `redact()` automatically, but the filesystem file and `ContextBuilder`'s later re-read of it (`read_artifact_text`, `src/dark_factory/artifacts/store.py:23-47`) do not. Plan should explicitly decide whether to reuse `dark_factory.events.redaction.redact`/`scrub_known_values` on `stdout`/`stderr` before the file write, or document this as an accepted scoped risk (RESEARCH Security Domain, SEC-01 exposure).

## No Analog Found

None — every file in this phase's scope either extends an existing file in place (with a directly-analogous existing block to mirror) or is a new test file with a strong same-repo db-tier test idiom (`tests/db/test_four_role_pipeline.py`) to copy structurally.

## Metadata

**Analog search scope:** `src/dark_factory/{domain,orchestrator,workflows,context,events,actions,tools}/`, `.dark-factory/roles/`, `tests/{unit,db,support}/`
**Files scanned:** signal.py, lifecycle.py, pipeline.py, runner.py (targeted ranges), context/builder.py, events/catalog.py, actions/builtins.py, tools/env.py, DEVELOPMENT.yaml, QA.yaml, test_lifecycle.py, test_domain_enums.py, test_four_role_pipeline.py, fake_artifacts.py
**Pattern extraction date:** 2026-09-22
