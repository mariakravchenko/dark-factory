# Phase 9: Independent Quality Gate & Bounded Feedback Loops - Context

**Gathered:** 2026-09-22
**Status:** Ready for planning

<domain>
## Phase Boundary

After QA passes, Dark Factory itself re-runs the repository's own
`quality_gate.commands` in the run's worktree — the gate decision comes from
exit codes, never from agent prose or self-reports, even though Developer and
QA may still run their own tests/lint during their own work. The gate's
result (per-command exit code + captured output) is written to
`verification/quality_gate.json`.

Both feedback edges get bounded, config-driven retry: a QA FAIL routes a
structured issues artifact back to the Developer; a quality-gate FAIL routes
the actual command failure output back to the Developer, after which QA
re-evaluates and the gate re-runs. Each edge has its own iteration counter
(`Run.qa_developer_iterations`, `Run.quality_gate_iterations`, already
scaffolded) checked against its own config cap
(`retry.qa_developer_max_iterations`, `retry.quality_gate_max_iterations`,
already scaffolded in `RepoConfig`) *before* dispatch. Exhausting either cap
transitions the run to `FAILED` with every attempt and the exhaustion reason
persisted.

Out of scope (belongs to other phases): GitHub issue intake and idempotent
publishing (Phase 10) — this phase only prevents an unverified result from
advancing past the gate, it does not create the PR; cross-machine/CI resume
proof (Phase 11); the observability/audit surface beyond the events this
phase itself adds (Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Gate placement in the pipeline
- **D-01:** The quality gate is an orchestrator-only step, not a pipeline role. It is not added to `workflow.roles` and gets no `WorkerRegistry` entry, no `role_executions` row, and no worker of any kind. Once QA's role attempt transitions to `COMPLETED` with a PASS verdict, the orchestrator (in `runner.py`, right where the QA branch currently computes its transition) directly invokes `shell_execute` for each `quality_gate.commands` entry, writes `verification/quality_gate.json`, and only then computes the transition to the next real role. This matches GATE-02/03's framing that the gate is Dark Factory's own check, not agent work, and avoids inventing a fake "internal worker" concept just to reuse `_run_current_role`. — **Reversibility:** costly — **rationale:** promoting the gate to a real pseudo-role later would mean adding a `WorkerRegistry` entry, a role config shape, and migrating the orchestrator-only call site into the dispatch loop; not a trivial refactor once other Phase 9 code assumes "gate has no role_executions row."
- **D-02:** The gate's start/pass/fail are visible in the audit trail via new, narrow purpose-built `run_events` (e.g. `QUALITY_GATE_STARTED`, `QUALITY_GATE_PASSED`, `QUALITY_GATE_FAILED`), following Phase 6's `CAPABILITY_DENIED` precedent — an auditable fact worth its own event type rather than folding into QA's existing events. `dark-factory status` can show gate attempts in the timeline even though there is no `role_executions` row for them.
- **D-03:** Gate commands run with `cwd` set to the run's existing worktree at HEAD — the same worktree `shell.execute` already uses for role work, exactly what QA and Developer just committed. No separate clone/worktree for gate isolation; Phase 5's per-role write-scope and clean-tree discipline is treated as sufficient.

### Bounce-back mechanism
- **D-04:** A new `Signal.ROLE_BOUNCED` is added alongside `ROLE_COMPLETED`/`ROLE_FAILED`/`ROLE_NEEDS_INPUT` (`domain/signal.py`). `lifecycle.transition()` maps it to re-entering the Developer's position in the pipeline, instead of `RunStatus.FAILED`. The orchestrator decides `ROLE_BOUNCED` vs `ROLE_FAILED` by checking the relevant iteration counter against its config cap *before* choosing the signal for a QA-FAIL or gate-FAIL outcome: under cap → `ROLE_BOUNCED`; at/over cap → `ROLE_FAILED`. This keeps `lifecycle.transition()` as the single place the run's next position is computed, preserving the "one mutation path" invariant from Phase 1/3 rather than letting `runner.py` hand-build a competing next-state decision. — **Reversibility:** one-way — **rationale:** `Signal` is consumed by `lifecycle.transition()`'s pure state-machine logic and by `signal_from_result`; once other code (and tests) depend on `ROLE_BOUNCED` existing as a distinct signal, collapsing it back into `ROLE_FAILED` means re-threading the iteration-cap check into every call site that currently just inspects the signal.
- **D-05:** On a bounce, both Developer and QA get a fresh `role_executions` row (`attempt = previous_attempt + 1`) each time they re-run — reusing the existing `_enter_role`/attempt-increment machinery from Phase 4, not an update-in-place of the prior row. Full per-attempt history stays queryable, matching LOOP-04's "every attempt... persisted" literally, and preserves the `uq_role_exec_attempt` constraint's meaning.
- **D-06:** `Run.qa_developer_iterations` and `Run.quality_gate_iterations` are independent counters, each incremented immediately before its own bounced dispatch (QA-FAIL increments `qa_developer_iterations` before re-dispatching Developer; gate-FAIL increments `quality_gate_iterations` before re-dispatching Developer) and checked independently against `retry.qa_developer_max_iterations` / `retry.quality_gate_max_iterations`. Exhausting either cap alone sends the run to `FAILED`, matching the two distinct config keys already scaffolded in `RetryConfig` — neither counter is folded into the other.

### Feedback payload to Developer
- **D-07:** QA's structured issues (`Verdict.issues`: severity/criterion/description) and the gate's actual failure output (per-command exit code/stdout/stderr from `verification/quality_gate.json`) reach the Developer's next attempt through a durable artifact file, read by the existing `ContextBuilder` (Phase 4) — not injected in-memory. A QA-FAIL's issues are available via QA's own `verdict.json` (already an existing output); a gate-FAIL's detail is `verification/quality_gate.json` (GATE-04's destination, D-01). Because these are ordinary durable artifacts, the same crash/resume story as every other artifact applies: a process dying between the bounce decision and Developer's next dispatch loses nothing — a fresh process reads the same files. — **Reversibility:** reversible — swapping the artifact-read mechanism for something else later touches only `ContextBuilder` and role config, no persisted schema.
- **D-08:** `.dark-factory/roles/DEVELOPMENT.yaml` gains explicit new declared inputs for the feedback files (QA's `verdict.json` issues and/or `verification/quality_gate.json`), consistent with CFG-02's config-driven-inputs pattern rather than a Python-hardcoded "is this a bounced attempt?" special case in `ContextBuilder`. On attempt 1 (no bounce yet) these inputs are simply absent, resolved the same way any not-yet-produced optional input already is.

### Gate command execution semantics
- **D-09:** All commands in `quality_gate.commands` run regardless of earlier failures — never stop at first failure. `verification/quality_gate.json` records every command's result; the gate PASSes only if every command exits 0. This gives the Developer maximum information per bounce (e.g. both a lint failure and a test failure surface together), spending fewer of the limited `quality_gate_max_iterations` round-trips discovering problems one at a time.
- **D-10:** Each gate command reuses `Settings.worker_timeout_seconds` (the single generous timeout knob Phase 7 D-03 already established) via `shell_execute`'s existing `timeout` parameter — no new dedicated `quality_gate_timeout_seconds` setting. One "Dark Factory is waiting on a subprocess" timeout concept, not two.
- **D-11:** `verification/quality_gate.json` shape:
  ```json
  {
    "status": "PASS",
    "commands": [
      {"command": "...", "exit_code": 0, "stdout": "...", "stderr": "...", "timed_out": false}
    ]
  }
  ```
  Mirrors `shell.execute`'s existing `ShellResult` fields (`exit_code`/`stdout`/`stderr`/`timed_out`) directly, one entry per command. `status` is a computed property folded from the per-command results (PASS iff every `exit_code == 0` and no `timed_out`), never hand-set — the same "never a special case, always derived" discipline `Verdict.computed_status` already uses.

### Claude's Discretion
- Exact `EventType` names/payload shapes for `QUALITY_GATE_STARTED`/`PASSED`/`FAILED` (D-02) and for the exhaustion reason on `RUN_FAILED` (e.g. `{"reason": "quality_gate_max_iterations_exhausted", "attempts": N}`) — left to planning, following existing `run_events` payload conventions.
- Exact filenames/field names for the QA-issues-to-Developer feedback artifact (D-07/D-08) — whether it's QA's existing `verdict.json` read directly or a Developer-facing copy/transform of it — left to planning, as long as it's a durable artifact `ContextBuilder` resolves via config.
- Where exactly in `runner.py` the iteration-cap check (D-04/D-06) sits relative to the existing QA branch and hook-dispatch code — left to planning.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §"Independent Quality Gate" (GATE-01..04) and §"Bounded Feedback Loops" (LOOP-01..04) — the eight requirements this phase implements.
- `.planning/ROADMAP.md` §"Phase 9: Independent Quality Gate & Bounded Feedback Loops" — goal, success criteria, invariants ("verdicts from exit codes and machine JSON, never prose").

### Already-scaffolded config and schema (consume, don't re-add)
- `src/dark_factory/config/repo_config.py:72-87` — `QualityGateConfig.commands`, `RetryConfig.qa_developer_max_iterations`/`quality_gate_max_iterations`, already wired into `RepoConfig` and parsed from `.dark-factory.yaml`.
- `src/dark_factory/persistence/models.py:31-34,135-140` — `Run.qa_developer_iterations`/`quality_gate_iterations` columns, explicitly documented as "D-19 columns, never derived... stored now, enforced in Phase 9."

### QA verdict model
- `src/dark_factory/domain/artifacts.py:199-245` — `Verdict`, `VerdictCriterionResult`, `VerdictIssue`, `computed_status` (PASS iff all criteria PASS and no blocking issue), schema-enforced status/computed_status consistency.
- `src/dark_factory/domain/status.py:64-89` — `VerdictStatus`, `IssueSeverity` enums.
- `.dark-factory/roles/QA.yaml` — QA's declared outputs (`test_report.json`, `verdict.json`) and the `collect_test_results` after-hook (currently a stub at `src/dark_factory/actions/builtins.py:136-138`, explicitly commented "until Phase 9 (GATE-04)").

### Shell execution
- `src/dark_factory/tools/env.py:150-233` — `shell_execute(*, command, cwd, role, timeout, env_var_name, value)` and `ShellResult(exit_code, stdout, stderr, timed_out)`; callable directly by orchestrator code, no `ToolRegistry` involvement needed for orchestrator-invoked (non-role) calls.

### Orchestrator dispatch and lifecycle
- `src/dark_factory/orchestrator/lifecycle.py:58-118` — `transition(state, signal, pipeline)`, the single place next-position is computed; `ROLE_FAILED` currently goes unconditionally to `RunStatus.FAILED` (lines 110-111) — this is where `ROLE_BOUNCED` handling is added.
- `src/dark_factory/domain/signal.py:22-40` — `Signal` enum and `signal_from_result`.
- `src/dark_factory/orchestrator/runner.py:644-1092` — `_run_current_role`; hook dispatch (~line 808), transition computation (~line 1020), failure branch (~lines 1042-1057) — where the gate step and iteration-cap check are wired in.
- `src/dark_factory/events/catalog.py` — existing `EventType` catalog (`ROLE_FAILED`/`RUN_FAILED`/`CAPABILITY_DENIED` precedent) for the new gate event types.

### Artifact durability pattern
- `src/dark_factory/actions/builtins.py:84-138` — `collect_diff` (the `after:` hook pattern writing under `verification/` via `resolve_under_run_root`, riding the role's own artifact commit) and the `collect_test_results` stub that is this phase's actual landing spot for GATE-04.
- `src/dark_factory/artifacts/store.py:50-68` — `write_artifact_text`, the general artifact-write pattern for comparison.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `shell_execute()` (`tools/env.py`) — directly reusable for gate commands; already handles timeout + process-group kill + captured stdout/stderr/exit_code in exactly the shape D-11 wants.
- `RepoConfig.quality_gate` / `RepoConfig.retry` — schema and defaults already exist; nothing to add to `.dark-factory.yaml` parsing.
- `Run.qa_developer_iterations` / `Run.quality_gate_iterations` columns — already migrated, currently unused; this phase is their first consumer.

### Established Patterns
- Verdicts are always schema-computed, never hand-set (`Verdict.computed_status`) — D-11's gate `status` follows the same discipline.
- Narrow, purpose-built `EventType`s over overloading existing ones when a fact is independently auditable (Phase 6's `CAPABILITY_DENIED`) — followed for the new gate events (D-02).
- Role inputs/outputs are always config-declared (CFG-02), never Python-hardcoded exceptions — followed for the Developer feedback inputs (D-08).
- Single mutation path: `lifecycle.transition()` is the only place a run's next position is computed — followed by routing the bounce decision through a new `Signal` rather than a runner.py side-branch (D-04).

### Integration Points
- The gate step's call site sits in `runner.py` right after QA's own transition is computed but before the pipeline advances past QA — this is the phase's core new wiring point.
- `ContextBuilder` (Phase 4) is the integration point for feeding QA-issues/gate-output artifacts into the Developer's next `RoleContext` (D-07/D-08).

</code_context>

<specifics>
## Specific Ideas

No UI/UX-style specific references — this is an internal orchestration phase. The concrete decisions above (exact JSON shape for `quality_gate.json`, the `ROLE_BOUNCED` signal, separate per-edge iteration counters) are the specifics.

</specifics>

<deferred>
## Deferred Ideas

None raised during this discussion — the conversation stayed within phase scope.

### Reviewed Todos (not folded)
None — `.planning/todos/pending/` had no phase-9-matching entries at discussion time.

</deferred>

---

*Phase: 9-Independent Quality Gate & Bounded Feedback Loops*
*Context gathered: 2026-09-22*
