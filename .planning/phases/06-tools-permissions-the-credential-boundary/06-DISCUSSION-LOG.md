# Phase 6: Tools, Permissions & the Credential Boundary - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-17
**Phase:** 6-Tools, Permissions & the Credential Boundary
**Areas discussed:** Capability enforcement model, Denial event & failure shape, Proving the credential boundary pre-Phase-7, MCP transport scope

---

## Capability enforcement model

| Option | Description | Selected |
|--------|-------------|----------|
| Mediated invocation | `ToolRegistry.invoke(role, capability, ...)` is a real, callable Python API; deny-by-default checked on every call | ✓ |
| Declarative + post-hoc | Grants validated at load time, converted to CLI flags/env restrictions, re-checked post-hoc against the diff (Phase 5's write_scope pattern) | |
| Hybrid by capability type | Post-hoc for repo.write/write_tests, real mediated invoke() for shell.execute/github.*, declarative flags for read-only capabilities | |

**User's choice:** Mediated invocation.
**Notes:** User picked the recommended option (the only one that makes SC1's literal wording — "denied by the registry" — true, and that makes the MCP transport meaningful as another transport onto the same invoke()).

| Option | Description | Selected |
|--------|-------------|----------|
| Registry governs Dark Factory-initiated calls only; native CLI tools out of scope for Phase 6 | Restricting a real CLI's native tools (e.g. --allowedTools) is a Phase 7 adapter concern, not built or proven in Phase 6 | |
| Registry is the single source of truth; Phase 6 also defines the per-worker translation contract | Same runtime scope, but Phase 6 additionally documents the mapping a future adapter must follow | ✓ |

**User's choice:** Registry as single source of truth + documented (not implemented) translation contract.
**Notes:** Resolves the tension between "the registry denies" (SC1's wording) and the fact that an external CLI's own native filesystem/shell tools can't literally be intercepted by Dark Factory.

| Option | Description | Selected |
|--------|-------------|----------|
| Migrate existing artifact I/O onto registry.invoke() | store_role_artifacts/collect_role_artifacts (Phase 4) rewired to call through the registry, giving real production call sites for artifacts.read/write | ✓ |
| Registry proven standalone; no existing code retrofitted | SC1 proven only via direct tests calling registry.invoke(); adapters (Phase 7+) become first real callers | |

**User's choice:** Migrate existing artifact I/O onto registry.invoke().
**Notes:** Chosen so deny-by-default is provable end-to-end through genuine production usage, not only simulated tests.

| Option | Description | Selected |
|--------|-------------|----------|
| Register all 8 TOOL-01 capabilities now, stub the ungranted ones | git.*/github.* registered with stubs even though nothing grants them yet | |
| Register only what's granted today | Only the 7 capabilities current role YAMLs actually use; git.*/github.* land with Phase 9/10 | ✓ |

**User's choice:** Register only what's granted today.
**Notes:** TOOL-02 extensibility proven with a synthetic test capability instead.

---

## Denial event & failure shape

| Option | Description | Selected |
|--------|-------------|----------|
| Denial always fails the role immediately | Reuses the Phase 4/5 FAILED shape (persisted FAILED role_execution + run_events error + immediate FAILED transition) | ✓ |
| Denial raises an exception the caller decides how to handle | More flexible CapabilityDeniedError with catch-and-continue possible, but no current call site needs it | |

**User's choice:** Denial always fails the role immediately.
**Notes:** User picked the recommended option — a denied call is itself a bug signal, same severity as any other contract violation.

**Note on plumbing:** A follow-up question ("how does the denial reach the FAILED transition given WR-01") was posed with only one coherent option and was answered directly without a second AskUserQuestion round (the tool rejected a single-option question) — locked in as: `registry.invoke()` raises a typed `CapabilityDeniedError` (session-free); `runner.py`'s mutation path catches it alongside `GitError` (the existing D-16 pattern), producing the same FAILED shape.

| Option | Description | Selected |
|--------|-------------|----------|
| New CAPABILITY_DENIED event type | A distinct, auditable fact, per the existing narrow-event-type pattern (QUESTION_CREATED, RUN_PAUSED, etc.) | ✓ |
| Reuse ROLE_FAILED/RUN_FAILED with denial detail in the error payload | Matches Phase 5's D-16 no-new-event-type precedent for git-push failures | |

**User's choice:** New CAPABILITY_DENIED event type.
**Notes:** Explicitly diverges from Phase 5's D-16 no-new-event-type precedent — that precedent was about a *transient* failure (git push); a capability denial is a contract violation, closer to Phase 2's added event types.

| Option | Description | Selected |
|--------|-------------|----------|
| CAPABILITY_DENIED plus ROLE_FAILED/RUN_FAILED | Both persisted; observability code needs no special-casing | ✓ |
| CAPABILITY_DENIED replaces ROLE_FAILED | Avoids a "duplicate" failed signal but requires status/observability code changes | |

**User's choice:** CAPABILITY_DENIED plus ROLE_FAILED/RUN_FAILED (both fire).
**Notes:** User picked the recommended option.

---

## Proving the credential boundary pre-Phase-7

| Option | Description | Selected |
|--------|-------------|----------|
| Generic builder + synthetic subprocess-echo test harness | build_worker_env() mirrors git_env()/child_env(); SC2 proven by spawning a real "dump os.environ" subprocess | ✓ |
| Wire FakeWorker to optionally spawn a real subprocess for this proof | Same function, but FakeWorker gains subprocess-spawning behavior a phase early | |

**User's choice:** Generic builder + synthetic subprocess-echo test harness.
**Notes:** User picked the recommended option — keeps FakeWorker's documented "no external call" contract intact.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep it generic — caller supplies the credential explicitly | No new Settings fields; mirrors D-16's git-push pattern | ✓ |
| Add placeholder Settings fields for all three worker credentials now | anthropic_api_key, github_copilot_token, hermes_api_key added speculatively | |

**User's choice:** Keep it generic — caller supplies the credential explicitly.
**Notes:** User picked the recommended option — avoids guessing at field names Phase 7/8 might not actually match.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — shell.execute spawns real subprocesses through build_worker_env() | Genuine production call site proving SEC-03, not just the synthetic harness | ✓ |
| No — shell.execute stays a thin/stub registration this phase | build_worker_env() proven only via the standalone harness | |

**User's choice:** Yes — shell.execute spawns real subprocesses through build_worker_env().
**Notes:** User picked the recommended option.

---

## MCP transport scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal skeleton adapter, proven with a fake/test MCP client | Isolated mcp/ package exposing registered capabilities, no real Claude Code integration this phase | ✓ |
| Full MCP server matching every ToolRegistry capability, spec-complete | Complete standalone deliverable even for capabilities nothing will touch for phases | |

**User's choice:** Minimal skeleton adapter, proven with a fake/test MCP client.
**Notes:** User picked the recommended option.

| Option | Description | Selected |
|--------|-------------|----------|
| Optional extra (uv dependency group) | mcp SDK only pulled in when the extra is installed; matches CLAUDE.md guidance literally | ✓ |
| Regular (always-installed) dependency | Isolation enforced only by import-graph guard, not installability | |

**User's choice:** Optional extra (uv dependency group).
**Notes:** User picked the recommended option.

| Option | Description | Selected |
|--------|-------------|----------|
| One MCP server instance spun up per role invocation, role baked in at construction | Mirrors RoleContext's per-attempt fresh-construction discipline | ✓ |
| Single long-lived MCP server, role passed as a parameter on every tool call | More like a real multi-tenant deployment; introduces new per-call identity concerns | |

**User's choice:** "choose the best" (delegated) → recommended option locked in: one MCP server instance per role invocation.
**Notes:** User explicitly delegated this specific sub-question rather than picking a labeled option; the recommended option was taken as the answer per standard practice for a delegated choice.

---

## Claude's Discretion

- Exact `CapabilityDeniedError` message format and the fields carried on the `CAPABILITY_DENIED` event payload.
- Exact shape of the documented native-tool-restriction translation contract (docstring vs. typed mapping table).
- Exact synthetic test capability used to prove TOOL-02 extensibility.
- Exact revert/format details not otherwise specified — user consistently chose the recommended ("You decide leans here") option throughout this discussion.

## Deferred Ideas

None — discussion stayed entirely within phase scope. Native-CLI tool restriction wiring (Phase 7), `git.*`/`github.*` capability implementations (Phase 9/10), and full MCP server build-out (post-Phase-6) were identified as later-phase concerns during discussion, not raised as new capabilities.
