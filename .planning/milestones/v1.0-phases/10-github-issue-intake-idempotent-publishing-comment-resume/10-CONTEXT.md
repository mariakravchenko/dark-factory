# Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume - Context

**Gathered:** 2026-09-26
**Status:** Ready for planning

<domain>
## Phase Boundary

A GitHub issue starts a run (`dark-factory run github:152` builds a
`NormalizedTask` from title/body/comments/labels/repo metadata — the
orchestrator stays agnostic to the origin from that point). When a role
raises `ROLE_NEEDS_INPUT` on a GitHub-sourced run, Dark Factory posts the
question as a clarification comment on the issue and the run stays
`WAITING_HUMAN`. A new issue-comment webhook delivery resolves the matching
pending interaction, stores the answer idempotently, and resumes the same
`RoleExecution` — never creating a new run, never double-processing a
redelivered webhook. Once QA PASSes and the independent Quality Gate PASSes,
Dark Factory collects the final diff, commits, pushes, and opens exactly one
pull request, with every external side effect (branch, commit, PR, comment)
keyed on a persisted identifier checked before acting, so a crash between an
API call and its own row commit still yields exactly one of each.

Out of scope (belongs to other phases): cross-machine/CI resume proof and
unifying CLI/webhook/CI triggers into one entrypoint (Phase 11 — TRIG-01/04);
the observability/audit surface beyond the events this phase itself emits
(Phase 12); the quality gate and bounded feedback loops themselves (shipped
Phase 9 — this phase only publishes after they PASS).

</domain>

<decisions>
## Implementation Decisions

### Comment ingestion architecture
- **D-01:** A new, separate webhook-receiver process (per the tech-stack doc's suggested pattern) verifies the GitHub webhook signature (using a new `Settings.github_webhook_secret: SecretStr | None`), parses the `issue_comment` payload, and resolves it to a `(run_id, interaction)` pair. This is new deployable surface but matches GIT-06's literal "GitHub event handler" framing; it does not attempt cross-machine/CI trigger unification — that generalization is explicitly Phase 11's job (TRIG-01/04). — **Reversibility:** reversible — it's an additive process; Phase 11 can wrap or replace its trigger role without touching the resolution/answer logic itself.
- **D-02:** The webhook process calls the existing `submit_answer(run_id, answer, session_factory=...)` (`orchestrator/answers.py:67-150`) directly, in-process, against the same database — no new mutation path, no separate "mark claimable and wait for something else to pick it up" indirection. Same lease/idempotency guarantees CLI resume already gets. — **Reversibility:** reversible — Phase 11 generalizing triggers into one entrypoint touches only how `submit_answer` gets invoked, not its contract.

### GitHub API surface & config
- **D-03:** `githubkit` (already the pinned dependency per CLAUDE.md's tech stack) is added to `pyproject.toml` and used for issue fetch (title/body/comments/labels), comment posting, and PR creation. It is not currently a dependency — this phase adds it.
- **D-04:** `RepositoryConfig` (`config/repo_config.py`) gains `github_owner`/`github_repo` fields alongside its existing `base_branch`, as explicit repo-level config rather than derived from the checked-out git remote. `Settings` gains `github_webhook_secret: SecretStr | None = None`, mirroring the existing `github_token: SecretStr | None` optional-credential shape (Phase 5's D-16 precedent). The existing `Settings.github_token` is reused for GitHub API auth (issue read, comment post, PR create) — no new token type is introduced for Dark Factory's own GitHub identity.

### Idempotency identifiers
- **D-05:** `human_interactions` gains a `clarification_comment_id` column (the posted GitHub comment's id) and a `github_comment_id` column recording the id of the comment that answered it. Before posting a clarifying question, the publish/ask step checks `clarification_comment_id`; if already set, it skips re-posting. A duplicate webhook delivery for the same answering comment is a no-op once the interaction is already `ANSWERED` with that `github_comment_id` — this is the durable business-level dedup key (not the X-GitHub-Delivery header, which is transport-level and doesn't protect against GitHub itself redelivering the same logical comment under a new delivery id). — **Reversibility:** reversible — additive columns; no existing data model changes.
- **D-06:** `Run` gains a new `published_commit_sha` column, distinct from `RoleExecution.wip_commit_sha` (which stays WIP-recovery-specific). Before acting on the publish step, Dark Factory checks `branch exists` + `published_commit_sha set` + `pr_number set` together — matching GIT-04's literal "branch, commit SHA, PR number and comment id are all checked before acting." `Run.pr_number`/`Run.pr_url` (existing, unused since Phase 5) are the PR-side identifiers; no new columns needed there.

### Event catalog
- **D-07:** Phase 10 adds the real `PUBLISH_STARTED`, `PR_CREATED`, and `PUBLISH_FAILED` event types to `events/catalog.py` now, since it's the phase that actually performs the work — same precedent as Phase 9 claiming `QUALITY_GATE_*` itself rather than waiting for a later "observability phase." The catalog's docstring (currently at `catalog.py:32-38`, claiming these arrive in Phase 12) is corrected to attribute them to Phase 10; Phase 12 becomes a consumer of these events, not their origin. — **Reversibility:** costly — once `EventType` members exist and are emitted/persisted, renaming or moving them means a data migration for already-written `run_events` rows; get the names right in Phase 10's plan review.

### Clarification comment format
- **D-08:** Each `ROLE_NEEDS_INPUT` on a GitHub-sourced run posts a fresh issue comment (never edits a prior one) with the question text as-is, lightly prefixed for identifiability (e.g. a bold "Dark Factory needs input:" lead-in) and no run-id or other internal metadata leaked into the comment body. This is consistent with `human_interactions`' existing partial-unique-index (one `WAITING` row per run at a time — Phase 2/9 precedent) so there is never ambiguity about which comment maps to which interaction.

### PR content convention
- **D-09:** PR title = `NormalizedTask.title` (the original issue title); PR body = a short generated summary linking back to the source issue and noting it was produced by Dark Factory; target/base branch = the existing `RepoConfig.repository.base_branch` (already exists from Phase 5) — no new branch-target config. Reuses what's already there rather than introducing a separate PR-target-branch concept.

### Claude's Discretion
- Exact githubkit client wrapper shape (a thin `GitHubClient` module vs. direct githubkit calls at call sites) — left to planning, following the existing `GitClient`/`shell_execute` precedent of one thin wrapper per external system.
- Exact webhook-receiver process technology (bare `httpx`/starlette handler vs. minimal FastAPI, per the tech-stack doc's own "Stack Patterns by Variant" suggestion) — left to planning; either satisfies D-01.
- Exact `EventType` payload shapes for `PUBLISH_STARTED`/`PR_CREATED`/`PUBLISH_FAILED` (D-07) — left to planning, following existing `run_events` payload conventions (e.g. Phase 9's `QUALITY_GATE_*` shapes).
- Whether the PR body includes QA/gate verdict summaries (D-09 leaves the body "short generated summary" — planning can decide exact content as long as title/base-branch/link-back are honored).
- Exact migration/column types for `published_commit_sha`, `clarification_comment_id`, `github_comment_id`, `github_owner`, `github_repo` — left to planning, following existing Alembic revision conventions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — INTAKE-03 (line 14), GIT-03..GIT-06 (lines 111-114) — the five requirements this phase implements.
- `.planning/ROADMAP.md` §"Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume" (lines 414-431) — goal, success criteria, invariant ("every external side effect is idempotent, keyed on a persisted identifier; the webhook path takes the same lease as the CLI path").

### Task intake (already built — extend, don't rebuild)
- `src/dark_factory/domain/task.py:16-25` — `NormalizedTask`, already origin-agnostic; no changes needed.
- `src/dark_factory/input/resolver.py:23-58` — `SourceKind.GITHUB` (line 28) and the `"github:"` prefix classification (line 41) already exist.
- `src/dark_factory/input/loaders.py:96-112` — `_load_github` (lines 96-99) is the stub this phase replaces with a real githubkit-backed issue/comments/labels fetch; `_LOADERS` dict dispatch needs no structural change.
- `src/dark_factory/cli.py:160-184` — `run` command dispatch; no change needed once the loader is real.

### Human interaction / resume (generic infra — reuse, extend with GitHub-facing callers)
- `src/dark_factory/persistence/models.py:231-281` — `HumanInteraction` ORM, `uq_one_waiting_interaction_per_run` partial unique index (lines 253-259) — the idempotency pattern D-05/D-08 extend.
- `src/dark_factory/domain/interaction.py:22-27` — `InteractionStatus` enum.
- `src/dark_factory/domain/signal.py:37,43` — `Signal.ROLE_NEEDS_INPUT`.
- `src/dark_factory/orchestrator/answers.py:67-150` — `submit_answer`, the one guarded transition out of `WAITING_HUMAN`; D-02's webhook handler calls this directly.
- `src/dark_factory/cli.py:187-221` — existing `resume --answer` CLI path, the pattern the webhook handler's call into `submit_answer` mirrors.

### GitHub-facing code (nothing exists yet — build fresh)
- `src/dark_factory/git/diff.py:230-279` — `push_working_branch`, the only existing GitHub-adjacent code (git push using `settings.github_token` as a scoped `GIT_ASKPASS` credential, never as an argument/URL — T-05-21 precedent). Wired from `orchestrator/runner.py:1176-1188`. This phase's PR-creation code sits alongside this, reusing the same token.
- No webhook receiver, no PR-creation code, no `githubkit` dependency exist anywhere in `src/` today (confirmed via grep) — all net-new.

### Persisted identifiers (columns exist for PR; new columns needed for the rest)
- `src/dark_factory/persistence/models.py:100-149` — `Run.pr_number`/`Run.pr_url` (lines 133-134), already declared and unused since Phase 5; `RoleExecution.wip_commit_sha` (line 188), WIP-recovery-specific, not to be repurposed for the publish commit (D-06).
- `src/dark_factory/config/repo_config.py:64-70,89-94` — `RepositoryConfig.base_branch`, `PublishingConfig.create_pr` (already gates PR creation per its own docstring, "stored now, gates PR creation in Phase 10").

### Event catalog
- `src/dark_factory/events/catalog.py:32-38,46-75` — current `EventType` members stop at Phase 9 (`QUALITY_GATE_*`, `ROLE_BOUNCED`); docstring incorrectly attributes `PUBLISH_STARTED`/`PR_CREATED` to Phase 12 — D-07 corrects this attribution to Phase 10.

### Credential boundary
- `src/dark_factory/config/settings.py:88-97,150-167` — `Settings.github_token: SecretStr | None` (line 90), already documented as Dark Factory's own infra credential (distinct from any worker's own GitHub auth, e.g. `copilot_github_token`), already auto-redacted via `known_secret_values()`. Reused for the GitHub API client per D-04; `github_webhook_secret` is added alongside it, same shape.
- `src/dark_factory/git/client.py:30-43` — `GIT_ENV_ALLOWLIST`, the explicit-allowlist precedent D-01's webhook process and any subprocess boundaries should follow if they ever spawn anything (they are not expected to).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `submit_answer()` (`orchestrator/answers.py`) — directly reusable by the webhook handler; already handles the lease-guarded state re-check.
- `Settings.github_token` + `known_secret_values()` redaction — directly reusable for the new GitHub API client; no new credential type needed for Dark Factory's own auth.
- `Run.pr_number`/`pr_url` — already-migrated columns, first real writer is this phase.
- `HumanInteraction`'s partial unique index pattern — the idempotency template D-05 follows for the new comment-id columns.

### Established Patterns
- Narrow, purpose-built `EventType`s claimed by the phase that does the work, not deferred to a later "observability phase" (Phase 9's `QUALITY_GATE_*` precedent) — followed for D-07.
- Infrastructure credentials are explicit `SecretStr` `Settings` fields, read once by the caller and passed as plain values into config-ignorant packages — never `os.environ.copy()` (Phase 5 D-16, Phase 6 D-09) — followed for `github_webhook_secret` and the reused `github_token`.
- Persisted identifiers checked before acting, one dict-dispatch per external side effect, no special-casing — followed for D-06's three-way check (branch/commit/PR) before any publish action.

### Integration Points
- `input/loaders.py`'s `_load_github` stub is the exact landing spot for real issue/comment/label fetching — dispatch machinery around it needs zero changes.
- `orchestrator/runner.py` around the existing gate/QA transition logic (Phase 9's wiring point, ~lines 1020-1092) is where the publish step (branch/commit/push/PR) gets invoked after Quality Gate PASS.
- `git/diff.py`'s existing push-with-token pattern is the direct neighbor for the new PR-creation call.

</code_context>

<specifics>
## Specific Ideas

- Clarification comment: plain markdown, lightly prefixed (e.g. "Dark Factory needs input:"), no internal metadata (run id, etc.) leaked into the comment body.
- PR title = original issue/task title; PR body = short generated summary linking back to the source issue; target branch = existing `base_branch` config, unchanged.
- Comment dedup key = GitHub comment id (business-level), not the transport-level `X-GitHub-Delivery` header, because GitHub can redeliver the same logical comment event under a new delivery id.

</specifics>

<deferred>
## Deferred Ideas

None raised as new capabilities during this discussion — the conversation stayed within phase scope. The one open question surfaced during scouting (event-catalog phase misattribution for `PR_CREATED`/`PUBLISH_STARTED`) was resolved as D-07, not deferred.

### Reviewed Todos (not folded)
None — `.planning/todos/pending/` had no entries at discussion time.

</deferred>

---

*Phase: 10-GitHub — Issue Intake, Idempotent Publishing, Comment Resume*
*Context gathered: 2026-09-26*
