# Phase 9: Independent Quality Gate & Bounded Feedback Loops - Research

**Researched:** 2026-09-22
**Domain:** Orchestrator-internal control flow (Python), no new external services or packages
**Confidence:** HIGH for code-grounded mechanics (every claim below a `[VERIFIED: path:lines]` tag was read this session); MEDIUM/LOW for design choices CONTEXT.md left to planning

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** The quality gate is an orchestrator-only step, not a pipeline role. It is not added to `workflow.roles` and gets no `WorkerRegistry` entry, no `role_executions` row, and no worker of any kind. Once QA's role attempt transitions to `COMPLETED` with a PASS verdict, the orchestrator (in `runner.py`) directly invokes `shell_execute` for each `quality_gate.commands` entry, writes `verification/quality_gate.json`, and only then computes the transition to the next real role. *(See "Drift found" below — CONTEXT.md's phrase "right where the QA branch currently computes its transition" refers to a branch that does not exist; this research supplies the actual, role-name-literal-free insertion point.)*
- **D-02:** The gate's start/pass/fail are visible in the audit trail via new, narrow purpose-built `run_events` (e.g. `QUALITY_GATE_STARTED`, `QUALITY_GATE_PASSED`, `QUALITY_GATE_FAILED`), following Phase 6's `CAPABILITY_DENIED` precedent. `dark-factory status` can show gate attempts in the timeline even though there is no `role_executions` row for them.
- **D-03:** Gate commands run with `cwd` set to the run's existing worktree at HEAD — the same worktree `shell.execute` already uses for role work. No separate clone/worktree for gate isolation.
- **D-04:** A new `Signal.ROLE_BOUNCED` is added alongside `ROLE_COMPLETED`/`ROLE_FAILED`/`ROLE_NEEDS_INPUT` (`domain/signal.py`). `lifecycle.transition()` maps it to re-entering the Developer's position in the pipeline, instead of `RunStatus.FAILED`. The orchestrator decides `ROLE_BOUNCED` vs `ROLE_FAILED` by checking the relevant iteration counter against its config cap *before* choosing the signal for a QA-FAIL or gate-FAIL outcome: under cap → `ROLE_BOUNCED`; at/over cap → `ROLE_FAILED`. — **Reversibility:** one-way.
- **D-05:** On a bounce, both Developer and QA get a fresh `role_executions` row (`attempt = previous_attempt + 1`) each time they re-run — reusing the existing `_enter_role`/attempt-increment machinery from Phase 4, not an update-in-place of the prior row.
- **D-06:** `Run.qa_developer_iterations` and `Run.quality_gate_iterations` are independent counters, each incremented immediately before its own bounced dispatch and checked independently against `retry.qa_developer_max_iterations` / `retry.quality_gate_max_iterations`. Exhausting either cap alone sends the run to `FAILED`.
- **D-07:** QA's structured issues (`Verdict.issues`) and the gate's actual failure output (`verification/quality_gate.json`) reach the Developer's next attempt through a durable artifact file, read by the existing `ContextBuilder` — not injected in-memory. — **Reversibility:** reversible.
- **D-08:** `.dark-factory/roles/DEVELOPMENT.yaml` gains explicit new declared inputs for the feedback files, consistent with CFG-02's config-driven-inputs pattern. On attempt 1 (no bounce yet) these inputs are simply absent, resolved the same way any not-yet-produced optional input already is. *(See "Critical Mechanics Gap 2" below — no such "optional input" resolution exists today; this is new work, not reuse.)*
- **D-09:** All commands in `quality_gate.commands` run regardless of earlier failures — never stop at first failure. The gate PASSes only if every command exits 0.
- **D-10:** Each gate command reuses `Settings.worker_timeout_seconds` via `shell_execute`'s existing `timeout` parameter — no new dedicated timeout setting.
- **D-11:** `verification/quality_gate.json` shape:
  ```json
  {
    "status": "PASS",
    "commands": [
      {"command": "...", "exit_code": 0, "stdout": "...", "stderr": "...", "timed_out": false}
    ]
  }
  ```
  `status` is a computed property folded from per-command results (PASS iff every `exit_code == 0` and no `timed_out`), never hand-set.

### Claude's Discretion

- Exact `EventType` names/payload shapes for `QUALITY_GATE_STARTED`/`PASSED`/`FAILED` and for the exhaustion reason on `RUN_FAILED`.
- Exact filenames/field names for the QA-issues-to-Developer feedback artifact — whether it's QA's existing `verdict.json` read directly or a Developer-facing copy/transform.
- Where exactly in `runner.py` the iteration-cap check sits relative to the existing QA branch and hook-dispatch code.

### Deferred Ideas (OUT OF SCOPE)

None raised during discussion — GitHub issue intake and idempotent publishing (Phase 10), cross-machine/CI resume proof (Phase 11), and the observability/audit surface beyond this phase's own new events (Phase 12) are explicitly out of scope for Phase 9.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GATE-01 | After QA passes, Dark Factory independently runs `quality_gate.commands` in the repo environment | Architecture Patterns §"Recommended wiring"; `shell_execute` confirmed callable directly outside `ToolRegistry` |
| GATE-02 | The gate decision is based on command exit codes, not agent prose | D-11's `status` fold; `ShellResult.exit_code`/`timed_out` confirmed exact shape |
| GATE-03 | Developer/QA self-validation is never accepted as final truth | Satisfied by construction — gate always re-runs regardless of worker-reported success |
| GATE-04 | Gate result written to `verification/quality_gate.json` | `collect_diff`'s `verification/<file>` pattern (`resolve_under_run_root`) is the precedent to reuse; `collect_test_results` stub is the *named* landing spot but see the role-name-literal guard note below on whether to use it as an after-hook vs. inline orchestrator code |
| LOOP-01 | QA FAIL returns structured issues to Developer | **Critical Mechanics Gap 1**: nothing today reads `verdict.json` content to drive a transition — must be added |
| LOOP-02 | Gate FAIL returns actual failure output to Developer, QA re-evaluates, gate re-runs | Falls out for free from `_enter_role`'s existing attempt-increment dispatch (see Architecture Patterns) once `ROLE_BOUNCED` routes back to DEVELOPMENT |
| LOOP-03 | Iterations bounded by `retry.*_max_iterations`, checked before dispatch | `state.qa_developer_iterations`/`state.quality_gate_iterations` already on `RunState`; `apply_transition`'s `counter_increments` already implemented and unused |
| LOOP-04 | Exhaustion transitions to FAILED with every attempt/reason persisted | Reuse existing `ROLE_FAILED`/`RUN_FAILED` event pair, mirroring `_fail_role_before_worker`'s shape, with an added exhaustion-reason payload |

</phase_requirements>

## Summary

Phase 9's architectural decisions (D-01 through D-11) are sound and the two schema/column pieces they lean on (`RepoConfig.quality_gate`/`retry`, `Run.qa_developer_iterations`/`quality_gate_iterations`) are confirmed present and correctly named. But three of CONTEXT.md's canonical-ref pointers describe code that doesn't exist as described, and this research found **three load-bearing mechanics gaps** that the plan must close explicitly — none of which are hinted at in CONTEXT.md's Discretion section, and all of which are exercised the moment `.dark-factory/roles/QA.yaml`'s pipeline actually loops:

1. **There is no "QA branch" in `runner.py`.** `_run_current_role` is completely role-agnostic — no code anywhere reads `Verdict.computed_status`. Today, a QA worker returning `WorkerResultStatus.COMPLETED` advances the run straight to `RunStatus.COMPLETED` *regardless of `verdict.json`'s PASS/FAIL content* (`next_node` returns `None` for the last pipeline role, so `transition()`'s `ROLE_COMPLETED` branch goes straight to `COMPLETED`). Phase 4 deliberately deferred this exact gap to Phase 9 (self-documented in `tests/db/test_artifact_schema_violation_fails_role.py`'s own docstring and `04-RESEARCH.md`). Phase 9 must add the verdict-reading logic from scratch.
2. **`ContextBuilder`'s declared-input resolution has no "optional input" concept, and cannot resolve orchestrator-written verification files at all.** D-08's premise ("resolved the same way any not-yet-produced optional input already is") describes behavior that does not exist. `build_role_context` unconditionally resolves every declared `inputs` entry and lets `MissingArtifactContentError` propagate uncaught — which would crash Developer's very first attempt once `verdict.json` is added to its `inputs`, since QA (the producing role) is *downstream* of Developer and has no `COMPLETED` row yet on attempt 1. Separately, `verification/quality_gate.json` is not any role's declared `output`, so it cannot be resolved through the existing `_producing_role`/`ArtifactReference` lookup at all — `ArtifactReference.role_execution_id` is a required, non-nullable column, and D-01 gives the gate no `role_executions` row to attach one to.
3. **A repo-wide AST guard test forbids any of the six `RunStatus` role-name strings (`"BA"`, `"ARCHITECTURE"`, `"DEVELOPMENT"`, `"QA"`, `"VERIFYING"`, `"PUBLISHING"`) anywhere in `src/dark_factory/orchestrator/**` or `workflows/pipeline.py`, outside docstrings** (`tests/unit/test_no_role_name_literal.py`). This directly rules out the naive reading of D-01 ("wire the gate in where the QA branch computes its transition" via `if node.name == "QA":`) and directly rules out hardcoding `"DEVELOPMENT"` as the bounce target in `lifecycle.transition()`. Both must be computed structurally instead (detailed below) — this is mechanically required, not a style preference.

The good news more than offsets this: `apply_transition` **already has** a fully-wired, currently-unused `counter_increments: Mapping[str, int]` parameter restricted to exactly `{"qa_developer_iterations", "quality_gate_iterations"}`, applied atomically under the same `with_for_update` row lock every other mutation uses — LOOP-03's "checked and incremented safely" requirement needs zero new locking code, just a call-site argument. And the entire "Developer/QA get a fresh `role_executions` row on bounce" requirement (D-05) **falls out for free** from the existing `_advance_once` dispatch logic (`_enter_role` fires whenever `state.current_role != state.latest_execution.role`, computing `attempt = MAX(attempt)+1` in SQL) — no new code is needed there at all, as long as `lifecycle.transition()`'s new `ROLE_BOUNCED` branch correctly moves `current_role` backward.

**Primary recommendation:** Implement the QA-verdict check and the gate as one new inline block inside `_run_current_role`, gated on `next_node(pipeline, node.name) is None` (i.e. "this is the last pipeline role") rather than on a role-name comparison; add a `previous_node()` helper to `workflows/pipeline.py` mirroring `next_node()` so `lifecycle.transition()`'s `ROLE_BOUNCED` branch computes its target structurally; extend `ContextBuilder`/`build_role_context` with an explicit optional-input mechanism before adding anything to `DEVELOPMENT.yaml`'s `inputs:`; and `shlex.split()` each `quality_gate.commands` string before calling `shell_execute` (its `command` parameter is a `Sequence[str]` argv list and explicitly rejects a bare string).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| QA verdict interpretation (PASS/FAIL routing) | Orchestrator (`runner.py`) | Domain (`domain/artifacts.Verdict`) | Verdict schema/computed_status already lives in the domain layer (Phase 4); the orchestrator must be the only place that *acts* on it (ORCH-05) |
| Quality gate command execution | Orchestrator (`runner.py`) | Tools (`tools/env.shell_execute`) | D-01: gate is orchestrator-owned, not role-owned; reuses the existing credential-bounded shell tool as a plain function call |
| Bounce/fail signal computation | Orchestrator — pure (`orchestrator/lifecycle.py`) | Domain (`domain/signal.Signal`) | `transition()` is the single place a run's next position is computed (ORCH-06); must stay import-free of persistence and role-name-literal-free |
| Iteration-cap bookkeeping | Durable state (Neon `runs` columns via `persistence/mutations.apply_transition`) | Orchestrator (reads `RunState`) | D-19 discipline: counters are columns, incremented only inside the one mutation path, never derived |
| Feedback artifact delivery to Developer | Context assembly (`context/builder.py`) | Artifacts (`artifacts/store.py`) | ORCH-04: roles hand off through durable artifacts only; `ContextBuilder` is the sole assembly point |
| Gate audit trail | Durable state (`run_events` via `EventType`) | — | Matches Phase 6's `CAPABILITY_DENIED` precedent: an auditable fact with no `role_executions` row still needs its own event |

## Standard Stack

No new external packages. Everything Phase 9 needs is already a project dependency or the Python 3.12 standard library.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `shlex` (stdlib) | 3.12 | Split each `quality_gate.commands` config string into an argv list before calling `shell_execute` | `shell_execute(command: Sequence[str], ...)` explicitly rejects a bare string [VERIFIED: src/dark_factory/tools/env.py:161-209] (`isinstance(command, str)` raises `InvalidShellCommandError`), but `.dark-factory.yaml`'s `quality_gate.commands` entries are single strings like `"uv run pytest -q"` [VERIFIED: .dark-factory.yaml:16-19]. `shlex.split()` is the standard POSIX-shell-compatible way to convert one into the other with no new dependency. |
| `dark_factory.tools.env.shell_execute` | in-repo | Run each gate command | Already exists, already credential-bounded, already timeout+process-group-kill safe [VERIFIED: src/dark_factory/tools/env.py:161-233]; confirmed callable directly by orchestrator code with no `ToolRegistry` involvement — "This function performs no permission decision of its own... invoking it directly, bypassing the registry, simply runs the command" [VERIFIED: src/dark_factory/tools/env.py:185-190]. |
| `dark_factory.domain.artifacts.Verdict` | in-repo | Parse QA's `verdict.json` to get `computed_status` | Already exists, already schema-enforces declared-vs-computed agreement [VERIFIED: src/dark_factory/domain/artifacts.py:199-245]. Reuse directly — do not hand-roll a second PASS/FAIL fold. |

### Supporting

None beyond the above — this phase adds control flow to existing modules, not new libraries.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `shlex.split()` per configured command string | Change `QualityGateConfig.commands` to `list[list[str]]` | Cleaner typing, but breaks the already-shipped `.dark-factory.yaml` shape (`commands: ["uv run pytest -q", ...]`) [VERIFIED: .dark-factory.yaml:16-19] and the canonical-ref instruction to "consume, don't re-add" the already-scaffolded config schema. `shlex.split()` is the zero-schema-change option. |
| Inline orchestrator block in `_run_current_role` for the gate | An `ActionRegistry` `after:` hook (`collect_test_results`, already reserved and named for exactly this in `QA.yaml`'s `after:` list) | See "Critical Mechanics Gap 3" below — hooks run *unconditionally* regardless of signal and cannot themselves change the `Signal` the transition uses, so a hook alone cannot drive `ROLE_BOUNCED`/`ROLE_FAILED`. It could still *write* `verification/quality_gate.json`'s content-execution side effect, with the actual bounce/fail decision made back in `_run_current_role` reading the file the hook wrote — a legitimate split, but adds a hook mutating the signal-relevant decision the *runner* needs to make right after, doubling the code paths that need to agree. Recommendation: keep it all inline in `runner.py`, and repoint `collect_test_results`'s stub comment / `QA.yaml`'s `after:` list once the plan decides which way it goes (flagged as an open question below, not resolved here). |

**Installation:** none — no new packages.

**Version verification:** N/A — no new packages to verify against a registry.

## Package Legitimacy Audit

Not applicable. This phase installs no external packages (confirmed above: `shlex` is stdlib, everything else is already in the repository's dependency tree). No `gsd_run query package-legitimacy check` invocation is needed.

## Architecture Patterns

### Canonical-Reference Verification (drift check against CONTEXT.md)

| Canonical ref | CONTEXT.md claim | Verified this session | Verdict |
|---|---|---|---|
| `config/repo_config.py:72-87` | `QualityGateConfig.commands`, `RetryConfig.*_max_iterations` already wired | Confirmed at lines 72-108 [VERIFIED: src/dark_factory/config/repo_config.py:72-108] — `QualityGateConfig.commands: list[str]`, `RetryConfig.qa_developer_max_iterations: int = 3`, `RetryConfig.quality_gate_max_iterations: int = 2` | ✅ Accurate |
| `persistence/models.py:31-34,135-140` | `Run.qa_developer_iterations`/`quality_gate_iterations` columns, "D-19 columns" | Confirmed at lines 31-34 (docstring) and 135-140 (columns) [VERIFIED: src/dark_factory/persistence/models.py:31-34,135-140] — both `Integer, nullable=False, server_default=sa.text("0")`, already carried by migration `0001_walking_skeleton.py` (no separate later migration exists) | ✅ Accurate. Also: **no new Alembic migration needed** — the columns shipped in the very first revision. |
| `domain/artifacts.py:199-245` | `Verdict`, `computed_status`, schema-enforced agreement | Confirmed at lines 199-245 [VERIFIED: src/dark_factory/domain/artifacts.py:199-245] | ✅ Accurate |
| `domain/status.py:64-89` | `VerdictStatus`, `IssueSeverity` enums | Confirmed at lines 64-89 [VERIFIED: src/dark_factory/domain/status.py:64-89] | ✅ Accurate |
| `.dark-factory/roles/QA.yaml` outputs, `collect_test_results` stub | QA outputs `test_report.json`/`verdict.json`; stub at builtins.py:136-138 | Confirmed — `outputs: [test_report.json, verdict.json]` [VERIFIED: .dark-factory/roles/QA.yaml:52], stub is exactly lines 136-138 [VERIFIED: src/dark_factory/actions/builtins.py:136-138] | ✅ Accurate |
| `tools/env.py:150-233` — `shell_execute`/`ShellResult` | Callable directly, no `ToolRegistry` needed | Confirmed at lines 143-233 [VERIFIED: src/dark_factory/tools/env.py:143-233] — but see Standard Stack: `command` must be a pre-split `Sequence[str]`, not a bare string | ✅ Accurate, with the `shlex` caveat above |
| `orchestrator/lifecycle.py:58-118`, "`ROLE_FAILED` currently goes unconditionally to `RunStatus.FAILED` (lines 110-111)" | This is the exact spot `ROLE_BOUNCED` gets added | Confirmed exact line numbers: `if signal is Signal.ROLE_FAILED: return RunStatus.FAILED, role, state.current_step` is lines 110-111 verbatim [VERIFIED: src/dark_factory/orchestrator/lifecycle.py:110-111] | ✅ Accurate |
| `domain/signal.py:22-40` | `Signal` enum, `signal_from_result` | Confirmed lines 22-41 [VERIFIED: src/dark_factory/domain/signal.py:22-41] | ✅ Accurate |
| `orchestrator/runner.py:644-1092` — `_run_current_role`; "hook dispatch (~line 808), transition computation (~line 1020), failure branch (~lines 1042-1057)" | Where the gate step and iteration-cap check are wired in | Function spans exactly 644-1125 [VERIFIED: src/dark_factory/orchestrator/runner.py:644-1125]. `def _run_hooks` is exactly line 808. `next_status, next_role, next_step = transition(...)` is exactly line 1020. The `elif signal is Signal.ROLE_FAILED:` arm starts at line 1042 but **extends to line 1067** (not 1057) because it also handles the `capability_denial` prepend [VERIFIED: src/dark_factory/orchestrator/runner.py:1042-1067] | ⚠️ Minor drift — failure-branch end line is 1067, not 1057. Immaterial to the plan but note it so a plan step citing "~1042-1057" isn't confused when the real arm runs a few lines longer. |
| "right where the QA branch currently computes its transition" (D-01 prose) | Implies an existing per-role/QA-specific branch in `runner.py` | **No such branch exists.** `_run_current_role` is entirely role-agnostic — confirmed via `grep -n "QA" src/dark_factory/orchestrator/runner.py` returning zero hits, and by reading the full function body [VERIFIED: src/dark_factory/orchestrator/runner.py:644-1125] | ❌ **Drift.** This is Critical Mechanics Gap 1 below — flagged, not silently resolved. |

### Critical Mechanics Gap 1 — nothing reads `verdict.json` content today

`signal_from_result` maps **only** `WorkerResult.status` to a `Signal` [VERIFIED: src/dark_factory/domain/signal.py:38-41] (`quote`: `"""def signal_from_result(result: WorkerResult) -> Signal:\n    return _RESULT_STATUS_TO_SIGNAL[result.status]"""`). A QA worker that reports `WorkerResultStatus.COMPLETED` produces `Signal.ROLE_COMPLETED` regardless of what `verdict.json` says. Since `QA` is configured as the last pipeline role [VERIFIED: .dark-factory.yaml:16] (`roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]`), `lifecycle.transition()`'s `ROLE_COMPLETED` branch finds `next_node(pipeline, "QA") is None` and returns `RunStatus.COMPLETED` directly [VERIFIED: src/dark_factory/orchestrator/lifecycle.py:100-108]. **A run with a FAILing `verdict.json` reaches `COMPLETED` today**, unconditionally. This is not an oversight to work around quietly — Phase 4 explicitly deferred it: `tests/db/test_artifact_schema_violation_fails_role.py`'s own module docstring states verbatim: *"D-06, recorded here verbatim (04-CONTEXT.md): within Phase 4's scope the run advances past QA regardless of verdict PASS or FAIL... The FAIL -> Developer bounce is Phase 9's bounded feedback loop."* [VERIFIED: tests/db/test_artifact_schema_violation_fails_role.py:9-15]. Phase 9 is where this gets built, from nothing — it is the phase's actual headline mechanism, and CONTEXT.md's decisions (D-04/D-06) describe *how to route once you know PASS/FAIL* but not *how you find out*.

**Where the parsed `Verdict` comes from:** `collect_role_artifacts` (already called earlier in `_run_current_role`, at the point `artifact_writes` is populated [VERIFIED: src/dark_factory/orchestrator/runner.py:921-934]) already schema-validates `verdict.json` against the `Verdict` model internally [VERIFIED: src/dark_factory/artifacts/validation.py:49-54,109-116] (`"verdict.json": Verdict` dispatch table) but **returns only `list[ArtifactReferenceWrite]`** (path/checksum metadata), never the parsed model instance [VERIFIED: src/dark_factory/artifacts/validation.py:58-128]. The new gate logic must independently re-read the file (`read_artifact_text(run_dir, path)` where `path` comes from the matching `artifact_writes` entry whose `.type == "verdict.json"`) and re-parse it (`Verdict.model_validate(json.loads(text))`) to obtain `.computed_status`. This is a small, cheap re-read (the file was just written this same attempt) — not a design smell, just a fact to know before writing the plan's task list.

### Critical Mechanics Gap 2 — `ContextBuilder` has no "optional input" concept

`build_role_context` resolves every declared `inputs` filename unconditionally and lets failure propagate:

```python
inputs = [
    _resolve_input(session, repo_root, run_id, state, filename)
    for filename in role_def.get("inputs", [])
]
```
[VERIFIED: src/dark_factory/context/builder.py:254-257]

`_resolve_input` calls `_producing_role(state, filename)` (raises `ArtifactContractError` if no role in the snapshot declares `filename` as an output [VERIFIED: src/dark_factory/context/builder.py:149-165]) then `_latest_completed_execution(session, run_id, producing_role)`, and raises `MissingArtifactContentError` if that role has no `COMPLETED` row yet [VERIFIED: src/dark_factory/context/builder.py:167-192]. Neither exception is caught anywhere between there and `_run_current_role`'s `build_role_context` call, which happens **before** the worker is even invoked [VERIFIED: src/dark_factory/orchestrator/runner.py:802-806].

Two concrete consequences for D-08:
1. **`verdict.json` as a DEVELOPMENT input would crash Developer's first-ever attempt.** DEVELOPMENT is *upstream* of QA in the pipeline (`[BA, ARCHITECTURE, DEVELOPMENT, QA]`). If `DEVELOPMENT.yaml`'s `inputs:` list names `verdict.json`, then on Developer's attempt 1 (before QA has ever run), `_producing_role` still resolves to `"QA"` (found in the snapshot, regardless of position), but `_latest_completed_execution(session, run_id, "QA")` returns `None` → `MissingArtifactContentError` → the whole run fails before Developer's worker is ever called, on every single run, not just a bounce. This is the opposite of D-08's stated intent and must be fixed with new code, not configuration.
2. **`verification/quality_gate.json` cannot be resolved through this mechanism at all**, optional or not: it is never declared as any role's `outputs` (it's written directly by orchestrator code per D-01, with no `role_executions` row to own it), so `_producing_role` raises `ArtifactContractError` unconditionally, and even if it didn't, `ArtifactReference.role_execution_id` is a required non-nullable column [VERIFIED: src/dark_factory/persistence/models.py:283-303] with no row to attach it to.

**This is a genuine open design point, not something this research should silently resolve** (see Open Questions). Two viable directions:
- (a) Add an explicit optional-input marker to the resolution path (e.g., catch `MissingArtifactContentError` for inputs the role config flags as optional, or catch it unconditionally and simply omit the entry from `RoleContext.inputs`), plus a **second, distinct resolution path** for orchestrator-written `verification/*` files that bypasses `_producing_role`/`ArtifactReference` entirely (a direct `read_artifact_text(run_root, "verification/quality_gate.json")` call, tolerant of the file not existing yet).
- (b) Give the gate step a synthetic `ArtifactReference` anyway, attached to QA's own `role_execution_id` (the gate always runs immediately after QA's attempt in the same call), which would let it ride the *existing* `_resolve_input` path unmodified if `quality_gate.json` were also declared as one of QA's `outputs`. This keeps `ContextBuilder` completely untouched but stretches D-01's "no `role_executions` row is involved" framing slightly (the row already exists — QA's own — so this doesn't violate D-01's actual constraint, only its prose), and requires deciding whether writing an `artifacts` row for orchestrator-generated content (not a worker-reported one) is consistent with ART-01/ART-03's spirit.

Either way, `_resolve_input`'s current "any missing input crashes the whole role" behavior needs at least an escape hatch before `DEVELOPMENT.yaml`'s `inputs:` list can safely grow.

### Critical Mechanics Gap 3 — the role-name-literal guard forbids the obvious wiring

`tests/unit/test_no_role_name_literal.py` walks every file under `src/dark_factory/orchestrator/` and `src/dark_factory/workflows/pipeline.py` via `ast` and fails if any string literal equals one of `{"BA", "ARCHITECTURE", "DEVELOPMENT", "QA", "VERIFYING", "PUBLISHING"}` outside a docstring [VERIFIED: tests/unit/test_no_role_name_literal.py:1-75]. This is an active, currently-passing guard (Phase 3/7 provenance, "ORCH-03 guard: the pipeline is data from the snapshot, not code"). It directly forbids:
- `if node.name == "QA": run_gate()` anywhere in `runner.py`
- `if role == "DEVELOPMENT":` anywhere in `runner.py`
- A literal `"DEVELOPMENT"` return value inside `lifecycle.py`'s new `ROLE_BOUNCED` branch

**Structural, guard-compliant alternative (recommended):**

1. Detect "this is the terminal quality checkpoint" via `next_node(pipeline, node.name) is None` — already the exact predicate the existing code uses to decide whether to emit `RUN_COMPLETED` [VERIFIED: src/dark_factory/orchestrator/runner.py:1038-1041] (`if next_status is RunStatus.COMPLETED:`). This generalizes "after QA" to "after whichever role the config puts last," which is both guard-compliant and more correct under this project's own config-driven-pipeline discipline (ORCH-02/03) — QA is only "last" because `.dark-factory.yaml` currently says so.
2. Add `previous_node(pipeline, role) -> RoleNode | None` to `workflows/pipeline.py`, mirroring the existing `next_node` exactly:
   ```python
   def previous_node(pipeline: Pipeline, current_role: str) -> RoleNode | None:
       """Return the node before ``current_role``, or ``None`` when it is the first one."""
       idx = pipeline.index_of(current_role)
       preceding = idx - 1
       if preceding < 0:
           return None
       return pipeline.nodes[preceding]
   ```
   Then `lifecycle.transition()`'s new arm:
   ```python
   if signal is Signal.ROLE_BOUNCED:
       target = previous_node(pipeline, role)
       if target is None:
           raise IllegalTransitionError(
               f"{status.value} has no earlier role to bounce a signal to"
           )
       return RunStatus(target.name), target.name, pipeline.index_of(target.name)
   ```
   This mirrors the existing `ROLE_COMPLETED` arm's `RunStatus(following.name)` pattern exactly [VERIFIED: src/dark_factory/orchestrator/lifecycle.py:100-108] and contains no role-name literal.
3. `verdict.json`/`quality_gate.json` filename strings are **not** in the guard's forbidden set (it only matches the six `RunStatus` values) — hardcoding those filenames in `runner.py` (as `collect_role_artifacts`'s own `MACHINE_ARTIFACT_MODELS` dict already does [VERIFIED: src/dark_factory/artifacts/validation.py:49-55]) is fine and matches existing style.

### Recommended wiring inside `_run_current_role`

Insert after the existing `enforce_write_scope` block (ends at line 1018) and before `transition()` is called (line 1020) [VERIFIED: src/dark_factory/orchestrator/runner.py:1004-1020]:

```python
# NEW: only when this attempt is still ROLE_COMPLETED after every existing
# post-worker check, and only for the pipeline's terminal role (config-driven,
# no role-name literal -- see RESEARCH "Critical Mechanics Gap 3").
if signal is Signal.ROLE_COMPLETED and next_node(pipeline, node.name) is None:
    verdict_write = next(
        (w for w in artifact_writes if w.type == "verdict.json"), None
    )
    if verdict_write is not None:
        verdict_text = read_artifact_text(run_dir, verdict_write.path)
        verdict = Verdict.model_validate(json.loads(verdict_text))

        if verdict.computed_status is VerdictStatus.FAIL:
            if state.qa_developer_iterations >= qa_max:
                signal = Signal.ROLE_FAILED
                outcome = {**outcome, "error": "qa_developer_max_iterations_exhausted"}
            else:
                signal = Signal.ROLE_BOUNCED
                counter_increments = {"qa_developer_iterations": 1}
        else:
            gate_result = _run_quality_gate(work_dir, run_dir, commands, timeout)
            if gate_result.status is not VerdictStatus.PASS:  # or a dedicated GateStatus
                if state.quality_gate_iterations >= gate_max:
                    signal = Signal.ROLE_FAILED
                    outcome = {**outcome, "error": "quality_gate_max_iterations_exhausted"}
                else:
                    signal = Signal.ROLE_BOUNCED
                    counter_increments = {"quality_gate_iterations": 1}
            # else: signal stays ROLE_COMPLETED, existing code below proceeds unchanged
```

Config reads (`qa_max`, `gate_max`, `commands`) come from `state.workflow` directly — **never** re-import `dark_factory.config.loader`/`RepoConfig` into `runner.py`. `_role_definition` already reads role config the identical way (`state.workflow["roles"]`) [VERIFIED: src/dark_factory/orchestrator/runner.py:159-183], and `build_role_context` already reads `state.workflow.get("quality_gate")` the same way for its `constraints` field [VERIFIED: src/dark_factory/context/builder.py:262-267]. So: `state.workflow.get("retry", {}).get("qa_developer_max_iterations", 3)` and `state.workflow.get("quality_gate", {}).get("commands", [])`. This also keeps `tests/unit/test_orchestrator_no_live_config_read.py`'s AST closure guard green, since that guard forbids `dark_factory.config.loader` (not `dark_factory.config.repo_config`, and not raw dict reads) transitively reachable from `runner.py`/`lifecycle.py`/`answers.py`/`workflows/pipeline.py` [VERIFIED: tests/unit/test_orchestrator_no_live_config_read.py:1-95].

Then extend the existing signal-dispatch block (currently `if ROLE_COMPLETED / elif ROLE_FAILED / elif ROLE_NEEDS_INPUT / else raise`, lines 1023-1088 [VERIFIED: src/dark_factory/orchestrator/runner.py:1023-1088]) with a new `elif signal is Signal.ROLE_BOUNCED:` arm. Recommended shape, matching the project's existing "reuse the identical shape" discipline (the same phrase appears at every prior failure-branch addition — D-07/D-08 capability-denial, D-12/13/14 write-scope, D-09 schema violation):
- `re_status = _ROLE_COMPLETED` (`"COMPLETED"`) — **not** a new status string. The worker genuinely completed; only the *run-level* routing differs. This also matters structurally: `_latest_completed_execution`'s `_resolve_input` lookup filters on `RoleExecution.status == "COMPLETED"` [VERIFIED: src/dark_factory/context/builder.py:118-131] — a bounced QA attempt must remain visible to that filter so Developer's next attempt can actually read `verdict.json`'s content per D-08's intent.
- `re_result = outcome` (the worker's own result, same as the `ROLE_COMPLETED` arm).
- New events: at minimum one gate/verdict-specific event (see Open Questions on exact naming) — do not reuse `ROLE_FAILED`/`RUN_FAILED` for a bounce; those specifically mean "the run is dead," which a bounce is not.
- Pass `counter_increments={"qa_developer_iterations": 1}` or `{"quality_gate_iterations": 1}` into the same `apply_transition(...)` call already being made at line 1092 [VERIFIED: src/dark_factory/orchestrator/runner.py:1092-1113] — `apply_transition` already accepts and atomically applies this parameter under its `with_for_update` row lock [VERIFIED: src/dark_factory/persistence/mutations.py:253-364] (`quote`: `"""_INCREMENTABLE_COUNTERS = frozenset({"qa_developer_iterations", "quality_gate_iterations"})"""` at line 78-80, and `"""for name, delta in increments.items(): setattr(run, name, getattr(run, name) + delta)"""` at lines 351-352). **No new locking pattern is needed** — this is the single most valuable simplification this research found: LOOP-03's "checked before dispatch" requirement is satisfied by reading `state.qa_developer_iterations`/`quality_gate_iterations` (already on `RunState` [VERIFIED: src/dark_factory/persistence/repositories.py:104-105,180-181]) before choosing the signal, and the increment itself piggybacks on the transition commit that's already happening.

### Why D-05 needs zero new code

`_advance_once`'s dispatch is entirely data-driven [VERIFIED: src/dark_factory/orchestrator/runner.py:355-374]:
```python
if state.status is RunStatus.CREATED:
    return _enter_first_role(...)
if state.latest_execution is None or state.latest_execution.role != state.current_role:
    return _enter_role(...)   # inserts attempt = MAX(attempt)+1 for (run_id, current_role) in SQL
return _run_current_role(...)
```
Once `lifecycle.transition()`'s `ROLE_BOUNCED` arm sets `runs.current_role = "DEVELOPMENT"` (via `apply_transition`'s `next_current_role`), the *next* `advance()` call sees `state.latest_execution.role == "QA" != state.current_role == "DEVELOPMENT"` and automatically routes to `_enter_role`, which inserts a fresh `role_executions` row for DEVELOPMENT with `attempt = MAX(attempt)+1` computed in SQL [VERIFIED: src/dark_factory/persistence/mutations.py:381-401]. When Developer later re-completes and the pipeline advances forward to QA again, the identical mechanism gives QA its own fresh `attempt = MAX(attempt)+1` row too. **D-05 is satisfied by the existing `_enter_role`/`_advance_once` code, unmodified**, as a direct consequence of `ROLE_BOUNCED` being "just another `current_role` change" from this dispatcher's point of view.

### `quality_gate.json` write pattern

Follow `collect_diff`'s exact precedent [VERIFIED: src/dark_factory/actions/builtins.py:84-116]:
```python
destination = resolve_under_run_root(run_dir, "verification/quality_gate.json")
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(gate_result.model_dump_json(), encoding="utf-8")
```
using the already-imported `resolve_under_run_root` (already imported into `runner.py` transitively is *not* confirmed — `builtins.py` imports it from `dark_factory.artifacts.paths`; `runner.py` would need the same import, which is a plain module already imported elsewhere in the codebase, not a new dependency).

### Test patterns to reuse

- **Pure `lifecycle.transition()` unit tests:** `tests/unit/test_lifecycle.py` uses a local `@dataclass(frozen=True) class _FakeState` (no DB, no persistence import) [VERIFIED: tests/unit/test_lifecycle.py:41-48] and parametrizes `(status, current_role, current_step, signal, pipeline, expected)`. Add `Signal.ROLE_BOUNCED` cases here, plus an "illegal pair" case for bouncing from the pipeline's first role (where `previous_node` returns `None`).
- **`EventType`/`Signal` enum member-count guards:** `tests/unit/test_domain_enums.py::test_event_type_has_exactly_twelve_members_with_the_phase_two_five_and_six_types` currently asserts `len(list(EventType)) == 12` [VERIFIED: tests/unit/test_domain_enums.py:114-121] — **must be updated** to the new count once Phase 9's events are added, following the file's own established pattern of one `test_event_type_contains_the_*` membership test plus one exact-count test per phase. `Signal` has no equivalent pinned-count test today — none to update.
- **Full-pipeline db tests:** `tests/db/test_four_role_pipeline.py` and `tests/db/test_artifact_schema_violation_fails_role.py` are the established idiom (`start_run` + `drive` against real PostgreSQL, `pytestmark = [pytest.mark.db, pytest.mark.usefixtures("use_fake_secrets")]`, a config tree built via `load_effective_config`, `cleanup_runs` teardown) [VERIFIED: tests/db/test_four_role_pipeline.py:1-65]. New Phase 9 db tests (bounce, gate-fail, exhaustion) should sit alongside these.
- **Scripted QA content:** `tests/support/fake_artifacts.py::_FOUR_ROLE_FILES["QA"]["verdict.json"]` currently hardcodes a PASS verdict [VERIFIED: tests/support/fake_artifacts.py:86-105]. Phase 9 tests need new fixture variants with a FAIL verdict (a `criterion_id` with `"result": "FAIL"` or a `"severity": "blocking"` issue) and, since `LazyFourRoleWorker._record` currently ignores `context.attempt` and always returns identical content [VERIFIED: tests/support/fake_artifacts.py:135-144], a **new attempt-aware fake worker** is needed to simulate "QA fails on attempt 1, passes on attempt 2" and "gate fails on attempt N, passes on attempt N+1" — this doesn't exist yet and is real new test-support work, not a reuse.
- **Retry-isolation precedent:** `tests/db/test_context_builder_retry_isolation.py` already constructs a two-attempt state by driving `apply_transition` directly with `RoleExecutionWrite(mode="insert")` twice for the same role, and its own docstring says this is "exactly the sequence Phase 9's real retry will eventually produce" [VERIFIED: tests/db/test_context_builder_retry_isolation.py:6-19]. Once Phase 9's real bounce exists, consider whether this test should be extended to drive the *actual* bounce path instead of hand-simulating it (not required, but worth a plan note).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PASS/FAIL fold over QA's criteria+issues | A second ad-hoc "is this really a pass" check in `runner.py` | `Verdict.computed_status` [VERIFIED: src/dark_factory/domain/artifacts.py:218-228] | Already schema-enforced to agree with the declared `status`; a second independent fold risks disagreeing with it |
| Gate command execution / timeout / process-group kill | A bespoke `subprocess.run` call in the gate logic | `dark_factory.tools.env.shell_execute` [VERIFIED: src/dark_factory/tools/env.py:161-233] | Already handles the credential-bounded env, `start_new_session=True` + `os.killpg` on timeout, and the exact `ShellResult` shape D-11 wants |
| Counter increment safety under concurrent access | A new advisory lock / `SELECT ... FOR UPDATE` call site for the two iteration columns | `apply_transition`'s existing `counter_increments` parameter [VERIFIED: src/dark_factory/persistence/mutations.py:253-364] | Already atomic under the same row lock (`with_for_update=True`) every other mutation uses; a second lock site would be a second, divergent concurrency mechanism |
| "Fresh attempt row per bounce" | New insert logic in the bounce-handling branch | The existing `_enter_role`/`_advance_once` dispatch [VERIFIED: src/dark_factory/orchestrator/runner.py:355-374] | Already computes `attempt = MAX(attempt)+1` in SQL for any `current_role` change, forward or backward — no special-casing needed |

**Key insight:** Phase 9's actual coding surface is much smaller than CONTEXT.md's eleven decisions suggest — most of the durable-state machinery (counters, attempt rows, locking) is already built and idle, waiting for this phase to call it. The real work is concentrated in three places: (1) parsing `verdict.json` and running the gate inside `_run_current_role`, (2) two small, literal-free helper additions (`previous_node`, the `ROLE_BOUNCED` arm) in `lifecycle.py`/`pipeline.py`, and (3) a genuinely new optional-input mechanism in `ContextBuilder`.

## Common Pitfalls

### Pitfall 1: Passing a bare command string to `shell_execute`
**What goes wrong:** `shell_execute(command="uv run pytest -q", ...)` raises `InvalidShellCommandError` immediately — every gate run fails before a single command executes.
**Why it happens:** `.dark-factory.yaml`'s `quality_gate.commands` entries are single strings [VERIFIED: .dark-factory.yaml:16-19], but `shell_execute`'s `command` parameter is typed `Sequence[str]` and explicitly checks `isinstance(command, str)` first and rejects it [VERIFIED: src/dark_factory/tools/env.py:161-209].
**How to avoid:** `shlex.split(cmd_string)` before calling `shell_execute`.
**Warning signs:** Every gate command reports `exit_code=None`... actually no — it would raise before returning a `ShellResult` at all, so the symptom is an uncaught `InvalidShellCommandError` crashing the whole role attempt on the very first gate run.

### Pitfall 2: Adding `verdict.json`/`quality_gate.json` to `DEVELOPMENT.yaml`'s `inputs:` before fixing `ContextBuilder`
**What goes wrong:** Developer's very first attempt (before QA has ever run) crashes with `MissingArtifactContentError`, on every run, not just a retry.
**Why it happens:** `_resolve_input` has no optional/absent-input concept today (Critical Mechanics Gap 2, above) — every declared input is mandatory and resolved eagerly, before the worker is even invoked.
**How to avoid:** Land the optional-input mechanism (or a Phase-9-specific escape hatch) in `context/builder.py` *before* or *in the same task as* the `DEVELOPMENT.yaml` config change — never land the config change alone.
**Warning signs:** A previously-green `tests/db/test_four_role_pipeline.py` (or any full-pipeline test) starts failing immediately after the `DEVELOPMENT.yaml` edit, even with no bounce anywhere in the test.

### Pitfall 3: Hardcoding a role-name string anywhere in `runner.py`/`lifecycle.py`/`pipeline.py` for the gate/bounce logic
**What goes wrong:** `tests/unit/test_no_role_name_literal.py` fails at CI/pre-commit time — a currently-green guard test regresses.
**Why it happens:** The obvious, CONTEXT.md-literal reading of D-01 ("wire the gate in where the QA branch computes its transition") and D-04 ("re-entering the Developer's position") both suggest writing `if node.name == "QA"` / a literal `"DEVELOPMENT"` return value — but there is no existing role-name branch to extend, and the codebase actively forbids introducing one.
**How to avoid:** Use `next_node(pipeline, node.name) is None` to detect the terminal role, and add `previous_node()` to `pipeline.py` for the bounce target — both structural, config-driven, and guard-compliant (see Critical Mechanics Gap 3).
**Warning signs:** `ast.walk`-based test failure naming the exact offending line — this guard's failure message is specific and easy to miss if the plan's own verification step doesn't run the full `unit` marker suite.

### Pitfall 4: Reusing `ROLE_FAILED`/`RUN_FAILED` events for a bounce
**What goes wrong:** The audit trail claims the run died (`RUN_FAILED`) when it actually just looped back to Developer — misleading for anyone reading `dark-factory events <run>` later, and semantically wrong for OBS-02's eventual "QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED" event vocabulary that Phase 12 is documented to still owe [VERIFIED: src/dark_factory/events/catalog.py:20-24] (`quote`: `"""The remainder listed in PROJECT.md -- ARTIFACT_CREATED, QA_FAILED/PASSED, QUALITY_GATE_FAILED/PASSED, PUBLISH_STARTED, PR_CREATED -- still arrive in Phase 12."""`).
**Why it happens:** `ROLE_FAILED`/`RUN_FAILED` is the closest existing shape to copy from, and the failure-branch code (lines 1042-1067) is right next to where the new logic gets added.
**How to avoid:** A distinct event (or pair) for the bounce itself, separate from the true-exhaustion `ROLE_FAILED`/`RUN_FAILED` pair used only when the cap is hit. See Open Questions — this is the same conflict flagged in the next pitfall.
**Warning signs:** N/A at test time (both events are structurally valid `EventType` members) — this is a semantic/design review catch, not a test failure.

### Pitfall 5 (flagged conflict, not a "pitfall" to silently fix): `events/catalog.py`'s own docstring says quality-gate events "still arrive in Phase 12"
`events/catalog.py`'s module docstring, written during an earlier phase, explicitly states that `QUALITY_GATE_FAILED/PASSED` (among others named in `PROJECT.md`'s full `OBS-02` event list) "still arrive in Phase 12" [VERIFIED: src/dark_factory/events/catalog.py:20-24], and `REQUIREMENTS.md`'s traceability table maps the whole of `OBS-02` to Phase 12 as `Pending` [VERIFIED: .planning/REQUIREMENTS.md:134,269]. CONTEXT.md's D-02 (a locked Phase 9 decision) directs adding `QUALITY_GATE_STARTED/PASSED/FAILED` **now**, in Phase 9. This is not necessarily wrong — a phase implementing a capability plausibly also gets to add the event that makes it auditable, and D-02 explicitly frames it as following the `CAPABILITY_DENIED` precedent from Phase 6, which *also* pre-empted part of `OBS-02`'s eventual list — but it is a genuine, un-flagged tension between two documents from different phases that the planner should resolve deliberately, not by accident:
- If Phase 9 adds `QUALITY_GATE_STARTED/PASSED/FAILED` now, the module docstring's "still arrive in Phase 12" comment becomes stale and **must be updated** in the same change (to say something like "QA_FAILED/PASSED... still arrive in Phase 12" if those specific two are *not* added now, or removed entirely if OBS-02's whole event list is now covered).
- Phase 12's own future plan should not attempt to re-add whichever events Phase 9 already shipped — worth a note in this phase's own summary/decision log for that future planner to find.

## Code Examples

### Reading QA's verdict back out for the routing decision

```python
# Source: this session's reading of collect_role_artifacts + read_artifact_text
# (src/dark_factory/artifacts/validation.py, src/dark_factory/artifacts/store.py)
from dark_factory.artifacts.store import read_artifact_text
from dark_factory.domain.artifacts import Verdict
from dark_factory.domain.status import VerdictStatus
import json

verdict_write = next((w for w in artifact_writes if w.type == "verdict.json"), None)
if verdict_write is not None:
    text = read_artifact_text(run_dir, verdict_write.path)
    verdict = Verdict.model_validate(json.loads(text))
    if verdict.computed_status is VerdictStatus.FAIL:
        ...  # bounce or fail, per iteration cap
```

### Splitting a configured gate command before executing it

```python
# Source: this session's reading of tools/env.py:shell_execute + .dark-factory.yaml
import shlex
from dark_factory.tools.env import shell_execute

commands: list[str] = state.workflow.get("quality_gate", {}).get("commands", [])
results = []
for cmd in commands:
    result = shell_execute(
        command=shlex.split(cmd),
        cwd=work_dir,
        role="quality_gate",  # not a RunStatus role value -- safe under the guard
        timeout=get_settings().worker_timeout_seconds,
    )
    results.append({"command": cmd, **result.model_dump()})
```

### `previous_node` addition to `workflows/pipeline.py` (mirrors existing `next_node`)

```python
# Source: this session's reading of src/dark_factory/workflows/pipeline.py:95-101
def previous_node(pipeline: Pipeline, current_role: str) -> RoleNode | None:
    """Return the node before ``current_role``, or ``None`` when it is the first one."""
    idx = pipeline.index_of(current_role)
    preceding = idx - 1
    if preceding < 0:
        return None
    return pipeline.nodes[preceding]
```

## State of the Art

Not applicable in the usual "library upgraded" sense — this is a closed, internal, already-well-established codebase pattern (SQLAlchemy 2.0 mutation-path discipline, pure-function state machine). The one relevant "old vs new" axis is internal to this project's own history:

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Verdict PASS/FAIL has no effect on the run's transition (Phase 4 deliberately shipped it this way) | Phase 9 makes `Verdict.computed_status` the actual routing input | This phase | Closes the ROLE-06 gap Phase 4 self-documented as deferred; this is the "verdicts... never prose" invariant becoming real for the first time |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Last pipeline role" (`next_node(...) is None`) is an acceptable, guard-compliant proxy for "this is QA" in the current `.dark-factory.yaml` shape | Architecture Patterns, Critical Mechanics Gap 3 | Low — it is provably equivalent given the current 4-role config; if a future config ever puts a non-QA-shaped role last, the gate logic would misfire, but that's out of this phase's scope to defend against |
| A2 | Direction (a) or (b) for resolving `verification/quality_gate.json` as a Developer-facing input is left open — this research recommends (a) as cleaner but does not mandate it | Critical Mechanics Gap 2 | Medium — whichever direction the plan picks changes `ContextBuilder`'s public surface differently; picking without discussion risks rework if Phase 10/12 later assume the other shape |
| A3 | `re_status = _ROLE_COMPLETED` ("COMPLETED") is the correct `role_executions.status` value for a bounced QA/gate-failed attempt (rather than a new status string) | Architecture Patterns, "Recommended wiring" | Medium — this is inferred from `_resolve_input`'s hardcoded `status == "COMPLETED"` filter [VERIFIED: src/dark_factory/context/builder.py:118-131], not from an explicit CONTEXT.md decision; if wrong, D-08's feedback-artifact delivery silently breaks (the input resolves to "producing role has no COMPLETED attempt" and crashes, per Pitfall 2) |
| A4 | Exact new `EventType` members and their count-guard update are left fully to planning per CONTEXT.md's Discretion section, but should be decided together with the Pitfall 5 conflict (Phase 12's docstring) rather than independently | Common Pitfalls, Pitfall 5 | Low — a naming choice, not a mechanics risk, but worth a deliberate decision rather than an incidental one |

## Open Questions

1. **How does `verification/quality_gate.json` reach `ContextBuilder` as a Developer-facing input (D-07/D-08)?**
   - What we know: it cannot use the existing `_producing_role`/`ArtifactReference` path unmodified (Critical Mechanics Gap 2).
   - What's unclear: whether the plan should add a distinct "verification-tree input" resolution path in `ContextBuilder`, or give the gate a synthetic `ArtifactReference` row tied to QA's own `role_execution_id`.
   - Recommendation: decide explicitly in planning (not execution) — this changes `RoleContext`'s shape and `ContextBuilder`'s public contract either way, and the choice should be visible in the plan's task list, not discovered mid-implementation.

2. **What role_executions status does a bounced attempt get, and does it need a distinct marker from a normal COMPLETED attempt?**
   - What we know: `_resolve_input` requires `status == "COMPLETED"` to find the row at all (Assumption A3).
   - What's unclear: whether observability (even deferred to Phase 12) will need to distinguish "QA completed and passed" from "QA completed and the run bounced" purely from `role_executions.status`, or whether that distinction lives entirely in the `result` JSONB payload / the new `run_events`.
   - Recommendation: keep `status = "COMPLETED"` (per A3) and put the FAIL/bounce distinction in the `result` payload and the new event, matching how `capability_denial` is threaded through `outcome`/events today without a new `role_executions.status` value.

3. **Should the gate write happen inline in `_run_current_role`, or via the already-reserved-and-named `collect_test_results` after-hook?**
   - What we know: `collect_test_results` is explicitly commented as "a genuine Phase 9 (GATE-04) placeholder" in both `QA.yaml` and `builtins.py`'s module docstring [VERIFIED: .dark-factory/roles/QA.yaml:36-37; src/dark_factory/actions/builtins.py:16-17]. But `after:` hooks run *unconditionally* regardless of the worker's signal [VERIFIED: src/dark_factory/orchestrator/runner.py:872] and cannot themselves influence the `Signal` used for the transition three lines later.
   - What's unclear: whether the plan should split "execute the gate commands and write the file" (a hook, matching the reserved name) from "read the file back and decide bounce/fail" (inline runner logic, reading what the hook wrote) — or just keep it all inline and leave `collect_test_results` a permanent no-op with an updated comment.
   - Recommendation: keeping it all inline is simpler and avoids a two-module split for one cohesive decision; if the plan does that, update `QA.yaml`'s comment and `builtins.py`'s module docstring to stop pointing at `collect_test_results` as the landing spot, so a future reader isn't misled by a stale reservation.

## Environment Availability

Not applicable — this phase adds no new external dependency (no new CLI, database, or service). Everything it touches (PostgreSQL via SQLAlchemy, `git`, the repo's own `quality_gate.commands` — e.g. `uv run pytest`, `uv run ruff check`) is already required and verified by earlier phases (1-8) and by this repository's own `.dark-factory.yaml`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 [VERIFIED: .planning/STATE.md project stack knowledge; confirmed live via `pyproject.toml` markers] |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`-equivalent `testpaths`/`markers` block) [VERIFIED: pyproject.toml:54-60] |
| Quick run command | `uv run python -m pytest -m "unit or contract" -q --tb=short` [VERIFIED: .planning/config.json workflow.test_command] |
| Full suite command | `uv run pytest -q` (includes `db`-marked tests, which require a reachable real PostgreSQL) [VERIFIED: pyproject.toml:56-58 marker definitions] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOOP-03/04 | `transition()` correctly computes `ROLE_BOUNCED` target and rejects an out-of-range bounce | unit | `uv run pytest tests/unit/test_lifecycle.py -x -q` | ❌ Wave 0 — extend existing file with new parametrized cases |
| GATE-01/02 | Gate commands actually execute via `shell_execute` with `shlex`-split argv, PASS iff all exit 0 | unit | new `tests/unit/test_quality_gate.py` (pure, injectable `shell_execute` or a scripted fake) | ❌ Wave 0 |
| GATE-04 | `verification/quality_gate.json` shape matches D-11 exactly | unit + db | new unit test for the pydantic model's computed `status`; db test asserting the file on disk after a real `drive()` | ❌ Wave 0 |
| LOOP-01 | QA-FAIL bounces to Developer with a fresh attempt row, verdict issues resolvable as Developer's next input | db | new `tests/db/test_qa_bounce.py`, following `tests/db/test_four_role_pipeline.py`'s idiom | ❌ Wave 0 |
| LOOP-02 | Gate-FAIL bounces to Developer, gate re-runs after QA re-evaluates | db | new `tests/db/test_quality_gate_bounce.py` | ❌ Wave 0 |
| LOOP-04 | Exhausting either cap transitions to FAILED with full attempt history + reason persisted | db | new `tests/db/test_iteration_cap_exhaustion.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest -m "unit or contract" -q --tb=short` (fast — covers `lifecycle.py`/`signal.py`/`pipeline.py` pure-function changes)
- **Per wave merge:** `uv run pytest -q` (full suite, including the new `db`-marked bounce/gate/exhaustion tests against real PostgreSQL)
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus a manual/human check that a real `quality_gate.commands` failure (e.g., temporarily breaking a test) actually bounces rather than silently completing — this project's own README-walkthrough-style human check precedent from Phases 1/2.

### Wave 0 Gaps
- [ ] `tests/unit/test_lifecycle.py` — extend with `Signal.ROLE_BOUNCED` legal/illegal parametrized cases (covers LOOP-03/04's transition correctness)
- [ ] `tests/unit/test_domain_enums.py` — update the `EventType` exact-count assertion (currently 12) once new members land
- [ ] `tests/support/fake_artifacts.py` — new FAIL-verdict fixture content and a new **attempt-aware** fake worker (current `LazyFourRoleWorker` ignores `context.attempt` and always returns identical content — cannot simulate "fails then passes")
- [ ] `tests/db/test_qa_bounce.py`, `test_quality_gate_bounce.py`, `test_iteration_cap_exhaustion.py` — new db-tier tests, no existing file covers this
- [ ] Framework install: none — pytest and all markers already configured

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase 9 has no auth surface |
| V3 Session Management | No | N/A |
| V4 Access Control | No — the gate is orchestrator-owned, not a role, so `ToolRegistry`/capability-grant checks (TOOL-03) don't apply to it by design (D-01) | N/A |
| V5 Input Validation | Yes | `quality_gate.commands` come from `.dark-factory.yaml` (repo-controlled, trusted config, already schema-validated by `RepoConfig` at run creation) — not user/agent-controlled input. `shell_execute` already avoids `shell=True` and passes an explicit argv list, so no shell-metacharacter injection risk exists even though the commands are now split with `shlex` rather than pre-split in config [VERIFIED: src/dark_factory/tools/env.py:173-179,211-221] |
| V6 Cryptography | No | N/A |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A malicious or buggy `quality_gate.commands` entry running with the same credential-bounded environment as role work | Elevation of Privilege (contained) | Already mitigated by the existing `build_worker_env` allowlist [VERIFIED: src/dark_factory/tools/env.py:44-67,82-116] — `DATABASE_URL`/`GITHUB_TOKEN`/worker credentials are never in the allowlist, so a gate command has the same credential boundary a role's own `shell.execute` already has. No new mitigation needed; just confirm the gate call site reuses `shell_execute` (which threads through `build_worker_env`) rather than raw `subprocess`. |
| A hung/runaway gate command (e.g. an infinite test loop) | Denial of Service | Already mitigated: `shell_execute`'s `timeout` + `os.killpg` process-group kill on `TimeoutExpired` [VERIFIED: src/dark_factory/tools/env.py:222-229] — reused unmodified per D-10 |
| Gate command failure output (stdout/stderr) leaking a secret into `verification/quality_gate.json` or the new `run_events` payload | Information Disclosure | `apply_transition`'s `redact()` call site already scrubs every JSONB payload it writes (`result`/`error`/event `payload`) against `Settings.known_secret_values()` [VERIFIED: src/dark_factory/persistence/mutations.py:29-33,319,354-361] — **but this only covers what's written through `apply_transition`.** `verification/quality_gate.json` itself is a **filesystem** write (via `resolve_under_run_root`, like `collect_diff`), which is **outside** `apply_transition`'s redaction call site entirely. If the run event payload for `QUALITY_GATE_FAILED` embeds the raw `stdout`/`stderr` (plausible, since D-07 wants "the actual command failure output" delivered), that embedded copy passes through `redact()`. But the **file on disk** does not, and neither does the copy `ContextBuilder` later reads back into `RoleContext` for Developer's next attempt (`read_artifact_text` performs no redaction [VERIFIED: src/dark_factory/artifacts/store.py:23-47]). This is a genuine SEC-01 exposure surface worth flagging explicitly: a test command that happens to print a secret to stdout on failure (e.g. a leaked API key in a stack trace) would land unredacted in `verification/quality_gate.json`, in the run's git-committed artifact tree (per Phase 5's D-09/D-11 commit-to-working-branch durability model), and in Developer's next prompt. **Recommend:** either redact `stdout`/`stderr` before writing `verification/quality_gate.json` (reusing `dark_factory.events.redaction.redact`/`scrub_known_values` outside its current `mutations.py`-only call site) or explicitly accept this as a known, scoped risk and note it in the plan — do not silently ship the file unredacted without a decision either way. |

## Sources

### Primary (HIGH confidence — every path:line cite above was opened with `Read` this session)
- `src/dark_factory/orchestrator/runner.py` (lines 1-1191) — `_run_current_role`, `_advance_once`, `_enter_role`, `_fail_role_before_worker`, imports
- `src/dark_factory/orchestrator/lifecycle.py` (full file, 119 lines) — `transition()`
- `src/dark_factory/domain/signal.py` (full file, 42 lines) — `Signal`, `signal_from_result`
- `src/dark_factory/domain/status.py` (full file, 90 lines) — `RunStatus`, `VerdictStatus`, `IssueSeverity`
- `src/dark_factory/domain/artifacts.py` (lines 160-246) — `TestReport`, `VerdictCriterionResult`, `VerdictIssue`, `Verdict`
- `src/dark_factory/config/repo_config.py` (full file, 109 lines) — `QualityGateConfig`, `RetryConfig`, `WorkflowConfig`, role-value legality
- `src/dark_factory/persistence/models.py` (lines 1-160, 283-303) — `Run`, `RoleExecution`, `ArtifactReference` columns
- `src/dark_factory/persistence/mutations.py` (full file, 512 lines) — `apply_transition`, `counter_increments`, `_write_role_execution`
- `src/dark_factory/persistence/repositories.py` (lines 1-115) — `RunState`, `load_run_state`
- `src/dark_factory/context/builder.py` (full file, ~290 lines) — `build_role_context`, `_resolve_input`, `_producing_role`
- `src/dark_factory/artifacts/validation.py` (full file, 129 lines) — `collect_role_artifacts`, `MACHINE_ARTIFACT_MODELS`
- `src/dark_factory/artifacts/store.py`, `src/dark_factory/actions/builtins.py`, `src/dark_factory/tools/env.py`, `src/dark_factory/workflows/pipeline.py`, `src/dark_factory/events/catalog.py`, `src/dark_factory/config/settings.py` (relevant excerpts)
- `.dark-factory.yaml`, `.dark-factory/roles/QA.yaml`, `.dark-factory/roles/DEVELOPMENT.yaml`, `.dark-factory/instructions/development.md`
- `tests/unit/test_lifecycle.py`, `tests/unit/test_no_role_name_literal.py`, `tests/unit/test_orchestrator_no_live_config_read.py`, `tests/unit/test_domain_enums.py` (full files)
- `tests/db/test_four_role_pipeline.py`, `tests/db/test_artifact_schema_violation_fails_role.py`, `tests/db/test_context_builder_retry_isolation.py` (docstrings + relevant excerpts)
- `tests/support/fake_artifacts.py`, `tests/support/config.py` (full files)
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/config.json`, `.planning/phases/04-*/04-RESEARCH.md`, `.planning/phases/04-*/04-VALIDATION.md`, `.planning/phases/04-*/04-CONTEXT.md`, `.planning/phases/04-*-PLAN.md`/`-SUMMARY.md` (grep + targeted reads)

### Secondary / Tertiary
None used — this phase required zero external documentation lookups (no new libraries, no external API). All findings are grounded in this repository's own source and its own prior-phase planning artifacts.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; every function cited was read this session
- Architecture: HIGH for what exists today (every claim is a direct `Read` citation); MEDIUM for the *recommended* new wiring (a sound, guard-compliant design grounded in the code, but not itself locked by CONTEXT.md — the planner should treat the code sketches as a strong starting point, not a mandate)
- Pitfalls: HIGH — all five are either a directly-reproducible code fact (guard test, missing-input crash, bare-string rejection) or a directly-quoted documentation conflict, not speculation

**Research date:** 2026-09-22
**Valid until:** No external expiry — this is an internal-codebase research pass; re-validate only if `runner.py`/`lifecycle.py`/`context/builder.py` change materially before this phase is planned/executed
