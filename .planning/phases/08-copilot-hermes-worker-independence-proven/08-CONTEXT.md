# Phase 8: Copilot & Hermes — Worker Independence Proven - Context

**Gathered:** 2026-09-21
**Status:** Ready for planning

<domain>
## Phase Boundary

`CopilotWorker` and `HermesWorker` become real, functional `CodingWorker`
adapters — following exactly the shape `ClaudeCodeWorker` (Phase 7) already
proved: spawn the CLI non-interactively, normalize output to `WorkerResult`,
resume through native session id or context reconstruction per
`WorkerCapabilities`, killed by process-group timeout if hung. Both new names
already resolve in `WorkerRegistry` (`default_registry`) to
`_NotYetImplementedWorker` placeholders naming "Phase 8" — this phase swaps
those placeholders for real factories, the same way 07-01 did for
`claude-code`.

The phase's headline proof is *independence*, not just two new adapters:
reassigning roles across all three real runtimes in configuration must
require zero workflow-code change (WORK-09), each adapter's own integration
suite must skip — not fail — when that runtime's credentials/CLI are absent
(QUAL-03), and the shared `CodingWorker` contract-test suite
(`tests/contract/test_coding_worker_contract.py`, `WORKER_FACTORIES`) must
pass against all four workers (`FakeWorker`, `ClaudeCodeWorker`,
`CopilotWorker`, `HermesWorker`).

This phase also resolves ROADMAP.md's Open Decision 3 — the exact
non-interactive flag/env matrix for the Copilot and Hermes CLIs — but see
D-02 below: resolved from documentation now, not from a live hands-on spike,
because neither CLI is installed in this environment.

Out of scope (belongs to later phases): the independent quality gate and
feedback loops (Phase 9); GitHub issue intake and publishing (Phase 10);
cross-machine/CI resume (Phase 11); observability surface (Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Copilot credential boundary
- **D-01:** `Settings` gains a new, separate optional credential field for
  the Copilot CLI (e.g. `copilot_github_token: SecretStr | None = None`),
  distinct from Dark Factory's own `github_token`. This mirrors D-02 from
  07-CONTEXT.md (`anthropic_api_key`) exactly: absence only surfaces as a
  clear, typed error when a run actually tries to invoke a `copilot` role,
  and the value flows to the subprocess exclusively through
  `build_worker_env(role, env_var_name=..., value=...)` — never through
  `os.environ.copy()`. This keeps Dark Factory's infra `GITHUB_TOKEN`
  (TOOL-04/SEC-01's protected credential — used for Dark Factory's *own*
  git/GitHub actions, e.g. push/PR) categorically separate from whatever
  GitHub-scoped credential the Copilot CLI itself authenticates with as a
  worker, even though both are technically GitHub PATs — conflating them
  would make it impossible to reason about "did the infra credential ever
  reach a worker" from the field name alone. — **Reversibility:** reversible
  — a Settings-field/validation-timing choice only, no persisted schema.

### CLI access & spike approach
- **D-02:** Neither `copilot` nor `hermes` is installed in this environment.
  Both adapters are implemented this phase against CLAUDE.md's already-
  documented, already-researched invocation patterns (`copilot -p "<prompt>"
  --no-ask-user --allow-tool 'shell(pytest)' --allow-tool write --model
  <pin>`; `hermes chat -q "<prompt>"` / `--oneshot` print mode) rather than
  from a live hands-on spike in a clean container. Each adapter's
  integration test suite is written and `pytest.mark.skipif`-guarded on
  CLI/credential absence — this is not a workaround invented for this
  decision, it is QUAL-03's own literal requirement ("skipped — not failed
  — when that runtime's credentials are absent"), so the real spike (and
  ROADMAP.md's Open Decision 3 resolution being genuinely *validated*
  against a live binary, not just documented) happens whenever the CLIs are
  actually installed, without blocking this phase. Contract-suite coverage
  (QUAL-02's "fake cannot diverge from real semantics" guarantee) is proven
  the same way 07-03 proved it for `ClaudeCodeWorker`: against a faked CLI
  executable on `PATH`, never a live binary — see
  `tests/support/fake_claude_cli.py` for the exact pattern to mirror.
  — **Reversibility:** reversible — nothing about the adapter's shape
  depends on this; a later live spike can only refine/correct flag details
  inside the same module, not change the architecture.

### NEEDS_INPUT signal reuse
- **D-03:** `CopilotWorker` and `HermesWorker` reuse Claude Code's exact
  pause-signal convention verbatim — the same `NEEDS_INPUT_MARKER` literal
  (`"NEEDS_INPUT:"`), the same `NEEDS_INPUT_PROTOCOL` prompt text, and (where
  practical to share rather than duplicate) the same `_NEEDS_INPUT_RE`
  MULTILINE+DOTALL extraction regex from `workers/claude_code.py`. One
  shared pause contract across all three adapters means HITL-01/02 behavior
  at the orchestrator level is identical regardless of which worker a role
  is assigned to, and the shared contract suite can pin pause/resume
  semantics once instead of three times. Planning decides whether the
  marker constant/regex is extracted to a shared module (e.g.
  `workers/needs_input.py`) or duplicated per adapter — either is
  acceptable as long as the literal marker text and extraction semantics
  are identical across all three. — **Reversibility:** reversible — the
  convention lives entirely in adapter-side parsing/prompting; changing it
  later touches adapter modules and role instruction text, no persisted
  schema.

### Role-reassignment proof scenario (WORK-09 / SC2)
- **D-04:** The SC2 proof uses ROADMAP.md's own literal example: Architect
  on `copilot`, Developer on `claude-code`, QA on `hermes` (BA's worker is
  planning's discretion — `fake` or `claude-code` are both fine, since BA
  isn't named in the roadmap's example and isn't load-bearing for the
  independence proof). This makes the SC2 test/demo a direct, literal
  satisfaction of the phase's own stated goal wording, not a
  planning-invented permutation. Requires: `.dark-factory/roles/*.yaml`
  `worker:` fields updated for `ARCHITECTURE`→`copilot` and `QA`→`hermes`
  (`DEVELOPMENT` already effectively slots to `claude-code` per Phase 7),
  and confirmation that the run still completes with zero workflow-code
  change — the config edit alone is proof of WORK-09.

### Claude's Discretion
- Exact `Settings` field name for the Copilot credential beyond
  "distinct from `github_token`" (D-01) — e.g. `copilot_github_token` vs.
  another name — and the exact typed error class/message on first missing
  use, mirroring `MissingWorkerCredentialError`'s existing shape.
- Whether Hermes needs its own `Settings` credential field at all, and
  what it's named — CLAUDE.md's Hermes row documents no explicit credential
  requirement the way Claude Code (`ANTHROPIC_API_KEY`) and Copilot (GitHub
  auth) do; planning/research should confirm from Hermes CLI docs whether
  one exists (e.g. a NousResearch API key) before assuming none is needed.
- Whether the `NEEDS_INPUT` marker/regex (D-03) is extracted to a shared
  module or duplicated per adapter file.
- Exact module/class names (`CopilotWorker`, `HermesWorker` are the obvious
  choices, matching `ClaudeCodeWorker`'s naming convention) and file
  locations (`workers/copilot.py`, `workers/hermes.py`, mirroring
  `workers/claude_code.py`).
- Per-adapter `WorkerCapabilities` values (`native_resume`, `session_id`,
  `non_interactive`, `structured_output`) — derive honestly from what each
  CLI's documented behavior actually supports; CLAUDE.md's own docs suggest
  neither Copilot nor Hermes documents a session-resume concept the way
  Claude Code's `--resume <session_id>` does, so both likely default to
  `native_resume=False` (context-reconstruction resume, per HITL-05's
  existing "orchestrator issues the identical call either way" contract) —
  but this should be confirmed against actual CLI docs during research, not
  assumed here.
- Whether Copilot's and Hermes's `NATIVE_TOOL_CONTRACT` entries (already
  fully specified in `tools/native.py` for all three runtimes, including
  Hermes's honest "no documented per-tool native restriction flag" note)
  need any adjustment once the adapters are actually built — the design
  contract predates this phase and should be the adapters' first real
  consumer for these two runtimes, same as 07-04 did for Claude Code.
- Exact skip condition/message for each adapter's integration suite (D-02)
  — e.g. checking for the binary on `PATH` via `shutil.which` vs. checking
  for the credential env var vs. both.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WORK-05, WORK-06, WORK-09, QUAL-03 (this
  phase's full requirement set)
- `.planning/ROADMAP.md` §"Phase 8: Copilot & Hermes — Worker Independence
  Proven" — goal, four success criteria, and Open Decision 3 (exact
  non-interactive flag/env matrix for Copilot and Hermes)

### The Phase 7 adapter this phase mirrors structurally
- `src/dark_factory/workers/claude_code.py` — `ClaudeCodeWorker`: the exact
  template both new adapters follow (spawn pattern, `NEEDS_INPUT` marker
  parsing, credential-missing error shape, `_spawn_and_parse`-style shared
  pipeline for execute/resume, catch-all `try/except Exception` so the
  adapter never raises out of `execute()`/`resume()`)
- `.planning/phases/07-claude-code-the-first-real-worker/07-CONTEXT.md` —
  D-01 (NEEDS_INPUT marker convention, reused verbatim per D-03 above),
  D-02 (lazy credential validation pattern, reused per D-01 above), D-03
  (single generous `Settings.worker_timeout_seconds` knob — already shared,
  no new decision needed this phase), D-04 (log streaming to
  `logs/<role>/` — already shared, no new decision needed this phase)

### Worker contract & registry this phase completes
- `src/dark_factory/workers/base.py` — the `CodingWorker` ABC every adapter
  implements
- `src/dark_factory/domain/worker.py` — `WorkerResult`, `WorkerResultStatus`,
  `WorkerCapabilities` — the exact normalized shape both adapters must
  produce
- `src/dark_factory/workers/registry.py` — `WorkerRegistry`,
  `default_registry`; `"copilot"`/`"hermes"` currently resolve to
  `_NotYetImplementedWorker("copilot"/"hermes", "8")` — this phase replaces
  both with real factory registrations, the same edit 07-01 made for
  `"claude-code"`
- `tests/contract/test_coding_worker_contract.py` — `WORKER_FACTORIES`;
  Phase 8 appends `CopilotWorker` and `HermesWorker` to this list
  (currently `[FakeWorker, ClaudeCodeWorker]`), proving QUAL-02 across all
  four workers
- `tests/support/fake_claude_cli.py` — the faked-executable-on-`PATH`
  technique 07-03 used to drive the contract suite against
  `ClaudeCodeWorker` with no live credential; the direct template for
  faking `copilot`/`hermes` executables the same way (D-02)

### Credential boundary & subprocess patterns to reuse
- `src/dark_factory/tools/env.py` — `build_worker_env()`,
  `WORKER_ENV_ALLOWLIST` — the exact allowlist-from-empty-dict function both
  new adapters must call when spawning their CLI, same as Claude Code
- `src/dark_factory/config/settings.py` — `Settings`, `known_secret_values()`
  — where D-01's new Copilot credential field (and any Hermes credential
  field, per Claude's Discretion) is added; `known_secret_values()` already
  walks `model_fields` for `SecretStr` so a new field is covered
  automatically with zero extra redaction wiring
- `.claude/CLAUDE.md` §"Invoking the agent CLIs" — the exact documented
  non-interactive invocation patterns for Copilot CLI and Hermes this phase
  builds against (D-02): `copilot -p "<prompt>" --no-ask-user --allow-tool
  'shell(pytest)' --allow-tool write --model <pin>`; `hermes chat -q
  "<prompt>"` / `--oneshot` print mode, no PTY/tmux

### Native tool restriction — already decided, applies to both new adapters
- `src/dark_factory/tools/native.py` — `NATIVE_TOOL_CONTRACT`,
  `NativeToolGrant` — already contains fully specified `copilot`/`hermes`
  entries for every capability (Copilot: narrow repeated `--allow-tool`
  values; Hermes: honest "no documented per-tool native restriction flag"
  for every capability). This phase's two adapters are their first real
  runtime consumers, the same way `ClaudeCodeWorker` became
  `NATIVE_TOOL_CONTRACT`'s first consumer in 07-04.
  `tests/unit/test_native_tool_contract.py`'s `_ALLOWED_CONSUMERS` allowlist
  needs both new adapter modules added.

### Config & role assignment (D-04)
- `.dark-factory/roles/*.yaml` — `worker:` field per role; all four
  currently say `worker: fake`. This phase's SC2 proof edits
  `ARCHITECTURE.yaml`→`copilot`, `QA.yaml`→`hermes` (and confirms
  `DEVELOPMENT.yaml`→`claude-code` still holds from Phase 7)
- `.dark-factory.yaml` — repo-level config; no change expected here, the
  reassignment happens entirely in per-role YAML

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ClaudeCodeWorker` (`workers/claude_code.py`) — not just a pattern to
  follow but the literal shape to copy: `_spawn_and_parse` pipeline,
  `NEEDS_INPUT` regex, `attempt_log_paths()`, `_RESULT_METADATA_KEYS`
  copy-verbatim-if-present convention, `MissingWorkerCredentialError` shape
  — both new adapters should structurally mirror this file, adjusted for
  each CLI's own argv/output shape.
- `build_worker_env()` (`tools/env.py`) — the credential-bounded subprocess
  pattern already proven twice (Claude Code, `shell.execute`); this phase
  is its third and fourth application.
- `NATIVE_TOOL_CONTRACT` (`tools/native.py`) — Copilot/Hermes translation
  entries already fully written; no new design work needed to derive the
  `--allow-tool`/no-native-restriction mapping.
- `tests/support/fake_claude_cli.py` — direct template for
  `fake_copilot_cli.py`/`fake_hermes_cli.py`-style faked executables the
  contract suite and each adapter's own unit tests spawn instead of a live
  binary.

### Established Patterns
- `frozen=True, extra="forbid"` on every pydantic boundary model.
- Explicit-allowlist-from-empty-dict for subprocess environments — now a
  4th/5th application (Copilot, Hermes) of the same discipline
  (`git_env()`, `build_worker_env()`, `ClaudeCodeWorker`).
- `SecretStr` + `known_secret_values()` walking `model_fields` — any new
  Settings credential field (D-01, and Hermes's per Claude's Discretion) is
  automatically covered.
- Adapters never import orchestrator/workflow/persistence code — carries
  forward unchanged as a roadmap invariant for both new adapters.
- Catch-all `try/except Exception` wrapping the entire adapter body so
  `execute()`/`resume()` never raise — `ClaudeCodeWorker`'s explicit
  rationale (an escaping exception strands `role_executions` at RUNNING
  with no terminal event) applies identically to both new adapters.

### Integration Points
- `src/dark_factory/workers/registry.py` — swap both
  `default_registry.register("copilot"/"hermes", lambda: _NotYetImplementedWorker(...))`
  lines for real factories.
- `src/dark_factory/config/settings.py` — new Copilot credential field
  (D-01) and possibly a Hermes credential field.
- `tests/contract/test_coding_worker_contract.py` — `WORKER_FACTORIES`
  gains `CopilotWorker`, `HermesWorker`.
- `tests/unit/test_native_tool_contract.py` — `_ALLOWED_CONSUMERS` gains
  both new adapter modules.
- New `src/dark_factory/workers/copilot.py` and
  `src/dark_factory/workers/hermes.py` modules, exempt from the
  worker-name-leak guard by living under `workers/` (already exempt).
- `.dark-factory/roles/ARCHITECTURE.yaml` (`worker: copilot`),
  `.dark-factory/roles/QA.yaml` (`worker: hermes`) — D-04's reassignment.

</code_context>

<specifics>
## Specific Ideas

No particular naming beyond what's captured in the decisions above. The
user chose the recommended option at every branch point in this
discussion: a separate Copilot credential field kept categorically apart
from Dark Factory's own `GITHUB_TOKEN`, proceeding with documentation-only
adapter implementation now (real CLI spike deferred, not blocking, matching
QUAL-03's own skip-when-absent design), reusing Claude Code's exact
`NEEDS_INPUT:` pause convention verbatim across all three adapters for one
shared pause contract, and using ROADMAP.md's own literal role-reassignment
example (Architect→Copilot, Developer→Claude Code, QA→Hermes) as the SC2
proof scenario.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. The live hands-on spike of the
real `copilot`/`hermes` CLIs (D-02) is explicitly deferred to whenever
those CLIs are actually installed — not treated as a backlog item requiring
a future phase, since QUAL-03's skip-when-absent integration tests already
accommodate it without blocking this phase's completion. Phase 9's
independent quality gate, Phase 10's GitHub intake/publishing, and later
phases remain unchanged by this discussion.

### Reviewed Todos (not folded)
None — `.planning/todos/pending/` is empty and `todo.match-phase` returned
zero matches for Phase 8.

</deferred>

---

*Phase: 8-Copilot & Hermes — Worker Independence Proven*
*Context gathered: 2026-09-21*
