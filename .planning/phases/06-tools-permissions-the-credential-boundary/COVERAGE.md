# Phase 6 — External API Coverage Matrix

**External API integrated:** the official MCP Python SDK (`mcp`, PyPI, `>=2.2,<3`), consumed by
`src/dark_factory/tools/mcp_transport.py` (plan 06-03).

**Scope note.** The surface enumerated below is the **MCP SDK's own capability surface** — the
external API this phase integrates. It is *not* the seven `ToolRegistry` capabilities
(`repo.*` / `shell.execute` / `artifacts.*`), which are Dark Factory's own internal capability
layer and are scoped by `06-CONTEXT.md` D-04, not by this matrix.

Every capability starts at `INTEGRATE`; this table is the subtraction record. Every `OPT-OUT`
carries a reason.

| capability | decision | reason |
|---|---|---|
| `MCPServer(name=...)` construction | INTEGRATE | — |
| `MCPServer.add_tool(fn, name=, description=)` | INTEGRATE | — |
| `@MCPServer.tool()` decorator sugar | OPT-OUT | D-15 needs a runtime loop over a per-role `granted_tools` list; a decorator cannot express a dynamic set. `add_tool` is the same registration path without that constraint. |
| `ToolError` (`mcp.server.mcpserver.exceptions`) | INTEGRATE | — |
| `Client(server)` in-memory transport | INTEGRATE | — |
| `Client(..., raise_exceptions=True)` | INTEGRATE | — |
| `Client.list_tools()` | INTEGRATE | — |
| `Client.call_tool()` | INTEGRATE | — |
| stdio transport (`server.run()` / stdio server) | OPT-OUT | Explicitly out of scope per `06-CONTEXT.md` `<domain>`: real Claude Code / Copilot / Hermes MCP integration is Phase 7+. No external process connects this phase. |
| HTTP / SSE transport (`starlette`, `uvicorn`, `sse-starlette`) | OPT-OUT | Same boundary as stdio — no network transport is served this phase, so no port is bound and none of the transitive web stack is reachable (threat `T-06-18`). |
| Resources primitive (`add_resource`, resource templates) | OPT-OUT | All seven registered capabilities are verb-shaped actions, not addressable read-only documents; modelling them as resources would split one capability set across two MCP primitives with no caller asking for it. |
| Prompts primitive (`add_prompt`) | OPT-OUT | Dark Factory owns prompt assembly (`ContextBuilder`, Phase 4, CTX-01). Exposing prompts over MCP would hand a lifecycle responsibility to the worker, which the project's responsibility boundary forbids. |
| Sampling (`ctx.sample()`) | OPT-OUT | Would let a worker ask the orchestrator to call an LLM on its behalf. `.claude/CLAUDE.md`'s stated boundary is that Dark Factory does not implement another coding agent. |
| Elicitation (`ctx.elicit()`) | OPT-OUT | Human-in-the-loop is already Dark Factory's own durable `human_interactions` mechanism (Phase 2, HITL-01); a second, non-durable ask-a-human channel would be unresumable across a process restart. |
| Progress / logging notifications (`Context`) | OPT-OUT | `ToolRegistry.invoke()` is synchronous and returns a single value; there is no long-running MCP-side operation to report progress for. Dark Factory's structlog trail plus `run_events` is the audit surface (SEC-01, SEC-02). |
| Auth / OAuth token verification | OPT-OUT | D-15 explicitly scopes out session and auth negotiation this phase; the server is constructed in-process with the role baked in, so there is no peer to authenticate (threat `T-06-06`, disposition `accept`, reopened in Phase 7). |
| Server lifespan / lifecycle hooks | OPT-OUT | D-15 makes the server freshly constructed and stateless per role invocation; there is no lifespan state to manage. |
| Low-level `Server` (raw `on_list_tools` / `on_call_tool` handlers) | OPT-OUT | `06-RESEARCH.md` Alternatives Considered: the low-level API would require hand-writing dispatch-by-name and JSON Schema that `add_tool` derives for free. Reach for it only if a future phase needs schema control `add_tool` cannot express. |

**Re-decision note.** No prior MCP integration exists in this project, so no opt-out was carried
over from an earlier surface. When Phase 7 adds a real transport to a real worker runtime, it
re-decides every row above from the same full-coverage baseline rather than inheriting this
matrix — in particular the stdio, auth and lifespan rows, which are opted out here purely
because no external peer connects yet.
