# Phase 7: Claude Code — the First Real Worker - Context

**Gathered:** 2026-09-20
**Status:** Ready for planning

<domain>
## Phase Boundary

`ClaudeCodeWorker` becomes a real, functional `CodingWorker` adapter: it spawns
the `claude` CLI non-interactively for a role attempt, normalizes its output to
`WorkerResult`, resumes a paused role through the CLI's native session id, and
is killed by process-group timeout if it hangs — with its output streamed to a
durable log file rather than buffered. The orchestrator must remain unable to
tell it apart from `FakeWorker`: the shared `CodingWorker` contract-test suite
runs against both, and no worker name may leak outside `workers/`/`config/`.

Out of scope (belongs to Phase 8): `CopilotWorker`, `HermesWorker`, and any
cross-worker independence proof beyond what the contract suite + registry
already give for free.

</domain>

<decisions>
## Implementation Decisions

### Clarifying-question signal (real NEEDS_INPUT)
- **D-01:** Because Claude Code's headless `-p` invocation cannot interactively pause mid-run, `ClaudeCodeWorker` derives `NEEDS_INPUT` from a convention marker in the CLI's own final result text — the role's instruction prompt tells Claude to end its turn with a fixed marker line (e.g. a line starting `NEEDS_INPUT:`) followed by the question, instead of guessing when it needs a human decision. The adapter parses the CLI's `result` text for that marker: present → `NEEDS_INPUT` with the question extracted from it; absent → `COMPLETED`/`FAILED` as usual. This is adapter-only parsing with no new CLI feature dependency, and is what makes SC2's pause/resume path reachable through the real adapter, not only via `FakeWorker` configured with a script. — **Reversibility:** reversible — the marker format lives entirely inside `ClaudeCodeWorker`'s parsing logic; changing it later touches one adapter module and the role instruction text, no persisted schema.

### Credential handling
- **D-02:** `Settings` gains a new optional credential field for the Claude Code CLI (e.g. `anthropic_api_key: SecretStr | None`, mirroring `github_token`'s existing optional shape) — not required at process startup. Its absence only surfaces when a run actually tries to invoke a `claude-code` role: `ClaudeCodeWorker.execute()`/`resume()` raise a clear, typed error naming the missing env var before spawning anything. This keeps every environment that only ever runs `fake`-worker pipelines (including CI's existing test suite) working with no new required configuration, consistent with the existing `github_token: SecretStr | None = None` precedent. The value flows to the subprocess exclusively through `build_worker_env(role, env_var_name=..., value=...)` (Phase 6 D-09) — never through `os.environ.copy()` or any other channel. — **Reversibility:** reversible — a later phase can tighten this to eager validation without touching persisted state; it's a Settings-field/validation-timing choice only.

### Timeout policy
- **D-03:** A single `Settings.worker_timeout_seconds` field (env-overridable int, generous default — planning discretion on the exact number, but explicitly generous rather than tight, since engineering roles like DEVELOPMENT can run long) governs every worker subprocess call this phase. This mirrors the existing `lease_ttl_seconds`/`lease_heartbeat_seconds` precedent (Phase 2) — one plain `Settings` knob, not a new per-role config key or a hardcoded constant. Per-role timeout overrides in `.dark-factory.yaml` are explicitly deferred, not adopted this phase. — **Reversibility:** reversible — a per-role override can be layered on top of this single knob later (falling back to it) without breaking existing callers.

### Log streaming target
- **D-04:** A worker subprocess's streamed output is written under the run's existing artifact tree, in a new `logs/<role>/` subdirectory alongside `artifacts/<role>/` under `.dark-factory/runs/<run_id>/` — raw stdout/stderr text, one file per attempt (e.g. `attempt-<N>.stdout.log` / `attempt-<N>.stderr.log`). This reuses the existing `run_root()` path helper and the same crash/resume durability model artifacts already have, with no new persistence concept, no new schema, and no dependency on structlog's configured sink for what is fundamentally a per-run worker transcript. — **Reversibility:** reversible — a later phase can add a structured-JSON-lines format or a live-tail feature on top of these files without changing where they live.

### Claude's Discretion
- Exact `NEEDS_INPUT:` marker text/format and how multi-line questions are extracted from the CLI result text — left to planning, as long as it's unambiguous against ordinary prose Claude might otherwise produce.
- Exact `Settings` field name for the Claude Code credential (e.g. `anthropic_api_key` vs. another name) and the exact typed error class/message raised on missing credential at first use.
- Exact default value of `Settings.worker_timeout_seconds` — generous is the stated intent (engineering roles run long); planning picks a concrete number (e.g. minutes, not seconds-scale).
- Exact log file naming/rotation scheme within `logs/<role>/` beyond "one file per attempt, raw stdout/stderr" — e.g. whether stdout and stderr are separate files or interleaved.
- Whether `resume()` shares the same timeout value as `execute()` or could differ — no signal from the user that these should diverge; default to sharing one `Settings.worker_timeout_seconds` value unless research surfaces a concrete reason not to.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WORK-04, WORK-07, HITL-04, HITL-05, QUAL-02, QUAL-04 (this phase's full requirement set)
- `.planning/ROADMAP.md` §"Phase 7: Claude Code — the First Real Worker" — goal, five success criteria, and the invariant ("the native-resume vs. context-reconstruction branch lives inside the adapter; adapters never import orchestrator, workflow or persistence code")

### Worker contract this phase implements against
- `src/dark_factory/workers/base.py` — the `CodingWorker` ABC (`execute`/`resume`/`capabilities`) every adapter implements
- `src/dark_factory/domain/worker.py` — `WorkerResult`, `WorkerResultStatus`, `WorkerCapabilities`, `ArtifactRef` — the exact normalized shape `ClaudeCodeWorker` must produce; note `WorkerResult`'s `model_validator` already rejects a `NEEDS_INPUT` with no `questions`
- `src/dark_factory/workers/fake.py` — `FakeWorker`, the reference implementation the contract suite already pins; its `native_resume`/`session_id` capability flags and artifact-synthesis behavior are what a real adapter must not diverge from semantically
- `src/dark_factory/workers/registry.py` — `WorkerRegistry`, `default_registry`; the `"claude-code"` name already resolves to a `_NotYetImplementedWorker` placeholder this phase replaces with a real factory registration
- `tests/contract/test_coding_worker_contract.py` — `WORKER_FACTORIES`; Phase 7 appends `ClaudeCodeWorker` to this list, which is what proves QUAL-02
- `src/dark_factory/context/builder.py` — `RoleContext`, the exact object `execute(context)`/`resume(context, previous, answer)` receive (run_id, role, worker, attempt, task, answer, instructions, inputs, baseline_docs, examples, constraints, tools, permissions, outputs, artifacts_dir)

### Credential boundary & subprocess patterns to reuse
- `src/dark_factory/tools/env.py` — `build_worker_env()`, `WORKER_ENV_ALLOWLIST`, `shell_execute()` — the exact allowlist-from-empty-dict credential-boundary function (Phase 6 D-09) `ClaudeCodeWorker` must call when spawning `claude`, and a direct template for the `Popen` + `start_new_session=True` + process-group-kill-on-timeout pattern this phase reuses for the `claude` subprocess itself
- `src/dark_factory/config/settings.py` — `Settings`, `known_secret_values()` — where D-02's new credential field and D-03's `worker_timeout_seconds` field are added; `known_secret_values()` already walks `model_fields` for `SecretStr` so the new credential field is covered automatically
- `.claude/CLAUDE.md` §"Invoking the agent CLIs" — the exact non-interactive invocation pattern (`claude -p "<prompt>" --output-format json`, parse `result`/`session_id`/`total_cost_usd`; `--allowedTools`/`--permission-mode` for native tool restriction; `Popen.communicate(timeout=...)` + `os.killpg` on `TimeoutExpired`)

### Native tool restriction — already decided in Phase 6, applies here
- `src/dark_factory/tools/native.py` — `NATIVE_TOOL_CONTRACT`, `NativeToolGrant` — the concrete per-capability `--allowedTools`/`--permission-mode` translation table this phase's adapter must actually implement at spawn time (this table was Phase 6's *design contract*, currently unconsumed by any runtime code — `ClaudeCodeWorker` is its first real consumer)
- `.planning/phases/06-tools-permissions-the-credential-boundary/06-CONTEXT.md` D-02 — states plainly that `ToolRegistry`/the MCP transport governs Dark-Factory-initiated calls only and cannot intercept a real CLI worker's own native tools; native restriction must come from the translation table above, not from wiring Claude Code to the Phase 6 MCP server

### Existing subprocess/log durability precedent
- `src/dark_factory/artifacts/paths.py` — `run_root()` — the path helper D-04's new `logs/<role>/` subdirectory is placed alongside `artifacts/<role>/` under
- `tests/support/subprocess_runner.py` — `child_env()`, cross-process test technique (`spawn`/`popen`/`run_id_from_stdout`/`wait_for`) — the established pattern for proving a real subprocess-spawning adapter's behavior across a genuine OS process boundary

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_worker_env()` + `shell_execute()` (`tools/env.py`) — the credential-bounded subprocess pattern (allowlist env, `start_new_session=True`, `communicate(timeout=...)`, `os.killpg` on `TimeoutExpired`) `ClaudeCodeWorker` mirrors for spawning `claude` itself, rather than reinventing subprocess plumbing.
- `NATIVE_TOOL_CONTRACT` (`tools/native.py`) — a fully specified per-capability `--allowedTools`/`--permission-mode` translation table already written for exactly this adapter to consume; no new design work needed to derive the mapping.
- `WorkerRegistry.register("claude-code", ...)` — the registration point already exists and is exercised by config validation (`"claude-code" in registry`); this phase only needs to swap the placeholder factory for a real one.
- `RoleContext` (`context/builder.py`) — already carries everything a prompt-construction step needs (`instructions`, `inputs`, `baseline_docs`, `examples`, `task`, `answer`, `tools`, `outputs`) with no orchestrator/persistence coupling required by the adapter itself.

### Established Patterns
- `frozen=True, extra="forbid"` on every pydantic boundary model — any new domain model this phase introduces (e.g. a parsed Claude CLI result shape, if one is needed as an intermediate) should match.
- Explicit-allowlist-from-empty-dict for subprocess environments (`git_env()`, `build_worker_env()`) — a third application would be a red flag; this phase reuses `build_worker_env()` directly rather than writing a fourth allowlist.
- `SecretStr` + `known_secret_values()` walking `model_fields` — the established mechanism by which any new `Settings` credential field is automatically covered by redaction with zero extra wiring.
- Adapters never import orchestrator/workflow/persistence code (this phase's own roadmap invariant) — `ClaudeCodeWorker` takes `RoleContext` as a plain data object and returns `WorkerResult`; it must not reach into `dark_factory.orchestrator` or `dark_factory.persistence`.

### Integration Points
- `src/dark_factory/workers/registry.py` — `default_registry.register("claude-code", ...)` swaps from `_NotYetImplementedWorker` to a real `ClaudeCodeWorker` factory.
- `src/dark_factory/config/settings.py` — new `anthropic_api_key` (or similar) and `worker_timeout_seconds` fields.
- `tests/contract/test_coding_worker_contract.py` — `WORKER_FACTORIES` list gains `ClaudeCodeWorker`.
- A new `src/dark_factory/workers/claude_code.py` (or similar) module — the adapter itself, exempt from the worker-name-leak guard by virtue of living under `workers/` (already an exempt top-level directory in `tests/unit/test_no_worker_name_leak.py`).
- A new `logs/<role>/` writer, likely alongside or inside the existing `artifacts/` package given it shares `run_root()`.

</code_context>

<specifics>
## Specific Ideas

No particular naming beyond what's captured in the decisions above. The user consistently chose the recommended option at every branch point in this discussion: a prompt-level marker convention for NEEDS_INPUT (no new CLI/schema dependency), lazy credential validation at first real use (no new required startup config), a single generous global timeout knob mirroring the existing lease-TTL precedent, and reusing the existing artifact-tree durability model for streamed logs rather than inventing a new persistence concept.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Per-role timeout overrides in `.dark-factory.yaml` and a structured (JSON-lines) log format were both explicitly named as possible future refinements during discussion, not requested now — captured as `Claude's Discretion` / decision rationale above, not as a backlog list. `CopilotWorker`/`HermesWorker` and cross-worker independence proofs remain Phase 8's scope per ROADMAP.md, unchanged by this discussion.

### Reviewed Todos (not folded)
None — `.planning/todos/pending/` is empty (STATE.md: "Pending Todos: None yet").

</deferred>

---

*Phase: 7-Claude Code — the First Real Worker*
*Context gathered: 2026-09-20*
