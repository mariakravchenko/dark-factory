# Phase 08 — API Coverage Declaration

**Phase:** 08 — Copilot & Hermes — Worker Independence Proven
**Decided:** 2026-09-21 (plan time)
**Outcome:** No coverage matrix — reasoned declaration instead.

## Declaration

No external API integration: this phase spawns `copilot`/`hermes` as non-interactive CLI
subprocesses and normalizes stdout to `WorkerResult` (mirroring `ClaudeCodeWorker`) — there
is no discrete verb/endpoint capability surface to enumerate the way a REST/SDK client
would have.

## Why this is the right call for this phase

The API Coverage checkpoint exists to stop "we integrated the API" from silently meaning
"we integrated whatever the first use case exercised", by enumerating a service's discrete
capability surface and forcing an explicit opt-out for each un-built one. That mechanism
needs a surface with enumerable members — endpoints, SDK verbs, resource types.

This phase's actual surface is two external binaries invoked as `argv` lists:

- `copilot -p <prompt> --no-ask-user -s [--allow-tool <name>]... [--model <pin>]`
- `hermes chat -q <prompt> --oneshot -Q --ignore-user-config`

There is exactly one operation per runtime — *run one role attempt to completion and give
back its output* — and the adapter performs it. There is no second verb that a later user
might reasonably expect to work and find missing. The axes along which these runtimes
genuinely differ are not capabilities but the four `WorkerCapabilities` fields
(`native_resume`, `session_id`, `non_interactive`, `structured_output`), and those are not
left to chance: ROADMAP SC4 requires each adapter's declaration to match its observed
behaviour, and plan 08-03 Task 3 (`tests/unit/test_worker_capabilities_match_behaviour.py`)
asserts each axis against observed argv and observed results rather than against a repeated
literal.

## The one enumerable surface that does exist, and where it is covered

Each CLI's own *tool* surface (what the spawned agent may do inside the worktree) is
enumerable, and it is not left implicit. It is enumerated in
`src/dark_factory/tools/native.py`'s `NATIVE_TOOL_CONTRACT` — one entry per Dark Factory
capability, each naming the `claude_code`, `copilot` and `hermes` translation plus the
`absent_behaviour` for a role that is denied it.

Coverage of that surface is enforced by tests rather than by this document:

| Surface member (capability) | Copilot | Hermes | Where enforced |
|---|---|---|---|
| `repo.read` | translated | no native mechanism → spawn-admission rule | 08-01 Task 1, 08-02 Task 1 |
| `repo.search` | translated | no native mechanism → spawn-admission rule | 08-01 Task 1, 08-02 Task 1 |
| `repo.write` | translated | no native mechanism → compensated by `enforce_write_scope` | 08-01 Task 1, 08-02 checkpoint + Task 1 |
| `repo.write_tests` | translated | no native mechanism → compensated by `enforce_write_scope` | 08-01 Task 1, 08-02 checkpoint + Task 1 |
| `shell.execute` | translated | no native mechanism → spawn-admission rule | 08-01 Task 1, 08-02 Task 1 |
| `artifacts.read` | translated | no native mechanism → spawn-admission rule | 08-01 Task 1, 08-02 Task 1 |
| `artifacts.write` | translated | no native mechanism → spawn-admission rule | 08-01 Task 1, 08-02 Task 1 |

Completeness is asserted, not declared: each adapter carries a plain function returning true
only when its translation table's key set equals `set(NATIVE_TOOL_CONTRACT)`, so a capability
added to the contract without a per-runtime translation fails a unit test instead of silently
granting nothing.

## Capabilities deliberately not adopted this phase

Two real, documented CLI features are opted out of, each with a one-line reason:

| Feature | Runtime | Disposition | Reason |
|---|---|---|---|
| `--output-format=json` structured output | copilot | opt out | Field schema undocumented in every source fetched during research; parsing an assumed shape against a CLI nobody has run is the rewrite-causing mistake this phase avoids. `structured_output=False` therefore describes what the adapter does, not what the CLI could do. |
| `--format stream-json` structured output | hermes | opt out | Same reason. |
| `--resume` session picker | copilot | opt out | Documented only as an interactive picker and absent from the CLI's own programmatic reference — `native_resume=False` is a documented fact, not a gap. |
| `--resume <session-id>` | hermes | opt out | The flag exists, but no fetched source confirms it completes headlessly combined with the one-shot and query flags; adopting it could hang an attempt until the worker timeout. Recorded as 08-RESEARCH.md Open Question 1 and as a flagged assumption in 08-02. |
| `--share` / `--share-gist` | copilot | forbidden | Exports the transcript outside Dark Factory's log tree, bypassing the redaction rewrite entirely (T-08-01). |
| `--allow-all-tools` / `--allow-all-paths` | copilot | forbidden | Bypasses the deny-by-omission translation and disables the CLI's own path confinement (T-08-04). |
| `--tui` | hermes | forbidden | Forces interactive mode against a closed stdin (T-08-15). |

Every opt-out above is revisitable by the deferred live spike (D-02) without an architectural
change — each would upgrade a `WorkerCapabilities` field and an argv branch inside the
existing adapter, nothing more.

## Verification

Checked at seal time via `check api-coverage.verify-pre .planning/phases/08-copilot-hermes-worker-independence-proven`.
