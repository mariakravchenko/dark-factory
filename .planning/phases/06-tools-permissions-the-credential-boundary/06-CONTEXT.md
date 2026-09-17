# Phase 6: Tools, Permissions & the Credential Boundary - Context

**Gathered:** 2026-09-17
**Status:** Ready for planning

<domain>
## Phase Boundary

A role receives exactly the capabilities its configuration grants and nothing more, and a worker subprocess can never reach an infrastructure credential. Concretely: (1) a real, callable `ToolRegistry.invoke()` API enforces deny-by-default on every capability call, backed by real implementations for the 7 capabilities current role YAMLs actually grant (`repo.read/search/write/write_tests`, `shell.execute`, `artifacts.read/write`); (2) a `build_worker_env()` allowlist builder proves a worker subprocess environment never carries `DATABASE_URL`/`GITHUB_TOKEN`/unrelated inherited keys; (3) a minimal MCP transport adapter exposes the registry's capabilities to a compatible worker, isolated behind an optional dependency and an import-graph guard.

Out of scope: real per-adapter native-tool restriction (e.g. Claude Code's `--allowedTools` flag construction) — Phase 6 defines the translation contract a future adapter must follow, but doesn't build or wire it; that's Phase 7. `git.status/diff/history` and `github.issue/comments.read` capabilities — registered when a phase actually grants them to a role (Phase 9/10). A full-featured MCP server matching every possible capability — Phase 6 ships a minimal skeleton proven with a fake/test client. Real Claude Code / Copilot / Hermes MCP integration — Phase 7+.

</domain>

<decisions>
## Implementation Decisions

### Capability enforcement model
- **D-01:** `ToolRegistry.invoke(role, capability, ...)` is a real, callable Python API — not a declarative-only permission validator. Deny-by-default is checked on every call. This is what makes SC1 ("a role invoking a capability it was not granted is denied by the registry") literally true, and what makes the MCP transport (D-13) meaningful: MCP becomes another transport calling the same `invoke()`.
- **D-02:** The registry governs Dark-Factory-initiated tool calls and MCP-exposed calls; it does not intercept a real CLI worker's own native filesystem/shell tools (Dark Factory can't literally do that for an external process). Phase 6 additionally documents (design-level, not implemented) the per-worker translation contract a future adapter must follow to derive its native-tool restriction from a role's `tools:` grants (e.g. a documented mapping to Claude Code's `--allowedTools`) — **Reversibility:** reversible — this is a documentation/design-contract decision, not code; Phase 7 can refine the mapping without touching Phase 6's registry.
- **D-03:** Existing artifact I/O (`store_role_artifacts` / `collect_role_artifacts` from Phase 4, currently unconditional) is migrated onto `registry.invoke('artifacts.read'/'artifacts.write', ...)` using each role's granted `tools:` list — giving real production call sites so SC1's deny-by-default is provable end-to-end, not only via a direct unit test, for `artifacts.read`/`artifacts.write`.
- **D-04:** Only the 7 capabilities current role YAMLs actually grant are registered and implemented this phase (`repo.read/search/write/write_tests`, `shell.execute`, `artifacts.read/write`). `git.status/diff/history` and `github.issue.read`/`github.comments.read` are **not** registered yet — they land when Phase 9/10 actually grants them to a role. TOOL-02's extensibility (SC3: "a new capability is added... without editing any role executor") is proven with a synthetic test capability, not a real future one.

### Denial event & failure shape
- **D-05:** A denied `registry.invoke()` call always fails the role attempt immediately — reuses the exact Phase 4/5 failure shape (persisted `FAILED` `role_execution` + `run_events` error entry + immediate `FAILED` transition), the same pattern already used for schema-violation (04-CONTEXT.md D-09) and write-scope-violation (05-CONTEXT.md D-13) failures. No new failure pathway, no "denied but continue" branch.
- **D-06:** `registry.invoke()` is session-free (consistent with WR-01 — actions never open a DB session) and raises a typed `CapabilityDeniedError` on denial; `runner.py`'s mutation-path code catches it alongside the existing `except GitError` block (D-16 pattern from Phase 5) and produces the standard `FAILED` shape.
- **D-07:** A denial gets its own `CAPABILITY_DENIED` `EventType` — a distinct, auditable fact SC1 explicitly names, following the existing pattern of narrow purpose-built event types (`QUESTION_CREATED`, `RUN_PAUSED`, etc. added in Phase 2). This deviates from Phase 5's own no-new-event-type precedent (D-16's git-push failure), which was a deliberate choice there to avoid growing failure vocabulary for a *transient* failure; a capability denial is a *contract violation*, closer in kind to the events Phase 2 already added.
- **D-08:** `CAPABILITY_DENIED` is emitted **in addition to** the usual `ROLE_FAILED`/`RUN_FAILED` events, not instead of them — `dark-factory status`/observability code needs zero special-casing to recognize "this run failed"; it just gets one extra informative event in the trail.

### Credential boundary — proving SEC-03 pre-Phase-7
- **D-09:** `build_worker_env(role, env_var_name: str, value: SecretStr | None)` is a generic, explicit-allowlist function mirroring `git_env()`/`child_env()` exactly (`PATH`, `HOME`, a temp `XDG_*`, plus only the named credential variable if a value is supplied; never `os.environ.copy()`). No new `Settings` fields this phase — the credential is an explicit caller-supplied parameter, mirroring D-16's git-push pattern (Phase 5) where `Settings.github_token` is read once by the caller and passed as a plain value into a config-ignorant package. Phase 7 adds `Settings.anthropic_api_key` (or similar) when `ClaudeCodeWorker` actually needs one — Phase 6 doesn't guess at a name that might not match.
- **D-10:** SC2 is proven by spawning a real OS subprocess (a tiny "dump `os.environ`" script, the same technique `tests/support/subprocess_runner.py` already uses from Phases 1–2) with `build_worker_env()`'s output and asserting `DATABASE_URL`/`GITHUB_TOKEN`/unrelated keys are absent. `FakeWorker` is not changed to spawn subprocesses — it stays in-process, documented as having no external call, per its existing contract. The credential-boundary function is proven standalone; Phase 7 wires `ClaudeCodeWorker` to actually call it when spawning `claude`.
- **D-11:** `shell.execute`'s real implementation runs the command via `subprocess.Popen` with `env=build_worker_env(role, ...)` — a genuine production call site proving SEC-03 through real code, not only the synthetic harness (D-10). No current pipeline role invokes it yet (Developer/QA are still `FakeWorker`), so it's exercised via direct tests today; the implementation itself is real and is reused unchanged once Phase 7+ roles actually shell out.

### MCP transport scope
- **D-12:** Phase 6 ships a minimal skeleton MCP adapter, not a full-featured server. It exposes the registered capabilities (D-04's 7 tools) via the official `mcp` SDK, enough for a test/fake MCP client to list and call them and observe the same deny-by-default behavior as direct `registry.invoke()`. No real Claude Code / Copilot / Hermes integration this phase.
- **D-13:** `mcp` is an **optional** dependency (a `uv`/`pyproject.toml` optional-dependencies group, e.g. `[project.optional-dependencies] mcp = [...]`), not a regular always-installed one — matching CLAUDE.md's own "the orchestrator must never import it on a core path" guidance literally: uninstalling the extra leaves the core fully functional, not just import-graph-clean. The dedicated MCP adapter test module is skipped when the extra isn't installed.
- **D-14:** SC5's "removing MCP entirely leaves the orchestrator fully functional" is proven by an import-graph guard test, mirroring the existing AST-based guards (`test_no_role_name_literal.py`, `test_orchestrator_no_live_config_read.py`) — asserting zero `mcp` imports anywhere on the core (non-adapter) import closure.
- **D-15:** The MCP adapter is a factory — `build_mcp_server(role, granted_tools)` — instantiated fresh per role invocation, with the role's grants baked in at construction. No session/auth negotiation, no per-call role-identity parameter. This mirrors the existing "nothing persists across role attempts unless it's a durable artifact" discipline (e.g. `RoleContext` built fresh per attempt in Phase 4's `ContextBuilder`).

### Claude's Discretion
- Exact `CapabilityDeniedError` message format and the fields carried on the `CAPABILITY_DENIED` event payload (role, capability, reason) — left to planning, as long as it's enough to answer "who tried what and was denied why" from the audit trail alone.
- Exact shape of the documented native-tool-restriction translation contract (D-02) — a docstring/module comment vs. a small typed mapping table — left to planning discretion as long as it's concrete enough for Phase 7 to implement without re-deriving the mapping from first principles.
- Exact synthetic test capability used to prove TOOL-02 extensibility (D-04) — implementation detail.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, SEC-01, SEC-03 (this phase's full requirement set)
- `.planning/ROADMAP.md` §"Phase 6: Tools, Permissions & the Credential Boundary" — goal, five success criteria, and the invariants ("worker environments are built up from an empty dict, never from `os.environ`"; "permission checks happen on every invocation and are never delegated to the worker")

### Existing domain/config contracts this phase extends
- `src/dark_factory/config/loader.py` — `RoleDefinition.tools: list[str]` (currently stored in the snapshot but unenforced, per its own docstring) and `RolePermissions` — this phase implements the enforcement D-01/D-04 makes real
- `.dark-factory/roles/*.yaml` — the actual `tools:` grants per role today (BA/ARCHITECTURE: read-only; DEVELOPMENT: `repo.read/search/write/write_tests`, `shell.execute`, `artifacts.read/write`; QA: `repo.read/search`, `artifacts.read/write`) — the ground truth for D-04's "register only what's granted today"
- `src/dark_factory/git/client.py` — `git_env()` / `GIT_ENV_ALLOWLIST` — the exact pattern `build_worker_env()` (D-09) mirrors for a different subprocess family
- `tests/support/subprocess_runner.py` — `child_env()` and the cross-process test technique D-10 reuses for the SC2 proof
- `src/dark_factory/git/diff.py` — the `GIT_ASKPASS` short-lived-helper credential-injection pattern from Phase 5 (D-16 in 05-CONTEXT.md); a precedent for injecting `shell.execute`'s worker credential without an argv/URL leak, if D-11's implementation needs it
- `src/dark_factory/artifacts/` — `store_role_artifacts` / `collect_role_artifacts` (Phase 4) — the call sites D-03 migrates onto `registry.invoke()`
- `src/dark_factory/actions/builtins.py` — module docstring explaining which actions are permanent no-ops vs. real hooks (the same convention any new tool-adapter code should follow if it needs a role-configurable hook)
- `src/dark_factory/persistence/mutations.py` / `orchestrator/runner.py` — the single mutation path and its existing `except GitError` block (D-16 pattern) that D-06 extends to catch `CapabilityDeniedError`
- `src/dark_factory/events/` — `EventType` catalog (Phase 1/2) — D-07 adds `CAPABILITY_DENIED` here, following the same enum-extension precedent as `QUESTION_CREATED`/`RUN_PAUSED`/`HUMAN_ANSWER_RECEIVED`/`RUN_RESUMED` (Phase 2)
- `src/dark_factory/config/settings.py` — `Settings` / `known_secret_values()` — D-09 deliberately does *not* add fields here this phase; any real worker-credential field is Phase 7's decision
- `tests/unit/test_single_mutation_path.py` and `tests/unit/test_no_role_name_literal.py` / `test_orchestrator_no_live_config_read.py` — the AST-guard test style D-14's MCP import-graph guard should follow
- `.planning/phases/05-isolated-workspace-git-lifecycle/05-CONTEXT.md` D-16 — the git-push credential-handling precedent (`GIT_ASKPASS`, no-new-event-type-for-transient-failure, explicit-parameter-not-Settings-field) that several Phase 6 decisions (D-06, D-09, D-11) explicitly follow or deliberately diverge from
- `.planning/phases/04-the-four-role-pipeline-artifact-handoffs/04-CONTEXT.md` D-09 — the schema-violation `FAILED` shape reused verbatim by D-05

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `git_env()` / `GIT_ENV_ALLOWLIST` (`git/client.py`) and `child_env()` (`tests/support/subprocess_runner.py`) — direct templates for `build_worker_env()`; the allowlist-from-empty-dict discipline already exists twice in this codebase, this phase is the third application.
- The `except GitError` catch block in `runner.py`'s mutation path (Phase 5, D-16) — the exact site `CapabilityDeniedError` handling (D-06) attaches alongside.
- `EventType` enum extension pattern (Phase 2: `QUESTION_CREATED` etc.) — direct template for adding `CAPABILITY_DENIED` (D-07).
- The Phase 4/5 `FAILED`-shape failure pattern (persisted `FAILED` role_execution + `run_events` error + immediate `FAILED` transition) — reused verbatim by D-05, no new pathway needed.

### Established Patterns
- Config validation fails loudly with typed errors before any run/row is created (`config/loader.py`) — any new `tools:` validation this phase adds (e.g. rejecting an unregistered capability name in role YAML) should follow the same fail-loud-at-config-load convention already used for `write_scope` glob validation.
- `frozen=True, extra="forbid"` on every pydantic boundary model — any new domain model this phase introduces should match.
- Actions/tools that touch mutation-path state never open a DB session (WR-01, enforced by `tests/unit/test_single_mutation_path.py`) — `ToolRegistry.invoke()` must stay session-free (D-06) for the same reason `ensure_clean_worktree`/`collect_diff` do.
- Per-attempt fresh construction, not shared mutable state — `RoleContext` is rebuilt every attempt (Phase 4); D-15 gives the MCP adapter the same discipline.

### Integration Points
- `orchestrator/runner.py` — where the `except GitError` block lives and where `CapabilityDeniedError` handling attaches (D-06); also the likely site for constructing `build_worker_env()` calls once a real worker needs one (Phase 7 concern, but the function itself ships now).
- `src/dark_factory/artifacts/` — `store_role_artifacts`/`collect_role_artifacts` call sites migrated onto `registry.invoke()` (D-03).
- A new `src/dark_factory/tools/` package (registry, capability implementations) and a new optional `src/dark_factory/mcp/` (or similar) adapter package, isolated per D-13/D-14.

</code_context>

<specifics>
## Specific Ideas

No particular naming beyond what's captured in the decisions above (`ToolRegistry`, `CapabilityDeniedError`, `CAPABILITY_DENIED`, `build_worker_env`) — user deferred exact identifiers/formats to Claude's discretion within the stated design. The user consistently chose the recommended ("You decide leans here") option at every branch point in this discussion, endorsing the mediated-invocation model, real production call sites over standalone-only proofs, and the generic/parameterized credential approach over adding speculative Settings fields.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Native-CLI tool restriction (`--allowedTools` wiring), `git.*`/`github.*` capability implementations, and full MCP server build-out were all explicitly identified as later-phase concerns during discussion (Phase 7, Phase 9/10, and "when a real MCP client exists" respectively) rather than raised as new capabilities — captured as scope boundaries in `<domain>` above, not as a backlog list.

### Reviewed Todos (not folded)
None — `.planning/todos/` had zero matches for Phase 6 (`todo.match-phase` returned `todo_count: 0`).

</deferred>

---

*Phase: 6-Tools, Permissions & the Credential Boundary*
*Context gathered: 2026-09-17*
