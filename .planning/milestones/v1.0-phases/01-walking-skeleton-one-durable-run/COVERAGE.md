# Phase 1 — API Coverage Declaration

**Phase:** 1 — Walking Skeleton: One Durable Run
**Generated:** 2026-09-07
**Contribution:** `api_coverage_gate` (plan:pre)

No external API integration: Phase 1 is local Postgres persistence + a Typer CLI driving FakeWorker; all AI/GitHub/network integration is explicitly out of scope.

---

## Why this phase self-skips the API Coverage checkpoint

| Candidate integration | Status in Phase 1 | Where it lands |
|---|---|---|
| Claude Code / Copilot / Hermes agent runtimes | Not integrated — `FakeWorker` returns a scripted `WorkerResult` in-process, zero subprocess, zero network | Phases 7-8 |
| GitHub REST/GraphQL/webhooks (`githubkit`) | Not a Phase 1 dependency; `github:` source classification exists but its loader raises `SourceNotSupportedError` | Phase 10 |
| MCP tool transport (`mcp` SDK) | Not a Phase 1 dependency | Phase 6 (optional) |
| Neon PostgreSQL | Consumed strictly as plain PostgreSQL over `DATABASE_URL` / `DATABASE_URL_DIRECT` through SQLAlchemy 2.0 + psycopg3. No `neon` SDK, no Neon control-plane API call, no provider-specific import (STATE-01) | n/a — it is a database, not an integrated API surface |

The only third-party surfaces Phase 1 touches are Python libraries resolved by `uv` from PyPI, which are covered by the Package Legitimacy Audit in `01-RESEARCH.md` and by threat `T-01-SC` plus the blocking-human legitimacy checkpoint in `01-01-PLAN.md`, not by the API Coverage gate.
