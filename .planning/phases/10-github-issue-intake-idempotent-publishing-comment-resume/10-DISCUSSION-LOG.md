# Phase 10: GitHub — Issue Intake, Idempotent Publishing, Comment Resume - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-26
**Phase:** 10-GitHub — Issue Intake, Idempotent Publishing, Comment Resume
**Areas discussed:** Comment ingestion mechanism, PR_CREATED event placement, Idempotency identifiers, Clarification comment & PR content, GitHub config

---

## Comment ingestion mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Webhook receiver process | Separate process verifies signature, resolves run/interaction, triggers resume | ✓ |
| Polling on resume | `dark-factory resume` fetches recent comments via GitHub API | |
| Something else | Hybrid or different shape | |

**User's choice:** Webhook receiver process.
**Notes:** Real-time and matches GIT-06's literal "GitHub event handler" framing over polling.

## Webhook → resume mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Call submit_answer() directly | Webhook process calls the same submit_answer used by CLI resume, same DB, same lease guarantees | ✓ |
| Just persist the answer, defer advancing | Webhook only writes the answer; something else advances the run later | |

**User's choice:** Call submit_answer() directly.
**Notes:** Zero new mutation path; cross-machine/trigger unification stays Phase 11's job.

---

## PR_CREATED event placement

| Option | Description | Selected |
|--------|-------------|----------|
| Add the real events now, fix the docstring | Phase 10 adds PUBLISH_STARTED/PR_CREATED now since it does the actual work; catalog docstring's Phase 12 attribution corrected | ✓ |
| Something else | Discuss why roadmap deferred these, or an alternative name/shape | |

**User's choice:** Add the real events now, fix the docstring.
**Notes:** Mirrors Phase 9's own precedent of claiming QUALITY_GATE_* itself rather than deferring to a later "observability phase."

---

## Idempotency identifiers — comment dedup key

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub comment id | Persist the answering comment's own id; dedup once ANSWERED with that id | ✓ |
| GitHub delivery id | Persist X-GitHub-Delivery header instead/also | |
| Both | Delivery id for transport-level early-exit, comment id as durable business key | |

**User's choice:** GitHub comment id.
**Notes:** Survives GitHub redelivering the same logical comment under a different delivery id.

## Idempotency identifiers — published commit SHA

| Option | Description | Selected |
|--------|-------------|----------|
| New Run.published_commit_sha column | Dedicated column alongside pr_number/pr_url; all three checked together before acting | ✓ |
| Reuse/repurpose wip_commit_sha | Avoid a new column by overloading the existing WIP-specific field | |

**User's choice:** New Run.published_commit_sha column.
**Notes:** Keeps wip_commit_sha's WIP-recovery-only meaning uncontaminated.

## Idempotency identifiers — clarification comment id

| Option | Description | Selected |
|--------|-------------|----------|
| Persist clarification_comment_id on human_interactions | Check before posting; skip if already posted | ✓ |
| Rely on WAITING_HUMAN state alone | No new column; state alone implies a comment was already posted | |

**User's choice:** Persist clarification_comment_id on human_interactions.
**Notes:** Matches GIT-04's literal list of identifiers checked before acting; protects a crash between "comment posted" and "row committed."

---

## Clarification comment & PR content — question format

| Option | Description | Selected |
|--------|-------------|----------|
| Plain markdown, one comment per question | Fresh comment each time, lightly prefixed, no internal metadata leaked | ✓ |
| Something else | Different format, run-id inclusion, editable comment, or structured template | |

**User's choice:** Plain markdown, one comment per question.

## Clarification comment & PR content — PR convention

| Option | Description | Selected |
|--------|-------------|----------|
| Task title as PR title, generated summary body, base_branch as target | Reuses existing base_branch config, no new PR-target concept | ✓ |
| Something else | Exact title/body template, draft-PR behavior, auto-labeling | |

**User's choice:** Task title as PR title, generated summary body, base_branch as target.

---

## GitHub config

| Option | Description | Selected |
|--------|-------------|----------|
| New RepositoryConfig fields + Settings.github_webhook_secret | github_owner/github_repo added to RepositoryConfig; webhook secret as new SecretStr Settings field; reuses existing github_token for API auth | ✓ |
| Derive owner/repo from git remote instead | Parse origin's remote URL at runtime | |

**User's choice:** New RepositoryConfig fields + Settings.github_webhook_secret.
**Notes:** Explicit, auditable config over coupling to whatever remote happens to be checked out.

---

## Claude's Discretion

- Exact githubkit client wrapper shape (thin `GitHubClient` module vs. direct calls at call sites).
- Exact webhook-receiver process technology (bare httpx/starlette vs. minimal FastAPI).
- Exact `EventType` payload shapes for `PUBLISH_STARTED`/`PR_CREATED`/`PUBLISH_FAILED`.
- Exact PR body content beyond "short generated summary" (whether QA/gate verdict summaries are included).
- Exact migration/column types for the five new columns (`published_commit_sha`, `clarification_comment_id`, `github_comment_id`, `github_owner`, `github_repo`).

## Deferred Ideas

None raised as new capabilities — discussion stayed within phase scope. The event-catalog phase-misattribution question surfaced during codebase scouting was resolved as a decision (D-07 in CONTEXT.md), not deferred.
