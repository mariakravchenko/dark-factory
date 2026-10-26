# Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume - Research

**Researched:** 2026-09-26
**Domain:** GitHub REST API integration (githubkit), webhook receipt/verification, git-lifecycle idempotency under crash-resume
**Confidence:** MEDIUM — codebase-grounded architecture findings are HIGH; exact `githubkit` method signatures could not be fetched verbatim and are MEDIUM/LOW pending a first-implementation-step confirmation (see Assumptions Log)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** A new, separate webhook-receiver process (per the tech-stack doc's suggested pattern) verifies the GitHub webhook signature (using a new `Settings.github_webhook_secret: SecretStr | None`), parses the `issue_comment` payload, and resolves it to a `(run_id, interaction)` pair. This is new deployable surface but matches GIT-06's literal "GitHub event handler" framing; it does not attempt cross-machine/CI trigger unification — that generalization is explicitly Phase 11's job (TRIG-01/04). — **Reversibility:** reversible.
- **D-02:** The webhook process calls the existing `submit_answer(run_id, answer, session_factory=...)` (`orchestrator/answers.py:67-150`) directly, in-process, against the same database — no new mutation path, no separate "mark claimable and wait for something else to pick it up" indirection. Same lease/idempotency guarantees CLI resume already gets. — **Reversibility:** reversible.
- **D-03:** `githubkit` (already the pinned dependency per CLAUDE.md's tech stack) is added to `pyproject.toml` and used for issue fetch (title/body/comments/labels), comment posting, and PR creation. It is not currently a dependency — this phase adds it.
- **D-04:** `RepositoryConfig` (`config/repo_config.py`) gains `github_owner`/`github_repo` fields alongside its existing `base_branch`, as explicit repo-level config rather than derived from the checked-out git remote. `Settings` gains `github_webhook_secret: SecretStr | None = None`, mirroring the existing `github_token: SecretStr | None` optional-credential shape (Phase 5's D-16 precedent). The existing `Settings.github_token` is reused for GitHub API auth — no new token type.
- **D-05:** `human_interactions` gains a `clarification_comment_id` column (the posted GitHub comment's id) and a `github_comment_id` column recording the id of the comment that answered it. Before posting a clarifying question, the publish/ask step checks `clarification_comment_id`; if already set, it skips re-posting. A duplicate webhook delivery for the same answering comment is a no-op once the interaction is already `ANSWERED` with that `github_comment_id` — the durable business-level dedup key (not `X-GitHub-Delivery`). — **Reversibility:** reversible.
- **D-06:** `Run` gains a new `published_commit_sha` column, distinct from `RoleExecution.wip_commit_sha`. Before acting on the publish step, Dark Factory checks `branch exists` + `published_commit_sha set` + `pr_number set` together. `Run.pr_number`/`Run.pr_url` (existing, unused since Phase 5) are the PR-side identifiers; no new columns needed there.
- **D-07:** Phase 10 adds the real `PUBLISH_STARTED`, `PR_CREATED`, and `PUBLISH_FAILED` event types to `events/catalog.py` now. The catalog's docstring is corrected to attribute them to Phase 10; Phase 12 becomes a consumer, not their origin. — **Reversibility:** costly (renaming after emission needs a data migration).
- **D-08:** Each `ROLE_NEEDS_INPUT` on a GitHub-sourced run posts a fresh issue comment (never edits a prior one), lightly prefixed for identifiability (e.g. bold "Dark Factory needs input:"), no run-id or internal metadata leaked. Consistent with `human_interactions`' existing partial-unique-index (one `WAITING` row per run).
- **D-09:** PR title = `NormalizedTask.title`; PR body = short generated summary linking back to the source issue, noting it was produced by Dark Factory; target/base branch = existing `RepoConfig.repository.base_branch` — no new branch-target config.

### Claude's Discretion

- Exact githubkit client wrapper shape (a thin `GitHubClient` module vs. direct githubkit calls at call sites) — following the existing `GitClient`/`shell_execute` precedent of one thin wrapper per external system.
- Exact webhook-receiver process technology (bare `httpx`/starlette handler vs. minimal FastAPI) — either satisfies D-01.
- Exact `EventType` payload shapes for `PUBLISH_STARTED`/`PR_CREATED`/`PUBLISH_FAILED` (D-07) — following existing `run_events` payload conventions (Phase 9's `QUALITY_GATE_*` shapes).
- Whether the PR body includes QA/gate verdict summaries (D-09 leaves the body "short generated summary").
- Exact migration/column types for `published_commit_sha`, `clarification_comment_id`, `github_comment_id`, `github_owner`, `github_repo` — following existing Alembic revision conventions.

### Deferred Ideas (OUT OF SCOPE)

None raised as new capabilities during discussion. Cross-machine/CI resume proof and unifying CLI/webhook/CI triggers into one entrypoint belong to Phase 11 (TRIG-01/04). The observability/audit surface beyond events this phase itself emits belongs to Phase 12. The quality gate and bounded feedback loops themselves shipped in Phase 9 — this phase only publishes after they PASS.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTAKE-03 | `dark-factory run github:152` pulls issue title/body/comments/labels/repo metadata into a `NormalizedTask` | Architecture Patterns § "Wiring `_load_github`"; Code Examples § githubkit issue fetch |
| GIT-03 | Publishing occurs only when QA=PASS and Gate=PASS; collects final diff, commits, pushes, creates PR, persists PR metadata, transitions to COMPLETED | Architecture Patterns § "Where the publish step lives"; reuses existing `collect_pr_diff`/`commit_run_artifacts`/`push_working_branch` |
| GIT-04 | Publishing is idempotent — retrying with an existing `pr_number` does not open a second PR; branch/commit-SHA/PR-number/comment-id checked before acting | Common Pitfalls § "The crash-between-API-call-and-commit gap"; Architecture Patterns § "GitHub-side idempotency check" |
| GIT-05 | For a GitHub-sourced run, post a clarification comment and stay `WAITING_HUMAN` until an answer is associated | Architecture Patterns § "Ask step"; Common Pitfalls § "Self-comment loop" |
| GIT-06 | A GitHub event handler receiving a new comment finds the associated run/interaction, stores the answer, resumes the same `RoleExecution`, never creates a new run | Architecture Patterns § "Webhook receiver"; Code Examples § webhook signature verification |
</phase_requirements>

## Summary

This phase wires GitHub as both a task *source* and a publishing *target*, using `githubkit` (already the project's pinned GitHub SDK per CLAUDE.md's tech-stack doc) for every GitHub REST call, and a small separate process for inbound webhooks. The codebase already has every extension seam this phase needs pre-built and unused: `_load_github` is a one-line stub waiting for a real body (`input/loaders.py:96-99`), `Run.pr_number`/`pr_url` are migrated-but-never-written columns (`persistence/models.py:133-134`), and `PublishingConfig.create_pr` already gates PR creation in its own docstring. The one mutation path (`persistence/mutations.py`) and the terminal-role post-worker block in `orchestrator/runner.py` (where Phase 9's quality gate already lives) are the two places nearly all new code attaches.

The single most important architectural finding from reading the actual pipeline code: **`RunStatus.PUBLISHING` and `RunStatus.VERIFYING` are declared enum members with no reachable transition** — `lifecycle.py::transition()` maps a terminal role's `ROLE_COMPLETED` signal directly to `RunStatus.COMPLETED`, never through an intermediate status. Phase 9's quality gate already established the precedent this phase should follow: run the extra work (gate, and now publish) as synchronous, in-process, post-worker code inside `_run_current_role`'s terminal-role block, *before* `apply_transition` is called — not as a new lifecycle hop. This means a crash during publish leaves the role's `role_executions` row at `RUNNING` and, on resume, the terminal role's *worker* re-executes too (exactly as a crash during the Phase 9 gate already does) — this is pre-existing, accepted behavior, not something Phase 10 introduces.

The second critical finding, directly relevant to GIT-04/success-criterion-3: a **pure DB-flag check ("is `pr_number` set?") cannot by itself close the crash window between a successful GitHub API call and the local commit that records its result** — because if the process dies in that exact window, the DB still shows `pr_number IS NULL` on resume, and a naive idempotency check would create a second PR. The codebase already contains the correct pattern for this class of problem: Phase 5's WIP-recovery commit (`A-05-06`) checks **git's own state** (`head_sha` before/after) rather than only a DB column, so a resumed process that already made the recovery commit sees no diff and skips re-committing. The direct analogue for GIT-04 is to check **GitHub's own state** before creating a PR (list existing pulls for the working branch) as the crash-safety net underneath the faster DB-flag check — this is additive to D-06, not a contradiction of it, and is flagged prominently below as both a Common Pitfall and a recommended Architecture Pattern.

A third, non-obvious finding: because Dark Factory posts its own clarification comment using its own `github_token` identity, and GitHub's `issue_comment` webhook fires for *every* comment including ones Dark Factory itself just posted, **the webhook handler must actively exclude Dark Factory's own comments** before attempting to resolve an "answer" — otherwise posting the question comment can immediately trigger a self-answer with the question's own text. This is flagged as a Common Pitfall.

**Primary recommendation:** Add a thin `github/client.py` (`GitHubClient`) wrapping `githubkit.GitHub` for the three call shapes (issue fetch, comment post, PR create), following the existing `GitClient`/`shell_execute` one-wrapper-per-external-system precedent; do the publish work synchronously in `orchestrator/runner.py`'s existing terminal-role block, immediately after the `QUALITY_GATE_PASSED` branch; check GitHub's own state (existing PR for branch) as well as the persisted flags before creating a PR; and build the webhook receiver as a small `httpx`/starlette-class handler (or minimal FastAPI) that does nothing but verify signature, parse payload via `githubkit.webhooks.parse`, filter out Dark Factory's own comment identity, resolve `(run_id, interaction)`, and call `submit_answer` in-process.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| GitHub issue/comment/label fetch (intake) | Backend / Orchestrator core | — | `input/loaders.py::_load_github` runs inside `start_run`, before any DB row exists; it is orchestration-tier code, not a role's tool call |
| Clarification comment posting | Backend / Orchestrator core | — | Runs inside `_run_current_role`'s `ROLE_NEEDS_INPUT` branch, in the same process as the lifecycle mutation, alongside the existing `HumanInteractionWrite(mode="ask")` write |
| Webhook receipt + signature verification | New standalone process (Backend) | — | D-01: a separate deployable, not a role, not a CLI command; talks to the same Neon database as the CLI process |
| Answer resolution + resume | Backend / Orchestrator core (`orchestrator/answers.py`) | Webhook process (caller only) | D-02: the webhook process is a *caller* of `submit_answer`, never a second mutation path — `submit_answer` itself is unchanged infra already covered by Phase 2's lease/HITL-07 guarantees |
| Branch/commit/push (publish) | Backend / Orchestrator core (`git/diff.py`, `git/worktree.py`) | — | Already exists from Phase 5; Phase 10 adds only the PR-creation call on top of the existing commit/push primitives |
| PR creation | Backend / Orchestrator core | External API (GitHub) | A new githubkit call site alongside `push_working_branch`, gated by `PublishingConfig.create_pr` |
| Persisted identifiers (`pr_number`, `pr_url`, `published_commit_sha`, `clarification_comment_id`, `github_comment_id`) | Database / Storage (Neon via `persistence/mutations.py`) | — | ORCH-06: the *only* write path for these is `apply_transition`/`create_run`; no other module may construct or assign them |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `githubkit` | `>=0.16,<0.17` (0.16.1 confirmed current) [VERIFIED: pip index versions githubkit] | Issue/comment/PR REST calls, webhook signature verification, webhook payload parsing | Locked by D-03; already the project's chosen tech-stack pin (fully typed, auto-generated from GitHub's OpenAPI spec, ships a dedicated `githubkit.webhooks` module for exactly this phase's signature-verify + typed-parse needs) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | transitive via `githubkit` (`>=0.28,<1`, already in the tech-stack doc) | Underlying HTTP transport for `githubkit`; optionally the webhook receiver's own minimal server if not using FastAPI | Already pulled in by `githubkit`; do not add a second HTTP client for the receiver — reuse if a bare handler is chosen |
| `FastAPI` (optional) | not yet a dependency | Minimal webhook receiver framework, if the bare-`httpx`/starlette route is not chosen | Left to planning discretion per CONTEXT.md; only needed if the receiver wants request-body/header parsing conveniences beyond stdlib `http.server`/starlette |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `githubkit` | `PyGithub` | Locked out by D-03 (githubkit already the project's chosen SDK); PyGithub lacks first-class webhook payload models and is REST-only |
| Separate webhook process (FastAPI/starlette) | Bare `http.server`/`socketserver` stdlib handler | Works but reimplements request parsing, header access, and content-length handling that starlette/FastAPI already handle; not recommended given the low marginal cost of one more dependency for a security-sensitive parsing path |
| GitHub-state PR-existence check (recommended below) | DB-flag-only idempotency check | A DB-only check cannot detect "PR was created on GitHub but the commit that would have recorded it never landed" — the exact crash scenario success-criterion-3 names |

**Installation:**
```bash
uv add "githubkit>=0.16,<0.17"
# If the webhook receiver uses FastAPI (discretionary):
uv add "fastapi>=0.115,<1" "uvicorn>=0.34,<1"
```

**Version verification:** `githubkit==0.16.1` confirmed current on PyPI via `pip index versions githubkit` [VERIFIED: pip index versions githubkit, run this session] — matches the version already pinned in `.claude/CLAUDE.md`'s tech-stack table (sourced there from the PyPI JSON registry API on 2026-09-06).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `githubkit` | PyPI | latest release 2026-08-14; project active since 2023 | unknown (registry lookup returned no download-count signal) | `github.com/yanyongyu/githubkit` | **SUS** (`unknown-downloads`) [tool-verdict: `gsd_run query package-legitimacy check --ecosystem pypi githubkit`] | Kept — already a locked project decision (D-03) and independently named with sources in `.claude/CLAUDE.md`'s tech-stack doc; **planner must add a `checkpoint:human-verify` task before `uv add githubkit`**, per the SUS protocol, even though the package is a known, actively-maintained, typed GitHub SDK (16k+-star-class project referenced by name in the project's own architecture doc) |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `githubkit` — automated verdict driven by a missing download-count signal in this environment's registry lookup, not by any actual red flag (repo exists, is not deprecated, has no postinstall script); still gated behind `checkpoint:human-verify` per protocol.

*The package name `githubkit` itself was discovered via the project's own `.claude/CLAUDE.md` tech-stack table (a project-locked decision, itself sourced from the PyPI JSON registry API per that document's own Sources section) — treated as `[VERIFIED: pip index versions, cross-checked against CLAUDE.md's cited PyPI source]`, not `[ASSUMED]`, because the name did not originate from this session's web search.*

## Architecture Patterns

### System Architecture Diagram

```
GitHub issue #152                     GitHub issue comment webhook (issue_comment: created)
       │                                              │
       ▼                                              ▼
 dark-factory run github:152                 webhook-receiver process (NEW, D-01)
       │  cli.py::run()                              │  verify signature (githubkit.webhooks.verify)
       │  load_effective_config() -> snapshot         │  parse payload  (githubkit.webhooks.parse)
       │  start_run(source, snapshot=snapshot)         │  filter: is this Dark Factory's own comment? -> drop
       │      classify("github:152") -> (GITHUB,"152") │  resolve (run_id, interaction) from issue+comment
       │      load(GITHUB, "152", repository=snapshot["repository"])   │  submit_answer(run_id, answer)  (D-02, in-process)
       │          _load_github: GitHubClient.fetch_issue(owner,repo,152)
       │              -> issue title/body/comments/labels             ▼
       │          -> NormalizedTask(source_kind="github", ...)   orchestrator/answers.py::submit_answer
       │      create_run(...)  [one mutation path]                    │  same run_lease() as CLI resume (HITL-07)
       ▼                                                              │  apply_transition(WAITING_HUMAN -> role, ...)
 orchestrator drive loop (advance/_advance_once/_run_current_role)    ▼
       │  ... BA -> ARCHITECTURE -> DEVELOPMENT -> QA ...      role re-enters via worker.resume(...)
       │  (unchanged: orchestrator is source-agnostic past NormalizedTask)
       ▼
 QA role completes (terminal role, next_node(pipeline, "QA") is None)
       │
       ▼
 verdict.json PASS?  ── FAIL ──> bounce/fail (Phase 9, unchanged)
       │ PASS
       ▼
 quality gate runs (Phase 9, unchanged) ── FAIL ──> bounce/fail (unchanged)
       │ PASS
       ▼
 PUBLISH STEP (NEW, synchronous, same post-worker block as the gate — no new RunStatus hop)
       │  commit_run_artifacts + push_working_branch (existing, git/diff.py)
       │  check: branch exists? published_commit_sha set? pr_number set? (D-06, fast DB path)
       │  if not: check GitHub's own PR list for this head branch (crash-safety net, see Pitfalls)
       │  if no PR found either way: GitHubClient.create_pr(owner, repo, title, head, base, body)
       │  patch-write published_commit_sha / pr_number / pr_url  (one mutation path, ordinary apply_transition)
       ▼
 apply_transition(ROLE_COMPLETED -> COMPLETED)  [unchanged shape from lifecycle.transition()]
```

### Recommended Project Structure

```
src/dark_factory/
├── github/                      # NEW package -- mirrors git/ (one dir per external system)
│   ├── __init__.py              # typed error hierarchy (GitHubApiError, ...), mirrors dark_factory.git's __init__
│   └── client.py                # GitHubClient: fetch_issue, create_comment, create_pull_request, find_pull_request_for_branch
├── input/
│   └── loaders.py                # _load_github: replace the stub, call GitHubClient
├── config/
│   └── repo_config.py            # RepositoryConfig gains github_owner / github_repo (D-04)
├── config/
│   └── settings.py                # Settings gains github_webhook_secret: SecretStr | None (D-04)
├── orchestrator/
│   └── runner.py                  # publish step added to the existing terminal-role post-worker block
├── events/
│   └── catalog.py                 # + PUBLISH_STARTED, PR_CREATED, PUBLISH_FAILED (D-07)
├── persistence/
│   ├── models.py                  # Run.published_commit_sha; HumanInteraction.clarification_comment_id / github_comment_id
│   └── mutations.py                # RoleExecutionWrite/HumanInteractionWrite/new RunFieldsWrite-style param for publish columns
└── webhook/                       # NEW, SEPARATE deployable (D-01) -- not imported by the orchestrator core
    ├── __init__.py
    ├── app.py                     # the FastAPI/starlette app: one POST route
    └── resolve.py                 # (run_id, interaction) resolution from an issue_comment payload

migrations/versions/
└── 000X_github_publishing_columns.py   # published_commit_sha (runs), clarification_comment_id + github_comment_id (human_interactions)
```

### Pattern 1: Threading repo config into `_load_github` (a signature gap CONTEXT.md leaves to planning)

**What:** `start_run(source, *, snapshot)` currently calls `load(kind, locator)` with no config. `_load_github` needs `github_owner`/`github_repo` from the resolved `.dark-factory.yaml` (D-04) to know which repository's issue to fetch — the CLI argument (`github:152`) carries only the issue number, never owner/repo.
**When to use:** Any time a loader needs config the CLI-level `load_effective_config` already resolved but `classify`/`load` doesn't currently see.
**Why this matters:** Without this thread-through, `_load_github` has no way to know which repository to call `githubkit` against, and INTAKE-03 cannot be implemented as literally as `dark-factory run github:152` (no owner/repo in the CLI invocation) without it.
**Recommended shape** (extends, not replaces, existing signatures — verified against the actual current signatures read this session):

```python
# input/loaders.py -- current signature (verified: src/dark_factory/input/loaders.py:109-111)
# def load(kind: SourceKind, locator: str) -> NormalizedTask:
#     return _LOADERS[kind](locator)

# Recommended: thread an optional repository config through, defaulting to None so
# _load_text / _load_spec need no change (they ignore the new parameter).
def load(
    kind: SourceKind,
    locator: str,
    *,
    repository: Mapping[str, Any] | None = None,
) -> NormalizedTask:
    return _LOADERS[kind](locator, repository=repository)  # each loader accepts **kwargs or the named param

# orchestrator/runner.py::start_run -- current call site (verified: src/dark_factory/orchestrator/runner.py:277-278)
# kind, locator = classify(source)
# task = load(kind, locator)
# Recommended:
kind, locator = classify(source)
task = load(kind, locator, repository=snapshot.get("repository"))
```

### Pattern 2: Where the publish step lives (no new `RunStatus` hop)

**What:** `RunStatus.PUBLISHING` and `RunStatus.VERIFYING` are declared members of the enum [VERIFIED: src/dark_factory/domain/status.py:37-38 — `VERIFYING = "VERIFYING"` / `PUBLISHING = "PUBLISHING"`] but `lifecycle.py::transition()` has no branch that ever returns either of them — the only `ROLE_COMPLETED` outcomes are "advance to the next pipeline node" or, when `next_node(pipeline, role) is None`, `RunStatus.COMPLETED` directly [VERIFIED: src/dark_factory/orchestrator/lifecycle.py:106-114 — `if following is None: return RunStatus.COMPLETED, role, state.current_step`].
**When to use:** Any terminal-role side effect that must happen after the worker completes but before the run reaches `COMPLETED` (Phase 9's quality gate is the existing example; Phase 10's publish step is the same shape).
**Recommended shape:** Insert the publish step in `orchestrator/runner.py`, in the same `if (signal is Signal.ROLE_COMPLETED and next_node(pipeline, node.name) is None):` block that already runs the quality gate [VERIFIED: src/dark_factory/orchestrator/runner.py:1071-1074], immediately after the `gate_result.status is VerdictStatus.PASS` branch, before `commit_run_artifacts` is called for this role's own gate-result artifact. A crash during the publish step leaves the role's row at `RUNNING` and the *worker* re-executes on resume — this is the exact, already-accepted behavior for a crash during the Phase 9 gate; Phase 10 does not change this contract, it only adds work inside the same crash-and-redo envelope.

```python
# Illustrative shape only -- exact insertion point and helper names are a
# planning decision, not verified against phase-10 code (none exists yet).
if gate_result.status is VerdictStatus.PASS:
    gate_events.append(EventWrite(type=EventType.QUALITY_GATE_PASSED, payload={...}))
    publishing_cfg = state.workflow.get("publishing", {})
    if publishing_cfg.get("create_pr", True):
        gate_events.append(EventWrite(type=EventType.PUBLISH_STARTED, payload={"role": node.name}))
        publish_result = run_publish_step(  # new function, mirrors run_quality_gate's shape
            work_dir=work_dir,
            run_id=run_id,
            state=state,
            settings=get_settings(),
        )
        gate_events.append(
            EventWrite(type=EventType.PR_CREATED, payload={"pr_number": publish_result.pr_number, "pr_url": publish_result.pr_url})
            if publish_result.pr_number is not None
            else EventWrite(type=EventType.PUBLISH_FAILED, payload={"error": publish_result.error})
        )
```

### Pattern 3: GitHub-side idempotency check (recommended addition to D-06's "checked before acting")

**What:** D-06's persisted-identifier check (`branch exists` + `published_commit_sha set` + `pr_number set`) is the correct *fast path*, but cannot by itself satisfy success-criterion-3's literal scenario — "killing the process **after the PR API call but before its identifier is committed**". In that exact window, `Run.pr_number` is still `NULL` on resume (nothing was ever persisted), so a check that only reads the DB would create a second PR.
**When to use:** Immediately before calling `pulls.create`, whenever the DB-flag check finds `pr_number IS NULL`.
**Recommended shape:** Mirror the WIP-recovery precedent's principle — check the *external system's own state*, not only the DB flag — by listing existing pull requests for the working branch as `head` before creating a new one:

```python
# Illustrative -- githubkit exposes GitHub's "list pulls" endpoint filtered by head,
# following the OpenAPI operationId convention githubkit auto-generates method names
# from (per the githubkit README: "auto-generated from the OpenAPI spec"). Exact
# method/parameter names are [ASSUMED] pending a first-implementation-step check
# (see Assumptions Log A2) -- confirm with `python -c "from githubkit import GitHub; help(GitHub.rest.pulls)"`
# against the installed 0.16.1 before writing this call site.
existing = client.rest.pulls.list(
    owner=owner, repo=repo, head=f"{owner}:{working_branch}", state="all"
)
if existing.parsed_data:
    pr = existing.parsed_data[0]
    pr_number, pr_url = pr.number, pr.html_url
else:
    created = client.rest.pulls.create(
        owner=owner, repo=repo, title=title, head=working_branch, base=base_branch, body=body
    )
    pr_number, pr_url = created.parsed_data.number, created.parsed_data.html_url
```

This is **additive** to D-06, not a contradiction: D-06's DB check still runs first and is the common-case fast path (skips the extra API call entirely once `pr_number` is durably recorded); this GitHub-side check only fires on the narrow "DB says no PR yet" branch, closing exactly the gap success-criterion-3 names.

### Pattern 4: Webhook receiver — signature verification and payload parsing via `githubkit.webhooks`

**What:** `githubkit` ships a dedicated `githubkit.webhooks` module with `verify()` and `parse()` functions, purpose-built for this — do not hand-roll `hmac.compare_digest` (see Don't Hand-Roll).
**Source (quoted verbatim):**

```python
# Source: https://yanyongyu.github.io/githubkit/usage/webhooks/ [CITED]
from githubkit.webhooks import verify

valid: bool = verify(secret, request.body, request.headers["X-Hub-Signature-256"])
```

```python
# Source: https://yanyongyu.github.io/githubkit/usage/webhooks/ [CITED]
from githubkit.webhooks import parse

event = parse(request.headers["X-GitHub-Event"], request.body)
```

**When to use:** Every inbound webhook POST, in this order: read the raw body (unparsed — the signature covers exact bytes [CITED: docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries]), call `verify(secret, raw_body, signature_header)` and reject (401/403) on `False` *before* doing anything else, then `parse("issue_comment", raw_body)` into a typed event object.
**Payload shape to resolve against** (issue_comment event): `action` is one of `"created" | "deleted" | "edited" | "pinned" | "unpinned"` [CITED: docs.github.com/en/webhooks/webhook-events-and-payloads]; only `action == "created"` is relevant for GIT-06. `comment.id` / `comment.body` identify the answering comment; `issue.number` + the repo identify the run (via a lookup keyed on `source_ref`/`github_owner`+`github_repo`+issue number, or on `clarification_comment_id`'s parent issue — a planning decision); `issue.pull_request` is present only for PR comments (absent for issue comments) [CITED: same source] — filter these out, since Dark Factory only asks questions on issues, never PRs; `sender`/`comment.user` identify who posted it (see Pitfall 3 — must exclude Dark Factory's own identity here).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Webhook signature verification | A hand-rolled `hmac.new(...).hexdigest()` + `hmac.compare_digest` comparison | `githubkit.webhooks.verify(secret, body, signature_header)` | Already ships in the pinned dependency, handles the `sha256=` prefix and encoding correctly, and is one fewer hand-written security-critical code path to review |
| Webhook payload parsing | Manual `json.loads(body)["comment"]["id"]` dict-poking | `githubkit.webhooks.parse(event_name, body)` (typed Pydantic v2 models) | Matches CLAUDE.md's own tech-stack rationale for githubkit ("optional data validation with Pydantic, for both webhook events and REST API responses") — a malformed/unexpected payload shape fails validation loudly instead of a `KeyError` deep in resolution logic |
| Idempotent PR creation | A bespoke "have I done this before" boolean flag as the *only* check | DB-flag fast path (D-06) **plus** GitHub-side "list pulls for this head branch" as the crash-safety net (Pattern 3 above) | A DB-only flag cannot distinguish "never attempted" from "attempted, succeeded on GitHub, crashed before the commit" — exactly the gap success-criterion-3 names |
| GitHub API auth signing | Manual `Authorization: Bearer` header construction | `githubkit.GitHub(token)` client construction | githubkit already handles token auth, retries, and pagination |

**Key insight:** Every hand-rolled piece in this list is a security- or correctness-critical parsing/comparison routine that a well-typed, already-adopted SDK already implements and tests upstream — hand-rolling any of them duplicates effort for a strictly worse result (untyped, unreviewed, no upstream test coverage).

## Common Pitfalls

### Pitfall 1: The crash-between-API-call-and-commit gap (GIT-04, success-criterion-3)

**What goes wrong:** The process is killed right after `pulls.create` returns 201 (PR now exists on GitHub) but before the `apply_transition` call that would record `pr_number`/`pr_url`/`published_commit_sha` ever commits. On resume, `Run.pr_number` is still `NULL`.
**Why it happens:** Any external side effect followed by a local commit has this window; it cannot be eliminated, only narrowed and defended against.
**How to avoid:** Before creating a PR, check GitHub's own state (list pulls for the working branch as `head`) in addition to the DB flag (Pattern 3 above) — this is the same principle the codebase already uses for the Phase 5 WIP-recovery commit (checks `head_sha` before/after against git's own state, not a DB column, to decide whether a commit already happened).
**Warning signs:** A test that "kills the process after the PR API call, before its identifier is committed, then resumes" and asserts `len(list_open_prs_for_branch) == 1` — this is close to success-criterion-3's own literal wording and should be provable end-to-end.

### Pitfall 2: Self-comment loop (GIT-05/GIT-06 interaction)

**What goes wrong:** Dark Factory posts its own clarification comment using `Settings.github_token`'s identity. GitHub's `issue_comment` webhook fires for **every** new comment on that issue, including the one Dark Factory itself just posted. If the webhook handler resolves "the run's pending interaction" purely from "there's a new comment on this issue and the run is `WAITING_HUMAN`", it will treat Dark Factory's own question as the human's answer — instantly self-answering the question with its own text.
**Why it happens:** Not addressed by D-05's dedup key (`github_comment_id`), which only prevents a *duplicate delivery of the same answer* from being double-counted — it doesn't prevent the *first* delivery being Dark Factory's own comment.
**How to avoid:** Before attempting to resolve an answer, compare the webhook's `comment.id` against the interaction's own `clarification_comment_id` (skip if equal) and/or compare `comment.user`/`sender`'s login/id against the identity behind `Settings.github_token` (fetched once, e.g. via `GET /user`, and cached) — reject self-authored comments outright.
**Warning signs:** A GitHub-sourced run reaches `WAITING_HUMAN`, then immediately transitions back out with an empty or question-text-echoing answer, with no human ever having replied.

### Pitfall 3: `github_owner`/`github_repo` unavailable to `_load_github` (INTAKE-03 signature gap)

**What goes wrong:** `start_run(source, snapshot=snapshot)` calls `classify(source)` then `load(kind, locator)` with no config passed through [VERIFIED: src/dark_factory/orchestrator/runner.py:277-278, quoted: `kind, locator = classify(source)` / `task = load(kind, locator)`]. `_load_github`, as currently stubbed, has no parameter for owner/repo at all [VERIFIED: src/dark_factory/input/loaders.py:96-99]. Without threading `snapshot["repository"]` through, `_load_github` cannot know which repository's issue to fetch.
**Why it happens:** `_load_text`/`_load_spec` never needed config, so `load()`'s signature was never extended.
**How to avoid:** Pattern 1 above — add an optional `repository` parameter to `load()`/each loader, defaulting to `None` so existing callers/tests for `text:`/`spec:` need no change.
**Warning signs:** `_load_github` raising `KeyError`/`AttributeError` reaching for owner/repo it was never given, or a hidden dependency on `os.environ`/a second config read (which would violate the "no live config read outside `cli.run()`" guard, `test_orchestrator_no_live_config_read.py`).

### Pitfall 4: Cross-ecosystem / hallucinated package names

**What goes wrong:** A GitHub-SDK-shaped Python package name resolved by memory/search rather than verified against PyPI directly (documented ~9% hallucination rate for this class of lookup).
**Why it happens:** Several similarly-named packages exist (`PyGithub`, `github3.py`, `ghapi`, `githubkit`) and training data can blend method names across them.
**How to avoid:** `githubkit` is independently confirmed on PyPI this session (`pip index versions githubkit` → `0.16.1`) and is the name already locked by the project's own `.claude/CLAUDE.md`. Do not substitute a different GitHub SDK package during implementation without re-verifying.
**Warning signs:** An import error for a method name that "looks right" but belongs to a different library's naming convention (e.g. PyGithub's `repo.get_issue(number)` vs. githubkit's `client.rest.issues.get(owner, repo, issue_number)`).

## Code Examples

### githubkit client construction (verified against README excerpt)

```python
# Source: https://github.com/yanyongyu/githubkit README [CITED]
from githubkit import GitHub

github = GitHub("<your_token_here>")
```

### Webhook signature verification (verified against official githubkit docs)

```python
# Source: https://yanyongyu.github.io/githubkit/usage/webhooks/ [CITED]
from githubkit.webhooks import verify, parse

def handle_webhook(raw_body: bytes, headers: Mapping[str, str], secret: str):
    signature = headers.get("X-Hub-Signature-256", "")
    if not verify(secret, raw_body, signature):
        raise PermissionError("invalid webhook signature")
    event = parse(headers["X-GitHub-Event"], raw_body)
    return event
```

### GitHub's own documented signature algorithm (for cross-checking `verify()`'s behavior, not for hand-rolling it)

```python
# Source: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries [CITED]
import hashlib, hmac

def verify_signature(payload_body: bytes, secret_token: str, signature_header: str) -> bool:
    hash_object = hmac.new(secret_token.encode("utf-8"), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)
```

### The one mutation path's existing shape (for extending, not replacing) — quoted verbatim

```python
# Source: src/dark_factory/persistence/mutations.py:97-123 (RoleExecutionWrite) [VERIFIED]
class RoleExecutionWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: Literal["insert", "update", "patch"]
    role: str
    worker: str
    status: str
    id: UUID | None = None  # required for mode="update"/"patch"
    worker_session_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    wip_commit_sha: str | None = None
```

The `wip_commit_sha: str | None = None` field on `RoleExecutionWrite`, and its `patch`-mode handling in `_write_role_execution` (`mutations.py:416-438`, quoted: `if spec.wip_commit_sha is not None: row.wip_commit_sha = spec.wip_commit_sha`), is the exact precedent to mirror for a *new* `HumanInteractionWrite` field (`clarification_comment_id`, `github_comment_id`) and for however `Run.published_commit_sha`/`pr_number`/`pr_url` get threaded through `apply_transition` — note that `apply_transition` currently has **no generic "set an arbitrary `runs` column" parameter** (it hard-codes `status`/`current_role`/`current_step`/lease-clear/`counter_increments`) [VERIFIED: src/dark_factory/persistence/mutations.py:253-267, the full keyword-argument list of `apply_transition`], so a new keyword parameter (e.g. `run_fields: Mapping[str, Any] | None = None`, mirroring `counter_increments`'s shape) is needed on `apply_transition` itself to write `pr_number`/`pr_url`/`published_commit_sha` — this is a genuine, required extension to the one mutation path, not an optional nicety.

### Deterministic branch name (for the GitHub-side PR-branch lookup)

```python
# Source: src/dark_factory/git/worktree.py:29-34 [VERIFIED]
def working_branch_name(run_id: UUID) -> str:
    return f"dark-factory/run-{run_id}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `PyGithub` REST-only wrapper | `githubkit` (typed, sync+async, OpenAPI-generated, Pydantic webhook models) | Project's own tech-stack decision, 2026-09 | Already locked (D-03); no migration needed since this is a greenfield GitHub integration |
| `X-GitHub-Delivery` header as dedup key | Business-level identifier (`github_comment_id`) as dedup key | This phase (D-05) | `X-GitHub-Delivery` is transport-level and does not protect against GitHub redelivering the same logical comment under a new delivery id — D-05's rationale, independently consistent with how webhook idempotency is generally recommended to be implemented |

**Deprecated/outdated:** none identified specific to this phase's stack.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `githubkit`'s REST namespace exposes `rest.issues.get(owner, repo, issue_number)`, `rest.issues.list_comments(owner, repo, issue_number)`, `rest.issues.list_labels_on_issue(owner, repo, issue_number)`, `rest.issues.create_comment(owner, repo, issue_number, body=...)`, and `rest.pulls.create(owner, repo, title=, head=, base=, body=)` following GitHub's OpenAPI operationId naming (the README confirms method names are auto-generated from GitHub's OpenAPI spec, but this session could not fetch a verbatim source confirming these exact five call shapes for the 0.16.1 API surface) | Architecture Patterns (Pattern 3), Code Examples, Recommended Project Structure | Low-to-medium: a wrong method/parameter name fails fast at first Developer-role or CI run with an `AttributeError`/`TypeError`; recommend the plan's first task run `python -c "from githubkit import GitHub; help(GitHub.rest.issues)"` / `help(GitHub.rest.pulls)` against the installed 0.16.1 as a cheap first-step verification before writing call sites |
| A2 | `githubkit`'s `rest.pulls.list(owner, repo, head=f"{owner}:{branch}", state="all")` is the correct call shape for finding an existing PR by head branch (Pattern 3's crash-safety-net check) | Architecture Patterns (Pattern 3), Common Pitfalls (Pitfall 1) | Medium: if the method/parameter shape differs, the crash-safety-net check silently fails to find an existing PR and either double-creates one or raises — must be verified against the installed version and covered by a unit test with a stubbed/faked GitHub client before relying on it |
| A3 | A minimal FastAPI (or bare starlette) webhook receiver, run as a separate process/deployable, is sufficient without needing GitHub App infrastructure (Dark Factory's own PAT via `Settings.github_token` is enough to post comments/create PRs; no GitHub App identity is required) | Architecture Patterns (Pattern 4), Standard Stack | Low: this mirrors D-04's explicit reuse of `github_token` and is consistent with the existing `push_working_branch`'s token-based auth; if the target org later requires a GitHub App, that is an unrelated future migration |
| A4 | The `issue_comment` webhook's `comment.user`/`sender` field, compared against the identity behind `Settings.github_token`, is a reliable way to detect and exclude Dark Factory's own posted comments (Pitfall 2) — exact field name (`sender.login` vs `comment.user.login`) not independently confirmed this session beyond the general payload shape found via search | Common Pitfalls (Pitfall 2) | Medium: if the self-comment filter is implemented against the wrong field, the self-comment loop (Pitfall 2) is not actually prevented — recommend a dedicated unit test simulating a webhook delivery for Dark Factory's own `clarification_comment_id` and asserting no answer is recorded |

**If this table is empty:** N/A — see rows above; every githubkit-specific method-shape claim is flagged here because this session's tooling could not reach githubkit's live API reference pages (404s on the versioned doc paths attempted) or context7 (not available in this environment), only its README/webhooks-usage prose pages and general web search.

## Open Questions

1. **Does `apply_transition` need a generic `run_fields` write parameter, or should `published_commit_sha`/`pr_number`/`pr_url` be written through a dedicated new write-spec model?**
   - What we know: `apply_transition` currently hard-codes exactly which `runs` columns it writes (`status`, `current_role`, `current_step`, lease columns, `counter_increments`) [VERIFIED: src/dark_factory/persistence/mutations.py:253-267,343-352] — there is no existing seam for an arbitrary `runs` column write.
   - What's unclear: whether the planner should add one generic `Mapping[str, Any]` parameter (fastest, mirrors `counter_increments`) or a typed `PublishFieldsWrite` model (more type-safe, matches the project's general preference for typed write-spec models like `RoleExecutionWrite`/`HumanInteractionWrite`).
   - Recommendation: a typed `PublishFieldsWrite(pr_number: int | None, pr_url: str | None, published_commit_sha: str | None)` model, following the project's established `*Write` naming and `frozen=True, extra="forbid"` shape, is more consistent with the existing style than an untyped mapping.

2. **What identifies "the run" for a given `issue_comment` webhook delivery?**
   - What we know: `Run.source_kind`/`Run.source_ref` are already persisted at creation (`create_run`, `persistence/mutations.py:213-233`); `source_ref` for a `github:` source is currently `None` for `_load_text`'s shape but is populated for `_load_spec` (the resolved file path) — the exact `source_ref` value `_load_github` should populate (e.g. `f"{owner}/{repo}#152"` or similar) is not locked by CONTEXT.md.
   - What's unclear: whether the webhook resolves a run by matching `(github_owner, github_repo, issue_number)` against `source_ref`/`normalized_task.metadata`, or by joining through `clarification_comment_id`'s parent issue via a stored issue number in `human_interactions` or `runs.normalized_task`.
   - Recommendation: populate `NormalizedTask.metadata` with `{"owner": ..., "repo": ..., "issue_number": ...}` at `_load_github` time (metadata is already a free-form `dict[str, Any]` field on `NormalizedTask` [VERIFIED: src/dark_factory/domain/task.py:25]) and have the webhook resolver query `runs` by matching those metadata fields plus `status = 'WAITING_HUMAN'` — this needs no new column, reuses an existing JSONB field, and keeps the webhook resolution query simple.

3. **Exact githubkit REST method/parameter names for 0.16.1** (see Assumptions A1/A2) — recommend resolving via `help()` against the actually-installed version as the very first implementation step, before any call-site code is written, rather than trusting this research's OpenAPI-convention inference.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `githubkit` (PyPI) | INTAKE-03, GIT-03..06 | ✓ (confirmed on PyPI, not yet installed in this repo) | 0.16.1 | none needed — `uv add` at plan time |
| Network access to `api.github.com` at runtime | Every GitHub API call this phase adds | Not verifiable from this research session (no live credential/network probe attempted) | — | Tests should use a faked/stubbed `GitHubClient` (mirroring `FakeWorker`'s precedent), never live network calls, for unit/db-tier suites; only a discretionary `integration`-marked suite (skipped absent credentials, per the project's existing `QUAL-03` pattern for worker adapters) should hit real GitHub |
| A GitHub PAT with repo + webhook-relevant scopes (`Settings.github_token`) | Issue read, comment post, PR create | Already an optional `Settings` field since Phase 1 (loaded for redaction even before use) [VERIFIED: src/dark_factory/config/settings.py:90] | — | Absence should surface as a typed error at the point of use, mirroring `anthropic_api_key`'s `MissingWorkerCredentialError` precedent — not a bare `None`-dereference crash |

**Missing dependencies with no fallback:** none — `githubkit` is a straightforward `uv add`.
**Missing dependencies with fallback:** live GitHub network access during tests — falls back to a faked client for unit/db tiers.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x [VERIFIED: pyproject.toml `dev = ["pytest>=9,<10", ...]`] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` [VERIFIED: pyproject.toml] |
| Quick run command | `uv run pytest -q -m unit` |
| Full suite command | `uv run pytest -q` (requires reachable PostgreSQL 17 for `db`-marked tests, per existing project convention) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTAKE-03 | `github:152` builds a correct `NormalizedTask` from a faked issue+comments+labels response | unit | `uv run pytest tests/unit/test_load_github.py -x` | ❌ Wave 0 |
| GIT-03 | QA PASS + Gate PASS → commit/push/PR-create/persist/COMPLETED, using a faked GitHubClient | db | `uv run pytest tests/db/test_publish_step.py -x` | ❌ Wave 0 |
| GIT-04 | Kill-after-API-call-before-commit simulation yields exactly one PR on resume | db | `uv run pytest tests/db/test_publish_idempotency.py -x` | ❌ Wave 0 |
| GIT-05 | `ROLE_NEEDS_INPUT` on a GitHub-sourced run posts exactly one comment, stays `WAITING_HUMAN` | db | `uv run pytest tests/db/test_ask_posts_comment.py -x` | ❌ Wave 0 |
| GIT-06 | A resolvable `issue_comment` webhook resumes the correct `RoleExecution`; an unresolvable one creates no run; a redelivered answer stores exactly one answer; a self-authored comment is ignored | unit + db | `uv run pytest tests/unit/test_webhook_signature.py tests/db/test_webhook_resolves_answer.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -q -m unit`
- **Per wave merge:** `uv run pytest -q` (full suite, requires real PostgreSQL 17 per existing project convention)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/support/fake_github.py` — a `FakeGitHubClient` test double mirroring `FakeWorker`'s existing precedent (scripted responses, no network), needed by every new unit/db test above
- [ ] `tests/unit/test_load_github.py` — covers INTAKE-03
- [ ] `tests/db/test_publish_step.py`, `tests/db/test_publish_idempotency.py` — cover GIT-03/GIT-04
- [ ] `tests/db/test_ask_posts_comment.py` — covers GIT-05
- [ ] `tests/unit/test_webhook_signature.py`, `tests/db/test_webhook_resolves_answer.py` — cover GIT-06
- [ ] Webhook receiver's own test harness (a `TestClient`-style in-process app test, per whichever framework is chosen) — no equivalent exists yet since this is the first non-CLI process in the codebase

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | `githubkit.GitHub(token)` using `Settings.github_token` (SecretStr, never logged — existing `known_secret_values()` redaction covers it automatically since it walks `model_fields` for `SecretStr`) |
| V3 Session Management | no | No user sessions in this phase; the webhook receiver is stateless per-request |
| V4 Access Control | yes | Webhook signature verification (`githubkit.webhooks.verify`) is the sole authorization gate on the inbound webhook route — reject before any parsing/DB access on a failed signature |
| V5 Input Validation | yes | `githubkit.webhooks.parse` (typed Pydantic v2 models) validates payload shape before any field is read; reject malformed/unexpected event types (only `issue_comment` with `action == "created"` and no `issue.pull_request` is in scope) |
| V6 Cryptography | yes | HMAC-SHA256 signature comparison — never hand-rolled (see Don't Hand-Roll); `Settings.github_webhook_secret` follows the existing `SecretStr` pattern |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Forged webhook payload (no/weak signature check) | Spoofing | `githubkit.webhooks.verify()` against the raw body, `hmac.compare_digest`-based (timing-safe), rejected before any DB read |
| Self-comment loop (Dark Factory answering its own question) | — (logic error, not a STRIDE category, but security-adjacent: an unauthenticated actor could otherwise craft this exact race) | Filter webhook events whose `comment.user`/`sender` matches Dark Factory's own token identity, per Pitfall 2 |
| Replay of a captured webhook delivery | Repudiation / Tampering | GitHub's signature does not include a timestamp/nonce by itself in the same way as e.g. Stripe's; rely on the business-level dedup (`github_comment_id` already `ANSWERED`) rather than only signature validity for replay protection — this is D-05's own stated rationale |
| Webhook secret leaking into logs/events | Information Disclosure | `Settings.github_webhook_secret: SecretStr` follows the exact existing pattern (`github_token`), automatically covered by `known_secret_values()`'s `model_fields` walk — no special-case code needed |
| Infra credential (`DATABASE_URL`, `GITHUB_TOKEN`) reaching a spawned process | Information Disclosure | Not applicable here — the webhook receiver and publish step run in-process/same-process as the orchestrator (never spawn a worker subprocess for this work), so `build_worker_env`'s allowlist discipline is not the relevant control; ordinary `Settings` access is fine |

## Sources

### Primary (HIGH confidence)
- `src/dark_factory/**` (this repository) — every `[VERIFIED: path:lines]` citation above was read directly this session.
- `.claude/CLAUDE.md` (project tech-stack doc) — `githubkit` 0.16.1 pin and its own PyPI-JSON-registry sourcing.
- `pip index versions githubkit` (run this session) — confirms `0.16.1` current.

### Secondary (MEDIUM confidence)
- https://yanyongyu.github.io/githubkit/usage/webhooks/ — `verify`/`parse` code shown verbatim above [CITED].
- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries — signature algorithm, header name, prefix format [CITED].
- https://docs.github.com/en/webhooks/webhook-events-and-payloads — `issue_comment` action values and payload shape [CITED].
- https://github.com/yanyongyu/githubkit README — client construction example [CITED].

### Tertiary (LOW confidence)
- githubkit exact REST method/parameter names for `issues.get`/`list_comments`/`create_comment`/`pulls.create`/`pulls.list` — inferred from the README's stated "auto-generated from GitHub's OpenAPI spec" convention plus general GitHub REST API parameter names; not independently fetched verbatim this session (context7 unavailable in this environment; githubkit's versioned API-reference doc paths returned 404 on the URLs attempted). Flagged in the Assumptions Log (A1/A2) with a recommended first-implementation-step verification.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `githubkit` is a locked project decision, independently version-confirmed against PyPI this session.
- Architecture: HIGH — every structural finding (no reachable `PUBLISHING`/`VERIFYING` transition, `apply_transition`'s fixed keyword surface, the terminal-role post-worker block's exact location, `_load_github`'s missing config parameter) is grounded in source code read this session, with file:line citations and verbatim quotes.
- Pitfalls: HIGH for the crash-window and self-comment-loop findings (derived directly from reading the actual mutation/transition code and the actual webhook event model); MEDIUM for the exact githubkit call shapes used to close them (see Assumptions Log).

**Research date:** 2026-09-26
**Valid until:** ~30 days for the architecture findings (stable, code-grounded); ~7-14 days for the exact `githubkit` method-name claims (recommend re-verifying against the installed version at implementation time regardless of research age).
