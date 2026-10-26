# Phase 07 — External Capability Coverage

**Decided:** 2026-09-20
**External surface:** the `claude` CLI's non-interactive (headless) invocation surface
(`@anthropic-ai/claude-code` 2.1.278, the version 07-RESEARCH.md validated against)

> The deterministic detector (`api-coverage.cjs`) returns `detected: false` for this phase's
> scope — Phase 7 integrates an external **CLI binary via `subprocess`**, not an HTTP API or
> an SDK, so the detector's verb/noun vocabulary does not fire. This file is authored anyway:
> the `claude` headless surface is genuinely a third-party capability surface with discrete
> flags, and an explicit INTEGRATE/OPT-OUT decision per flag is more useful than an implicit
> one. Every OPT-OUT carries a one-line reason.

Not an HTTP/SDK integration: no endpoint enumeration, no auth flow, no pagination, no
webhook surface. The whole contact surface is one argv and one JSON object on stdout.

## Capability Matrix

| Capability / flag | Decision | Reason | Where |
|-------------------|----------|--------|-------|
| `-p` / `--print` (non-interactive prompt) | INTEGRATE | The entire basis of `execute()`/`resume()`; a role attempt must run unattended. | 07-01 T1 |
| `--output-format json` | INTEGRATE | Gives `session_id`, `result`, `is_error`, `total_cost_usd`, `usage` — the fields `WorkerResult` normalizes from. | 07-01 T1 |
| `--output-format stream-json` | OPT-OUT | D-04 already delivers live durability by streaming raw stdout to `logs/<role>/`; incremental event parsing adds a second transcript format with no consumer this phase. |  |
| `--resume <session-id>` | INTEGRATE | The reason `WorkerCapabilities.native_resume=True` is honest; HITL-04's whole mechanism. | 07-03 T2 |
| `--continue` | OPT-OUT | Resumes "the most recent session" — implicit, process-local state, incompatible with a durable orchestrator that resumes a named attempt from a persisted id on a different machine. |  |
| `--session-id <uuid>` (caller-chosen id) | OPT-OUT | Would let Dark Factory mint the session id instead of storing the runtime's own. HITL-04 requires the id stay **opaque and runtime-owned**; minting it makes the orchestrator an interpreter of another system's handle. |  |
| `--allowedTools` | INTEGRATE | Translates the role's `tools:` grants into native tool restriction; the first runtime consumer of `NATIVE_TOOL_CONTRACT`. | 07-04 T1 |
| `--allowedTools` path-scoped specifier `Tool(<glob>/**)` | INTEGRATE | The only way to scope `artifacts.write` narrower than the whole worktree. | 07-04 T1 |
| `--disallowedTools` | OPT-OUT | Redundant and risky alongside an allow-list: deny-by-omission already refuses everything un-listed, and maintaining both invites a contradiction where the deny list silently wins. |  |
| `--permission-mode dontAsk` | INTEGRATE | A `-p` run has nobody to answer a permission prompt; without it an un-covered tool call hangs until the timeout, defeating the point of the timeout. | 07-01 T1 |
| `--permission-mode` as a path-scoping mechanism | OPT-OUT (does not exist) | 07-RESEARCH.md Summary finding 1: no `--permission-mode` value scopes file access to a directory. Worktree confinement comes from `cwd=work_dir`. 07-04 T2 corrects the contract table's prose accordingly. |  |
| `--dangerously-skip-permissions` / `bypassPermissions` | OPT-OUT | `--allowedTools` + `dontAsk` is sufficient for an unattended role, and `.claude/CLAUDE.md` scopes this flag to a sandboxed worktree only. Not needed; the blast radius is not worth the convenience. |  |
| `cwd=<worktree>` at spawn | INTEGRATE | The real worktree-confinement mechanism (un-prompted reads are limited to the working directory). | 07-01 T1 |
| `--add-dir` | OPT-OUT | Would widen the read surface beyond the run's worktree. Nothing this phase needs lives outside it. |  |
| `--json-schema` (enforced structured output) | OPT-OUT | D-01 is locked to a prose marker convention specifically to avoid a new CLI feature dependency. Recorded in 07-RESEARCH.md §"Alternatives Considered" as a future hardening pass for the `NEEDS_INPUT` parse. |  |
| `--bare` (skip host hooks / MCP / `CLAUDE.md` autoload) | OPT-OUT | 07-RESEARCH.md assumption A3: not adopted this phase. `RoleContext.baseline_docs` already carries the docs explicitly (CTX-01), so `--bare` is a reasonable later tightening, but switching now adds an untested behavioural delta to the tracer. |  |
| `--model <pin>` | OPT-OUT | No per-role model selection exists in `.dark-factory.yaml` or `RoleContext`; adding one is a config-surface decision, not an adapter decision. |  |
| `--max-turns` | OPT-OUT | `Settings.worker_timeout_seconds` (D-03) is the single agreed bound on an attempt. A second, differently-shaped limit would make "why did this attempt stop?" ambiguous. |  |
| MCP server wiring into the spawned CLI | OPT-OUT | Phase 6 D-02 states plainly that `ToolRegistry`/the MCP transport governs Dark-Factory-initiated calls only and cannot intercept a real CLI's own native tools. Native restriction comes from `--allowedTools`. |  |
| `ANTHROPIC_API_KEY` (credential) | INTEGRATE | D-02; reaches the subprocess solely through `build_worker_env(role, env_var_name=..., value=...)`. | 07-01 T1 |
| `total_cost_usd` / `usage` / `num_turns` / `duration_ms` | INTEGRATE (as `WorkerResult.metadata`) | Free observability per attempt at zero extra cost; the orchestrator never branches on them. | 07-01 T1 |
| `permission_denials` (JSON field) | INTEGRATE (as `WorkerResult.metadata`) | Records what the allow-list actually refused, which is the evidence that `--allowedTools` is doing anything. | 07-01 T1 |
| `structured_output` (JSON field) | OPT-OUT | Only populated when `--json-schema` is used, which is opted out above. |  |

## Summary

- INTEGRATE: 11
- OPT-OUT: 12 (each with a stated reason)
- Not applicable: HTTP endpoints, OAuth flows, pagination, webhooks, rate limits — this is a
  local subprocess surface, not a network API.
