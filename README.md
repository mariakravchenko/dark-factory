# Dark Factory

Durable software-delivery orchestration platform for AI engineering agents.

Dark Factory coordinates a single development task through specialized engineering
roles — Business Analyst → Architect → Developer → QA → Quality Gate → PR — where
each role is performed by an external AI agent runtime. The complete lifecycle
state of a run lives in PostgreSQL (Neon), so any process on any machine can
resume exactly where a previous one stopped.

> Phase 1 (walking skeleton) is under construction. A full local run guide lands
> with Plan 08.

## Development

```bash
uv sync --all-extras --dev
uv run pytest -m unit
```
