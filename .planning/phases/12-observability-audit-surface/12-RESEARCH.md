# Phase 12: Observability & Audit Surface - Research

**Researched:** 2026-10-03
**Domain:** CLI observability surface (Typer + rich) over an existing durable-run read model; event-catalog completion; end-to-end secret-redaction proof
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Status view depth and rendering**
- **D-01:** The default text `status <run>` view carries the same full detail
  as `--json` — run header, per-role history (role, worker, attempt, status),
  artifacts, questions/answers, quality-gate results, errors, and PR info.
  There is no separate compact/verbose tier; `--json` differs only in
  serialization, not in content.
- **D-02:** The full status report is rendered with `rich` (tables for
  per-role history, panels/tree for the overall layout) rather than plain
  aligned text. `rich` already arrives transitively via Typer and the tech
  stack doc calls this out as the intended use.

**`runs` command**
- **D-03:** `dark-factory runs` is a `rich` table of id, status, source,
  created_at, updated_at, sorted by `created_at DESC` (most recent first).
  Supports `--status <STATUS>` to filter to one status (e.g. only
  `WAITING_HUMAN` or `FAILED` runs) — the common operator question is "what
  needs my attention."

**`artifacts` command**
- **D-04:** `dark-factory artifacts <run>` lists `ArtifactReference` metadata
  only (id, type, role, path, created_at) — consistent with "Neon is not a
  document store." A `--show <artifact-id>` flag reads the actual file from
  the filesystem artifact store and prints its content to stdout, passed
  through the same redaction path as `status`/`events` (never raw).

**`events` command**
- **D-05:** `dark-factory events <run>` defaults to a chronological
  human-readable list — one line per event in `seq` order (seq, timestamp,
  type, short payload summary) — including every `ROLE_BOUNCED` cycle in a
  feedback loop. `--json` emits the full array of event rows (shape mirrors
  the `run_events` columns). `--type <EventType>` filters to one or more
  event types for focused debugging. Both text and JSON paths run through the
  redaction processor.

**Missing event emission points**
- **D-06:** `ARTIFACT_CREATED` is emitted in the same transaction as every
  `ArtifactReference` insert (i.e. wherever `store_role_artifacts` or
  equivalent action writes a row) — one event per artifact row. This follows
  the existing pattern in `persistence/mutations.py` of pairing a state
  mutation with its event in the same transaction; it does not special-case
  "final" vs "intermediate" artifacts.
- **D-07:** `QA_FAILED` / `QA_PASSED` are emitted **alongside** (not instead
  of) `ROLE_COMPLETED` when the QA role's `verdict.json` is processed — the
  same precedent `QUALITY_GATE_PASSED/FAILED` and `ROLE_BOUNCED` already set
  in `events/catalog.py`: a purpose-built event in addition to the generic
  role event, so no existing consumer of `ROLE_COMPLETED` needs a new branch.
  `QA_FAILED`/`QA_PASSED` speak to the acceptance-criteria verdict;
  `QUALITY_GATE_*` stays about the independent command re-run — they are
  deliberately distinct signals in the same event stream.

**Secret-redaction end-to-end proof (SC4)**
- **D-08:** The SC4 proof is a full integration test, not a redaction-unit
  test. Settings are populated with realistically-shaped fake credentials
  (a fake `GITHUB_TOKEN`, a fake `DATABASE_URL`, a fake worker API key) via
  the existing `FakeWorker`/`fake_github.py` test doubles. Drive one run to
  completion (including a publish step), then assert none of the raw secret
  strings appear in: artifact files on disk, `run_events` payloads read back
  from Neon, captured log output, `fake_github`'s recorded comment bodies,
  and `test_report.json`. Reuses existing fixtures
  (`fake_claude_cli.py`, `fake_github.py`) rather than new test
  infrastructure — this is the only way to prove the whole pipeline (not
  just `redact()` in isolation) actually calls redaction everywhere it must.

### Claude's Discretion
- Exact column widths/box style for `rich` tables.
- Exact short-payload-summary format for the `events` text line (e.g. how a
  `ROLE_STARTED` line differs from a `QUALITY_GATE_FAILED` line).
- Whether `runs`/`artifacts` need `--limit`/pagination flags — not raised as
  a blocking gray area; left to the planner/researcher to size based on
  realistic run/artifact counts in this project's own test fixtures.

### Deferred Ideas (OUT OF SCOPE)
- **`--limit`/pagination for `runs`/`artifacts`** — not decided as in-scope
  or out-of-scope; left for the planner to size against realistic fixture
  counts rather than speculatively building it now.
- **`--role`/`--since`/`--until` filters on `events`** — only `--type` is
  locked in; additional filters were raised but not pursued as a blocking
  decision for this discussion.
- **Dedicated error/PR-info panel styling in `status`** — the content is
  locked (errors and PR info are part of the full report), but the specific
  presentation (dedicated panel vs inline field) was not drilled into
  further; left to the planner/executor.
</user_constraints>

## Summary

This phase is "wire up existing data into a new CLI surface," not new infrastructure. Every data source the expanded `status`, new `runs`, new `artifacts` and new `events` commands need already exists as a column, a table or an existing read function (`read_status`/`RunView`, `Run`, `RoleExecution`, `HumanInteraction`, `ArtifactReference`, `RunEvent`). The two genuinely new mechanics are (1) three new `EventType` members (`ARTIFACT_CREATED`, `QA_FAILED`, `QA_PASSED`) emitted from two already-identified call sites inside `orchestrator/runner.py`'s `_run_current_role`, following patterns the codebase already established for `QUALITY_GATE_*`/`ROLE_BOUNCED`; and (2) `rich`-rendered CLI output, which is genuinely new in this codebase (`rich` is present only transitively via Typer; nothing in `src/` imports it directly yet).

Two concrete, previously-undocumented gaps were found by reading the current source directly (not assumed) and must be addressed by this phase's plan, not treated as out of scope surprises discovered mid-execution:

1. **The GitHub clarification-comment body is posted unredacted.** `orchestrator/runner.py`'s `ROLE_NEEDS_INPUT` branch builds `comment_body = build_clarification_comment(result.questions)` and passes it straight to `client.create_comment(..., body=comment_body)` with no `redact()` call — unlike the sibling `HumanInteractionWrite(question=...)` write, which *is* redacted inside `apply_transition`. SC4's "fake_github's recorded comment bodies" assertion will fail against current code for a credential-shaped question unless this call site also redacts.
2. **A COMPLETED run's artifact content is not readable from the filesystem.** `_cleanup_run_worktree` removes the run's worktree once a run reaches `COMPLETED` (D-04, Phase 5). `artifacts <run> --show <id>` therefore cannot call `read_artifact_text(root, path)` against a live worktree for most runs — it must read through the run's persisted `working_branch` via `git show <branch>:.dark-factory/runs/<run_id>/<path>`, exactly the pattern `tests/support/git_repo.py`'s `read_committed`/`run_artifact_text` already prove at the test tier, but with **no production equivalent in `src/dark_factory/git/` yet**.

**Primary recommendation:** Extend the read-model layer with new, architecturally-separate sibling modules (not a rewrite of `observability/status.py`), add a production `read_committed`-equivalent to `src/dark_factory/git/`, wire the two new event-emission points at the exact call sites identified below, and build the SC4 proof as a `db`-tier test that composes the existing `test_publish_step.py` (real GitHub-sourced run + `FakeGitHubClient` + publish) and `test_secret_redaction_e2e.py` (seeded secrets + `real_log_sink` + whole-table sweep) patterns rather than inventing a new test shape.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `status`/`runs`/`artifacts`/`events` CLI commands | CLI (Typer) | — | Thin Typer commands, exactly like existing `run`/`resume`/`status`; no lifecycle logic (enforced by `test_status_command_body_carries_no_lifecycle_logic`-style AST guard) |
| Expanded `RunView` / per-role history / PR info | Read-model (`observability/`) | Persistence (ORM) | Pure reads composed from `runs`/`role_executions`/`human_interactions`/`artifacts` columns; must not import `dark_factory.events` (architectural guard on `observability.status`'s transitive closure) |
| State-transition history / `events` data | Read-model, new sibling module (NOT `observability/status.py`) | Persistence (`run_events`) | `run_events` is the one table that *must* be read to satisfy OBS-01's "state-transition history" and OBS-03 — but only from a module outside `observability.status`'s guarded closure |
| Artifact content on disk ("`artifacts --show`") | Git plumbing (`dark_factory.git`) | Filesystem (via git objects) | Worktree is removed on COMPLETED; content must be read via `git show <working_branch>:<path>`, never a live path |
| `ARTIFACT_CREATED` / `QA_FAILED` / `QA_PASSED` emission | Orchestrator (`orchestrator/runner.py`) | `persistence/mutations.py` (the one write path) | Events are domain facts about what the orchestrator just did; they ride the existing `EventWrite` list into the one `apply_transition` call, never a second write path |
| Redaction of comment bodies / artifact content | `dark_factory.events.redaction` | CLI composition point | `redact()` stays the one implementation; every new sink (comment body, `--show` output) must call it at its own call site, mirroring the `functools.partial(redact, known_secrets=...)` idiom `cli.py` already uses |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | Report state, active role, worker, worker session id, attempt, role history, artifacts, questions, answers, quality-gate results, errors, PR info, state-transition history | `RunState`/`RunView` already carry most scalar fields (`src/dark_factory/domain/views.py:44-63`, `src/dark_factory/persistence/repositories.py:84-136`); per-role history/artifacts/questions need new ORM queries over ALL rows (not just latest); quality-gate results need a `git show` read of `verification/quality_gate.json`; state-transition history needs a new sibling module reading `run_events` |
| OBS-02 | Emit `ARTIFACT_CREATED`, `QA_FAILED`/`QA_PASSED` (plus the already-shipped catalog) at the right moment | Exact call sites identified in `orchestrator/runner.py` (`artifact_writes` construction ~line 1178-1211; verdict-fail/pass branching ~line 1237-1412); `events/catalog.py:48-87`'s "not-yet-reachable types are deliberately not pre-declared" rule still applies — add exactly these three |
| OBS-03 | `dark-factory events <run>` and `dark-factory runs` expose the audit trail and run list | New `RunEvent`/`Run` queries following `test_publish_step.py`'s `_event_types` helper shape (`ORDER BY seq`) and `read_status`'s two-select discipline |
| TRIG-02 | CLI provides `run`, `resume`, `status`, `runs`, `artifacts`, `events` | `run`/`resume`/`status` already exist in `cli.py`; three new `@app.command()` functions follow the identical thin-wrapper shape |
| TRIG-03 | `status <run>` renders id, task, state, per-role pipeline w/ worker+attempts, artifacts, human interactions | D-01/D-02 (CONTEXT.md) lock this into one `rich`-rendered report, text and `--json` sharing content |

</phase_requirements>

## Standard Stack

No new external packages are required by this phase. `rich` is already present as a transitive dependency of `typer>=0.27,<1` (installed version confirmed via `pip show rich` this session: **13.7.1** `[VERIFIED: pip show rich, this environment]`) but is not yet imported anywhere under `src/` (`grep -rn "^import rich\|from rich" src/` returned no hits this session `[VERIFIED: grep, this session]`). The project's own tech-stack doc (CLAUDE.md) names a target of `rich 15.0.0`; the installed 13.7.1 is whatever Typer 0.27's own dependency resolution pulled. The `Table`/`Panel`/`Tree` APIs this phase needs (`rich.table.Table`, `rich.panel.Panel`, `rich.console.Console`) are stable across both major versions and have been since `rich` 10.x — this is `[ASSUMED]` (training knowledge of rich's API stability, not verified against the 13.7.1 changelog this session) but low-risk since the phase does not depend on any 14/15-only feature.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| rich | 13.7.1 (installed, transitive) | `Table`/`Panel`/`Console` rendering for `status`/`runs` | Already on disk via Typer; CLAUDE.md names this as the intended tool for this exact job |
| typer | >=0.27,<1 (pinned, `pyproject.toml`) | New `runs`/`artifacts`/`events` `@app.command()` definitions | Existing convention; vendors Click, no separate pin |

No **Supporting** or **Alternatives Considered** entries — this phase adds zero new third-party dependencies.

**Installation:** none required. `uv sync` already resolves the above.

## Package Legitimacy Audit

Not applicable — this phase installs no new external packages. `rich` is already resolved and locked via the existing `typer` dependency; no new `uv add` / `pip install` happens in this phase.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │                 cli.py (Typer)                │
                    │  run | resume | status | runs | artifacts |   │
                    │  events                                       │
                    └───────┬───────────────┬──────────────┬───────┘
                             │               │              │
             read_status()  │   NEW reads   │   NEW: git show <branch>:<path>
                             ▼               ▼              ▼
                ┌─────────────────┐ ┌──────────────────┐ ┌───────────────────┐
                │ observability/   │ │ NEW sibling        │ │ dark_factory.git/   │
                │ status.py        │ │ module(s):         │ │ NEW: read_committed │
                │ (unchanged guard:│ │ - per-role history │ │  (production)       │
                │  no events       │ │ - artifacts list    │ │  used by            │
                │  import)         │ │ - questions/answers │ │  `artifacts --show` │
                └─────────┬────────┘ │ - PR info (Run cols)│ │  and the quality-   │
                          │          │ - events/seq list   │ │  gate-results read  │
                          │          │   (DOES import      │ └───────────────────┘
                          │          │   dark_factory.events)│
                          │          └──────────┬──────────┘
                          │                     │
                          ▼                     ▼
                 ┌──────────────┐      ┌──────────────────┐
                 │ Run, Role     │      │ RunEvent          │
                 │ Execution,     │      │ (run_events,      │
                 │ HumanInter-   │      │  ORDER BY seq)     │
                 │ action,        │      └──────────────────┘
                 │ ArtifactRef    │
                 └──────────────┘


   Orchestrator side (event emission, OBS-02):

   orchestrator/runner.py :: _run_current_role
   ┌────────────────────────────────────────────────────────────┐
   │ collect_role_artifacts() -> artifact_writes (per file)       │
   │        │                                                     │
   │        ▼  ONE new ARTIFACT_CREATED EventWrite per write,     │
   │           spliced into `events` in the ROLE_COMPLETED and    │
   │           ROLE_BOUNCED branches only (never ROLE_FAILED --   │
   │           artifact_writes is cleared to [] on failure)       │
   │                                                               │
   │ verdict_write found (terminal role only, by artifact TYPE,    │
   │ never by role-name literal)                                  │
   │        │                                                     │
   │        ├─ FAIL  -> NEW QA_FAILED EventWrite, alongside        │
   │        │          whatever ROLE_BOUNCED/ROLE_FAILED the       │
   │        │          existing _bounce_or_fail() decision adds    │
   │        └─ PASS  -> NEW QA_PASSED EventWrite, alongside the    │
   │                   existing QUALITY_GATE_STARTED emission      │
   └────────────────────────────────────────────────────────────┘
                          │
                          ▼
            persistence/mutations.py :: apply_transition
            (the ONE place events/role_executions/artifacts commit,
             unchanged by this phase)
```

### Recommended Project Structure

```
src/dark_factory/
├── cli.py                       # + runs, artifacts, events @app.command()
├── observability/
│   ├── status.py                # UNCHANGED guard (no events import)
│   └── run_detail.py            # NEW: per-role history, artifacts list,
│                                 #      questions/answers, PR info -- all
│                                 #      from runs/role_executions/
│                                 #      human_interactions/artifacts; still
│                                 #      imports nothing from dark_factory.events
├── events/
│   ├── catalog.py                # + ARTIFACT_CREATED, QA_FAILED, QA_PASSED
│   ├── redaction.py               # unchanged
│   └── reader.py                  # NEW: run_events query (ORDER BY seq),
│                                   #      state-transition history -- the
│                                   #      ONLY new module allowed to import
│                                   #      dark_factory.events for a read path
└── git/
    └── committed.py (or added to diff.py)  # NEW: production read_committed()
                                             #      (git show <branch>:<path>),
                                             #      promoted from
                                             #      tests/support/git_repo.py
```

### Pattern 1: Thin Typer command, rendering delegated to a DTO

**What:** Every new command (`runs`, `artifacts`, `events`) follows `status`'s exact shape: parse args, call one or two read functions, pass the result through `functools.partial(redact, known_secrets=get_settings().known_secret_values())`, render with `rich`, exit. No lifecycle branch, no `RunStatus` comparison in the command body — `tests/integration/test_status_cli.py::test_status_command_body_carries_no_lifecycle_logic` is the exact AST-based guard shape to replicate for the new commands.

**When to use:** Every new read-only CLI command in this phase.

**Example (the exact existing pattern to replicate):**
```python
# Source: src/dark_factory/cli.py:224-257 [VERIFIED: read this session]
@app.command()
def status(
    run_id: str,
    output_json: bool = typer.Option(
        False, "--json", help="Emit one JSON object instead of the text field list."
    ),
) -> None:
    try:
        parsed = UUID(run_id)
    except ValueError as exc:
        typer.echo(f"not a run id: {run_id}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        view = read_status(parsed)
    except UnknownRunError as exc:
        typer.echo(f"unknown run: {run_id}", err=True)
        raise typer.Exit(code=2) from exc

    redactor = functools.partial(
        redact, known_secrets=get_settings().known_secret_values()
    )
    if output_json:
        _route_logs_to_stderr()
        typer.echo(view.as_json(redactor=redactor))
    else:
        typer.echo(view.as_text(redactor=redactor))
```

### Pattern 2: `rich.table.Table` printed through a `Console`, captured in tests via `Console(file=...)`

**What:** `rich.console.Console` accepts a `file=` keyword (an `io.StringIO`) so a test can capture rendered table output deterministically without a real terminal — `rich` auto-detects non-tty output and disables color/width-guessing when given an explicit `file`, but tests should also pass `width=` explicitly to make column wrapping deterministic across CI runners. `[ASSUMED: rich API, training knowledge, not verified against the installed 13.7.1 docs this session]` — the planner should have the executor confirm `Console(file=buf, width=120, no_color=True)` renders deterministically before relying on substring assertions in CLI tests.

**When to use:** `runs` table, any `status` panel/table rendering.

**Example:**
```python
# Illustrative -- not sourced from this codebase; verify against the
# installed rich 13.7.1 before the executor relies on exact output shape.
import io
from rich.console import Console
from rich.table import Table

def render_runs_table(rows: list[RunListRow]) -> str:
    table = Table()
    for col in ("id", "status", "source", "created_at", "updated_at"):
        table.add_column(col)
    for row in rows:
        table.add_row(str(row.run_id), row.status.value, row.source_kind,
                       row.created_at.isoformat(), row.updated_at.isoformat())
    buf = io.StringIO()
    Console(file=buf, width=120, no_color=True).print(table)
    return buf.getvalue()
```

### Pattern 3: CLI-tier test asserting on rendered text and `--json`, following `test_status_cli.py` exactly

**What:** Every existing `status` CLI test spawns `python -m dark_factory <args>` as a real subprocess against a provisioned PostgreSQL, asserts on stdout substrings in text mode and on `json.loads(stdout)` keys in `--json` mode, and asserts `proc.returncode`. New `runs`/`artifacts`/`events` tests should sit in the same file or a sibling file under `tests/integration/`, reusing the exact `_cli()` helper shape (env built from `pg_url`, `DARK_FACTORY_FAKE_SCRIPT`/`DARK_FACTORY_CRASH_AFTER` stripped).

**Source:** `tests/integration/test_status_cli.py:33-57` (the `_cli()` helper) `[VERIFIED: read this session]`.

### Pattern 4: Reading artifact content that may no longer exist on disk — via git, not the filesystem

**What:** A `COMPLETED` run has its worktree removed by `_cleanup_run_worktree` (`orchestrator/runner.py:764-814`, calling `remove_worktree` `[VERIFIED: read this session]`). Any code path that reads artifact *content* after a run has reached `COMPLETED` must read it from the run's persisted `working_branch` (a `Run` column, already present) via `git show <branch>:<run-root-relative-path>`, never via `Path.read_text()` against a worktree path. The test tier already has exactly this helper; this phase's production code does not yet.

**Example — the test-tier precedent to promote into `src/`:**
```python
# Source: tests/support/git_repo.py:58-91 [VERIFIED: read this session]
def read_committed(repo_root: Path, branch: str, relative_path: str) -> str:
    """``git show <branch>:<relative_path>``."""
    return run_git(["show", f"{branch}:{relative_path}"], cwd=repo_root).stdout

def run_artifact_text(
    repo_root: Path, run_id: UUID, working_branch: str, relative_path: str
) -> str:
    return read_committed(
        repo_root, working_branch, f".dark-factory/runs/{run_id}/{relative_path}"
    )
```
`run_git` is already a production function (`src/dark_factory/git/client.py`, imported by the test helper above) — the planner's task is to add a production `read_committed`/equivalent next to it (or in `git/diff.py`), not to invent new git plumbing. This same function is also the only way to honestly satisfy OBS-01's "quality-gate results" field (`verification/quality_gate.json` is written to the run tree and committed — GATE-04 — but has no DB row of its own, D-01 in `orchestrator/quality_gate.py`).

**A repo-root parameter is needed for `artifacts --show`.** `read_committed`/`run_artifact_text` both take `repo_root` explicitly — the CLI does not currently have an obvious single source for "the repository root a given run's artifacts live in" outside of `Path.cwd()` (the same resolution `run`/`resume` already use, per `cli.py:174` `load_effective_config(Path.cwd())`). The planner should confirm `artifacts`/`events`/`status --json` commands resolve `repo_root` the same way `run` does (current working directory), since there is no `repository` column on `runs` holding an absolute filesystem path — only `base_branch`/`working_branch` (branch names) are persisted.

### Pattern 5: Splicing a new per-artifact event into the existing branch-shaped event list (OBS-02, D-06)

**What:** `_run_current_role` already builds `artifact_writes: list[ArtifactReferenceWrite]` (one entry per declared output file, via `collect_role_artifacts` — `src/dark_factory/artifacts/validation.py:58-128` `[VERIFIED: read this session]`) and clears it to `[]` on every failure path (`ArtifactError`/`CapabilityDeniedError`/`GitError`/`WriteScopeViolation`, four separate `except`/`if` arms in `orchestrator/runner.py`). The three signal-outcome branches (`ROLE_COMPLETED`, `ROLE_FAILED`, `ROLE_BOUNCED`) each independently build their own `events` list before the single `apply_transition` call at the bottom of the function (`runner.py:1511-1750`). D-06 says one `ARTIFACT_CREATED` event per artifact row, with no final-vs-intermediate special case — the natural, minimal-diff way to satisfy this without touching the failure branch at all is to build `artifact_events = [EventWrite(type=EventType.ARTIFACT_CREATED, role_execution_id=latest.id, payload={"role": node.name, "type": w.type, "path": w.path}) for w in artifact_writes]` once, right after `artifact_writes` is finalized (i.e., after the commit/push `GitError` catch, since that catch clears `artifact_writes` back to `[]`), then `events.extend(artifact_events)` in both the `ROLE_COMPLETED` and `ROLE_BOUNCED` branches — mirroring exactly how `gate_events` is already built once and `.extend()`-ed into all three branches (`runner.py:1529`, `1577`, `1610` `[VERIFIED: read this session, exact line content quoted below]`).

**Verbatim confirmation of the existing `gate_events` splice pattern this should mirror (quoted, not paraphrased):**
```
# ROLE_COMPLETED arm (runner.py:1518-1529):
        events = [
            EventWrite(
                type=EventType.ROLE_COMPLETED,
                payload={"role": node.name, "summary": result.summary},
            ),
        ]
        ...
        events.extend(gate_events)
# ROLE_FAILED arm (runner.py:1561-1577):
        events = [
            EventWrite(type=EventType.ROLE_FAILED, payload={...}),
            EventWrite(type=EventType.RUN_FAILED, payload=run_failed_payload),
        ]
        ...
        events.extend(gate_events)
# ROLE_BOUNCED arm (runner.py:1602-1610):
        events = [
            EventWrite(
                type=EventType.ROLE_COMPLETED,
                payload={"role": node.name, "summary": result.summary},
            ),
        ]
        events.extend(gate_events)
```
`ARTIFACT_CREATED` should extend `events` in the `ROLE_COMPLETED` and `ROLE_BOUNCED` arms only (both leave `artifact_writes` non-empty on the success path); the `ROLE_FAILED` arm needs no change since `artifact_writes` is always `[]` by the time that arm runs.

### Pattern 6: QA_FAILED / QA_PASSED alongside ROLE_COMPLETED — reuse the `gate_events`-style accumulator, keyed on structural detection

**What:** The terminal-role verdict block (`runner.py:1233-1412` `[VERIFIED: read this session]`) already detects "this is the role whose `verdict.json` output decides PASS/FAIL" **structurally**, by artifact *type* (`w.type == "verdict.json"`), never by a role-name literal — required, because `tests/unit/test_no_role_name_literal.py` forbids any `"QA"`/`"BA"`/etc. string literal anywhere under `src/dark_factory/orchestrator/` (`[VERIFIED: read this session, tests/unit/test_no_role_name_literal.py:1-24]`). Add a `qa_verdict_events: list[EventWrite] = []` accumulator, append `EventType.QA_FAILED` inside the existing `if verdict.computed_status is VerdictStatus.FAIL:` branch (`runner.py:1248`) and `EventType.QA_PASSED` inside the existing `else:` (PASS) branch (`runner.py:1267`, right where `QUALITY_GATE_STARTED` is already appended to `gate_events`), then `events.extend(qa_verdict_events)` in the same three places `gate_events` is already extended — this is the literal meaning of D-07's "alongside (not instead of) `ROLE_COMPLETED`": the worker's own completion is unaffected; the QA-outcome signal rides as an addition in whichever branch the final `signal` lands in (`ROLE_COMPLETED` for a PASS that also passes the gate, `ROLE_BOUNCED`/`ROLE_FAILED` for a FAIL verdict, mirroring exactly how a FAILED quality-gate result's `QUALITY_GATE_FAILED` event already survives into all three arms via `gate_events`).

**Payload shape**, mirroring the existing `QUALITY_GATE_PASSED`/`FAILED` payloads (`role`, and whatever is cheaply available): `{"role": node.name, "criteria_failed": [c.criterion_id for c in verdict.criteria if c.result is VerdictStatus.FAIL]}` for `QA_FAILED`, `{"role": node.name}` for `QA_PASSED` — exact field set is Claude's Discretion per CONTEXT.md (not drilled into in the discussion); keep it minimal and consistent with the existing gate-event payload style rather than inventing a new convention.

### Anti-Patterns to Avoid

- **Importing `dark_factory.events` from `observability/status.py` or from `RunView`.** `tests/unit/test_status_import_graph.py` walks the *transitive* closure from `dark_factory.observability.status`, not just its direct imports — a helper two hops away that reaches `dark_factory.events` still trips the guard (`[VERIFIED: read this session]`). Put the `run_events` read in a genuinely separate module and compose at the CLI layer.
- **Branching the new `QA_FAILED`/`QA_PASSED` logic on a role-name literal.** The existing verdict-detection code is already structural (by artifact type); do not regress it to `if node.name == "QA":` to make the new events "simpler" — this trips `test_no_role_name_literal.py`.
- **Reading artifact content from a live worktree path for `artifacts --show`.** Works for a still-running run, silently breaks (file not found) for any `COMPLETED` run — exactly the class of bug that is easy to miss in a plan that only tests against an in-flight run.
- **Posting the clarification-comment body to GitHub before redacting it.** This is the live bug identified above; do not let a new `events`/`status` display path reuse `build_clarification_comment`'s raw string for anything shown to an operator either — redact at the display call site even while the underlying production bug (unredacted post to GitHub) gets its own fix.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reading a specific git-committed file's content | A custom `subprocess.run(["git", "show", ...])` call site duplicated per new command | A single production `read_committed`/equivalent in `dark_factory.git`, reusing `run_git` (`src/dark_factory/git/client.py`) | One call site for the same T-05-01/T-05-04 env-allowlist discipline every other git call already follows; promoting the existing test-tier `read_committed` is strictly less risk than writing a second git-invocation helper |
| Secret scrubbing for a new sink (`--show` output, comment body) | A second regex/substitution helper "just for this one field" | `dark_factory.events.redaction.redact()` via the existing `functools.partial(redact, known_secrets=...)` idiom | `redact()` is documented as the *only* redaction implementation in the codebase (`events/redaction.py:1-20`); a second implementation is exactly the kind of drift SEC-02 exists to prevent |
| Rendering tabular CLI output | Hand-aligned `f"{a:<10}{b:<10}"` string formatting | `rich.table.Table` | CLAUDE.md names `rich` as the intended tool and it is already resolved; hand-rolled alignment breaks on variable-width UUIDs/timestamps |

**Key insight:** every "don't hand-roll" item above already has a shipped, working implementation somewhere in this codebase (test tier or production) — the work is promotion and composition, not invention.

## Common Pitfalls

### Pitfall 1: The clarification-comment body bypasses redaction entirely
**What goes wrong:** A GitHub-sourced run that asks a human a question containing a credential-shaped string (echoed from task text, a repo file, or a tool output) will post that string, unredacted, to a real GitHub issue comment — a permanent, externally-visible leak — even though the *persisted* `human_interactions.question` column is correctly redacted.
**Why it happens:** `orchestrator/runner.py`'s `ROLE_NEEDS_INPUT` branch calls `client.create_comment(..., body=comment_body)` with `comment_body = build_clarification_comment(result.questions)` built directly from the raw `WorkerResult.questions`, with no `redact()` call anywhere on that value before the GitHub API call (`[VERIFIED: read this session, runner.py:1662-1676]`). The only `redact()` call nearby scrubs a *different* string — the `clarification_comment_error` text in the `except GitHubError` arm (`runner.py:1685-1692`).
**How to avoid:** Add `comment_body = build_clarification_comment([redact(q, known_secrets=known) for q in result.questions])`, or redact the joined `comment_body` once, immediately before the `create_comment` call — matching the precedent 09-05 already set for `GateCommandResult.command` in `orchestrator/quality_gate.py:172-177` (redact before an external/durable sink, not only before the DB write).
**Warning signs:** SC4's "GitHub comment bodies" assertion failing with a literal secret string present in `fake_client.calls` entries for `create_comment`.

### Pitfall 2: `artifacts <run> --show <id>` works in dev testing, breaks for any real COMPLETED run
**What goes wrong:** A naive implementation resolves the artifact's `path` column against a live worktree (`ensure_worktree(...)` + `Path.read_text()`), which works perfectly in a quick manual test against a run still mid-pipeline, then raises `FileNotFoundError`/`MissingArtifactContentError` the first time it's tried against a run that actually finished — i.e., the common case an operator would reach for this command on.
**Why it happens:** `_cleanup_run_worktree` (`runner.py:764-814`) removes the worktree on every `COMPLETED` transition (D-04). The content survives only on the run's `working_branch` (a persisted `Run` column).
**How to avoid:** Always read artifact content via `git show <working_branch>:.dark-factory/runs/<run_id>/<path>` (Pattern 4 above), never a live filesystem path, regardless of run status — this also makes the code path uniform (same for a running or finished run) rather than branching on `run.status`.
**Warning signs:** A plan or test that only ever drives `artifacts --show` against a run still at an intermediate status, never against one that reached COMPLETED.

### Pitfall 3: `enforce_write_scope`-style zero-events or `collect_role_artifacts` ordering interactions with the new `ARTIFACT_CREATED` event
**What goes wrong:** If `ARTIFACT_CREATED` events are built from `artifact_writes` *before* the later `GitError`/`WriteScopeViolation` catches that clear `artifact_writes` back to `[]` on a late failure, the event list could claim artifacts were created when the commit that would have made them durable never happened.
**Why it happens:** `artifact_writes` is populated early (right after `collect_role_artifacts` succeeds, `runner.py:1178-1211`) but can still be cleared later by the commit/push `GitError` catch (`runner.py:1431-1451`) or the `enforce_write_scope` `WriteScopeViolation` catch (`runner.py:1491-1509`) — both already clear `artifact_writes = []` specifically so no `artifacts` DB row survives a late failure (ART-04's "never report artifacts as durable when they aren't" rule, stated explicitly in the existing `GitError` comment).
**How to avoid:** Build the `ARTIFACT_CREATED` event list from `artifact_writes` only after all of those later clearing points have already run — i.e., at the same point the final `apply_transition` call reads `artifact_writes` (bottom of the function), not immediately after `collect_role_artifacts`.
**Warning signs:** A test asserting `ARTIFACT_CREATED` events exist for a role whose commit/push subsequently failed.

## Code Examples

### Adding the three new catalog members (OBS-02)

```python
# Source: src/dark_factory/events/catalog.py:48-87, extended per this phase's
# own docstring convention of naming which phase/plan adds which member and why.
class EventType(StrEnum):
    ...
    PUBLISH_STARTED = "PUBLISH_STARTED"
    PR_CREATED = "PR_CREATED"
    PUBLISH_FAILED = "PUBLISH_FAILED"

    # Phase 12 -- the artifact-write and QA-verdict audit ties.
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    QA_FAILED = "QA_FAILED"
    QA_PASSED = "QA_PASSED"
```
There is almost certainly an existing unit test pinning the catalog's exact member count (the Phase 2 docstring at `events/catalog.py` describes earlier phases' additions being "pinned at ten members by a unit test" for an analogous enum) — the planner should grep for a catalog-cardinality test and update it in the same commit, not leave it to fail the suite.

### The exact `_event_types` query shape to reuse for the new `events` command

```python
# Source: tests/db/test_publish_step.py:224-232 [VERIFIED: read this session]
def _event_types(engine: Engine, run_id: Any) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                sa.select(RunEvent.type)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.seq)
            ).all()
        )
```
The production `events` command needs the full row (`seq`, `created_at`, `type`, `payload`, `role_execution_id`), not just `type`, but the `.where(RunEvent.run_id == run_id).order_by(RunEvent.seq)` shape is exactly right and already proven against real PostgreSQL.

### The `--status` filter for `runs` (D-03)

A `Run.status == <value>` filter composes trivially onto a `select(Run).order_by(Run.created_at.desc())` query — `Run.status` is typed as `Mapped[RunStatus]` via the `sa.Enum(RunStatus, native_enum=False, ...)` column (`persistence/models.py:71-78, 113` `[VERIFIED: read this session]`), so the CLI option should parse the `--status` string argument through `RunStatus(value)` (raising on an invalid value, mapped to exit 2) rather than comparing raw strings.

## State of the Art

No external framework/library "state of the art" shift applies here — this phase is entirely internal composition over an already-chosen stack (Typer, rich, SQLAlchemy 2.0, pydantic v2). No deprecated/outdated approach to flag.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `rich` 13.7.1's `Table`/`Panel`/`Console(file=...)` API is stable and sufficient for this phase's needs (no 14/15-only feature required) | Standard Stack, Pattern 2 | Low — if a specific `rich` call used in the plan doesn't exist in 13.7.1, it is a quick API-compat fix, not a redesign; the executor should run a quick `python -c "from rich.table import Table"`-style smoke check before relying on any newer API |
| A2 | The CLI resolves `repo_root` for `artifacts`/`events`/expanded `status` the same way `run` does today (`Path.cwd()`), since no absolute filesystem path is persisted on `runs` | Pattern 4 | Medium — if the planner instead expects a persisted repo path, that column does not exist and would need its own migration, which is out of this phase's locked scope |
| A3 | A catalog-cardinality unit test exists (analogous to the one the Phase 2 docstring references) and needs updating alongside the three new `EventType` members | Code Examples | Low — if no such test exists, the three new members simply need no test update; if it does exist and is missed, CI fails loudly and cheaply, not silently |

**If this table is empty:** N/A — three assumptions logged above, all low-to-medium risk and independently verifiable by the executor in minutes.

## Open Questions

1. **Exact module name/location for the new per-role-history/events-reader read functions.**
   - What we know: they must NOT live inside (or be transitively imported by) `observability/status.py`; a new sibling module (e.g. `observability/run_detail.py` for the non-events reads, `events/reader.py` for the `run_events` read) satisfies both the architectural guard and OBS-01/OBS-03.
   - What's unclear: whether the planner prefers one combined new module or two, and whether the CLI composes them inline in `cli.py` or through one new "expanded report" DTO.
   - Recommendation: two modules (mirrors the existing clean split between `observability/status.py` which never touches events, and a new reader that only ever touches events) — simpler to keep the import-graph guard trivially correct, and keeps `events` command's own data source identical to the one `status`'s "state-transition history" field composes.

2. **Where exactly the production `read_committed`-equivalent should live.**
   - What we know: `run_git` (the one subprocess wrapper) lives in `src/dark_factory/git/client.py`; `commit_run_artifacts`/`push_working_branch` (the nearest existing "high-level git operation" functions) live in `src/dark_factory/git/diff.py`.
   - What's unclear: whether to add a new `git/committed.py` module or add one function to the existing `diff.py`.
   - Recommendation: a new small module (`git/committed.py`) — `diff.py`'s existing docstring and `__all__` are scoped to "collect/commit/push" write-adjacent operations; a pure read function reads more honestly as its own module, and keeps `diff.py`'s existing guard/test surface untouched.

3. **Exact SC4 test construction — subprocess CLI vs. in-process `drive()`.**
   - What we know: `fake_claude_cli.py` + `fake_claude_env` exist for a real subprocess-spawned `ClaudeCodeWorker`; `FakeGitHubClient` injection via `github_client_factory` only works through the in-process `drive()`/`start_run()` call shape (`tests/db/test_publish_step.py`'s pattern), not through the CLI subprocess (which always binds `default_github_client_factory`).
   - What's unclear: CONTEXT.md's canonical_refs names both `fake_claude_cli.py` and `fake_github.py` as fixtures to reuse, but combining a real subprocess-spawned worker with an injected `FakeGitHubClient` requires driving through `drive()` directly (constructing a `WorkerRegistry` that wraps a real `ClaudeCodeWorker` instance pointed at the fake `claude` binary on `PATH`), not through `python -m dark_factory run ...`.
   - Recommendation: build the SC4 test as a `db`-tier test (`tests/db/test_secret_redaction_e2e_full_pipeline.py` or similar), combining `test_publish_step.py`'s `_write_github_four_role_tree` + `FakeGitHubClient` + `drive(..., github_client_factory=...)` shape with `test_secret_redaction_e2e.py`'s seeded-secrets + `real_log_sink` + whole-table-sweep shape, and wrap at least one role (e.g. DEVELOPMENT) with a real `ClaudeCodeWorker` via `write_fake_claude`/`fake_claude_env` to prove the subprocess/env boundary too — reusing `WorkerRegistry.register("claude-code", lambda: ClaudeCodeWorker(...))` the same way `test_claude_code_worker.py` already constructs one.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| rich | `runs`/`status` rendering | ✓ | 13.7.1 (transitive via typer) | — |
| git CLI | `artifacts --show`, quality-gate-results read | ✓ | system git (already required by every earlier phase) | — |
| PostgreSQL (db-tier tests) | `db`-marked tests for new CLI commands + SC4 proof | per-session, external (not probed this session — matches every earlier phase's db-tier dependency posture) | — | tests marked `@pytest.mark.db`, already skipped when unreachable per project convention |

No missing dependency blocks this phase; no new external dependency is introduced.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.x (per CLAUDE.md tech stack; `pyproject.toml` `[tool.pytest.ini_options]`) |
| Config file | `pyproject.toml` (`testpaths = ["tests"]`, four markers: `unit`, `db`, `integration`, `contract` `[VERIFIED: read this session, pyproject.toml:69-75]`) |
| Quick run command | `uv run pytest -q -m "unit or contract"` |
| Full suite command | `uv run pytest -q` (unit + contract + db + integration, per `.github/workflows/ci.yml`'s three separate steps: `pytest -q -m "unit or contract"` then `pytest -q -m db`, plus the dedicated `integration` CLI-subprocess tier) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRIG-02 | `runs`/`artifacts`/`events` commands exist and parse args correctly | integration (CLI subprocess) | `pytest -q tests/integration/test_runs_cli.py` (or added to `test_status_cli.py`) | ❌ Wave 0 |
| TRIG-03 | expanded `status` renders all D-01 fields, text and `--json` share content | integration | `pytest -q tests/integration/test_status_cli.py` | ✅ exists, extend |
| OBS-02 | `ARTIFACT_CREATED`/`QA_FAILED`/`QA_PASSED` emitted at the right moment | db | `pytest -q -m db tests/db/test_artifact_created_event.py tests/db/test_qa_verdict_events.py` | ❌ Wave 0 |
| OBS-03 | `events`/`runs` expose the full typed audit trail / run list | integration | `pytest -q tests/integration/test_events_cli.py tests/integration/test_runs_cli.py` | ❌ Wave 0 |
| SC4 (secret proof) | zero secret leakage across artifacts/events/logs/comments/reports for a full run | db (one comprehensive test) | `pytest -q -m db tests/db/test_secret_redaction_e2e_full_pipeline.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q -m "unit or contract"`
- **Per wave merge:** `uv run pytest -q -m db` (new db-tier tests require a reachable PostgreSQL, per every earlier phase's established posture)
- **Phase gate:** Full suite green (`unit`, `contract`, `db`, `integration`) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/integration/test_runs_cli.py` — covers TRIG-02 (`runs` command), OBS-03
- [ ] `tests/integration/test_events_cli.py` — covers TRIG-02 (`events` command), OBS-03
- [ ] `tests/db/test_artifact_created_event.py` — covers OBS-02 (`ARTIFACT_CREATED`)
- [ ] `tests/db/test_qa_verdict_events.py` — covers OBS-02 (`QA_FAILED`/`QA_PASSED`)
- [ ] `tests/db/test_secret_redaction_e2e_full_pipeline.py` — covers SC4
- [ ] A new `src/dark_factory/git/committed.py`-style production module — no test gap by itself, but every test above that exercises `artifacts --show` against a COMPLETED run depends on it existing

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | This phase adds no new authentication surface |
| V3 Session Management | no | N/A |
| V4 Access Control | no | CLI commands are local-operator tools, same trust boundary as existing `run`/`resume`/`status` |
| V5 Input Validation | yes | `--status`/`--type` CLI filter values must be validated against `RunStatus`/`EventType` enums (raise -> exit 2), never passed as raw strings into a SQL `WHERE` (SQLAlchemy's typed `Enum` column already parameterizes this safely) |
| V6 Cryptography | no | N/A |
| V9 (Data Protection, ASVS 4.x numbering) / this project's own SEC-01/SEC-02 | yes | `dark_factory.events.redaction.redact()` is the one implementation; every new sink (CLI `--show` output, the clarification-comment body) must call it at its own call site |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential leaked via an external, non-revocable sink (GitHub comment) | Information Disclosure | Redact *before* the external API call, not only before the DB write — the exact Pitfall 1 gap this research identified |
| Artifact-path traversal via a crafted `--show <artifact-id>` or a crafted `relative_path` reaching `git show` | Information Disclosure / Tampering | Reuse `resolve_under_run_root`'s existing path-escape rejection (`artifacts/paths.py:48-66`) for any filesystem-adjacent resolution; for the `git show` path specifically, the artifact's `path` column is already validated at write time (via `resolve_under_run_root` inside `collect_role_artifacts`'s own write path), so a `--show` lookup keyed by the `ArtifactReference.id` primary key (never a free-text path argument) cannot be used to request an arbitrary path |
| CLI `--status`/`--type` filter used as an injection vector | Tampering | Validate against the enum before querying; SQLAlchemy's typed column makes a raw-string injection structurally unreachable regardless, but validating early also gives a clean exit-2 error message instead of an empty result set |

## Sources

### Primary (HIGH confidence)
- `src/dark_factory/cli.py`, `observability/status.py`, `events/catalog.py`, `events/redaction.py`, `persistence/mutations.py`, `persistence/models.py`, `persistence/repositories.py`, `domain/views.py`, `domain/artifacts.py`, `domain/status.py`, `domain/signal.py`, `orchestrator/runner.py` (full read), `orchestrator/quality_gate.py`, `orchestrator/publish.py`, `artifacts/validation.py`, `artifacts/store.py`, `artifacts/paths.py`, `git/client.py` — all read directly this session.
- `tests/integration/test_status_cli.py`, `tests/unit/test_status_import_graph.py`, `tests/unit/test_single_mutation_path.py`, `tests/unit/test_no_role_name_literal.py`, `tests/support/fake_github.py`, `tests/support/fake_claude_cli.py`, `tests/support/fake_cli.py`, `tests/support/git_repo.py`, `tests/db/test_publish_step.py`, `tests/integration/test_secret_redaction_e2e.py`, `tests/support/log_sink.py`, `tests/support/fake_artifacts.py`, `tests/integration/test_real_pipeline_zero_config.py`, `tests/conftest.py` (relevant fixtures) — all read directly this session.
- `.planning/phases/12-observability-audit-surface/12-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/config.json`, `pyproject.toml`, `.github/workflows/ci.yml` — all read directly this session.
- `pip show rich` (this environment) — confirmed installed version 13.7.1.

### Secondary (MEDIUM confidence)
- None — this research required no external documentation lookups; every claim is either read directly from this repository's own source/tests this session (`[VERIFIED]`) or explicitly flagged `[ASSUMED]` (rich API stability across minor versions) and logged in the Assumptions table above. `.planning/config.json` has every external search provider (`brave_search`, `exa_search`, `tavily_search`, `firecrawl`, `ref_search`, `perplexity`, `jina`) set to `false`, consistent with this being an internal-codebase research task rather than a new-framework investigation.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency; existing pin/version confirmed via direct tool check this session
- Architecture (read-model split, event-emission call sites, git-read gap): HIGH — every claim traced to an exact file and line range read this session, not inferred
- Pitfalls (clarification-comment redaction gap, worktree-removal gap): HIGH — both are direct readings of current production code, reproducible by anyone re-reading the same lines, not speculation about what *might* go wrong

**Research date:** 2026-10-03
**Valid until:** 30 days (stable internal codebase; no external API/library surface this research depends on is expected to change inside that window)
