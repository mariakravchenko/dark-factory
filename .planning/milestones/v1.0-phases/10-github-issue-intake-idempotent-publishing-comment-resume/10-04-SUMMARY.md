---
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
plan: 04
subsystem: webhook
tags: [githubkit, github-api, starlette, webhook, hmac, human-in-the-loop, postgresql]

requires:
  - phase: 10-github-issue-intake-idempotent-publishing-comment-resume
    provides: "GitHubClient wrapper + FakeGitHubClient (plan 10-01); the github_comment_id/clarification_comment_id columns, PublishFieldsWrite/HumanInteractionWrite scaffolding and github_client_factory seam (plan 10-06); a real clarification_comment_id populated on a WAITING interaction (plan 10-03)"
provides:
  - "dark_factory.webhook -- the first non-CLI deployable in this codebase: a separate ASGI process (build_app()/app, run via uvicorn dark_factory.webhook.app:app) whose only mutation is submit_answer (D-02), never advance/drive"
  - "GitHubClient.authenticated_login -- the token's own login, cached per instance, used by the self-comment filter"
  - "persistence.repositories.github_pending_interaction -- the owner/repo/issue_number + WAITING_HUMAN/WAITING lookup, via SQLAlchemy 2.0 JSONB accessor operators, never source_ref string-matching"
  - "webhook.resolve.resolve_issue_comment -- the pure, total, write-free (payload, run lookup) -> ResolvedAnswer | UnresolvableComment decision, with two independent self-comment filters"
  - "webhook.app.build_app/app -- verify (githubkit.webhooks.verify, fail closed) -> parse (githubkit.webhooks.parse) -> resolve -> submit_answer, status codes mapped by retryability"
  - "orchestrator.answers.submit_answer(..., github_comment_id=...) -- D-05's durable dedup key threaded into the existing HumanInteractionWrite, no other change to the function"
  - "tests/support/webhook_events.py -- shared polyfactory-filled githubkit-typed issue_comment payload builder for the unit and db tiers"
affects: [10-05]

actuals:
  tokens: 19718
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "build_app(*, session_factory, settings_factory, authenticated_login) is a factory, not a bare module object -- app = build_app() is the production default, and every keyword is this codebase's session_factory/github_client_factory injection idiom extended to an ASGI route, so a test app never shares state (a lazily-constructed GitHubClient, a session factory) with another test's app."
    - "resolve_issue_comment orders its checks cheapest-and-most-exclusionary first (action, PR-thread, empty body, THEN the one database lookup, THEN both self-comment filters) so an obviously irrelevant delivery costs no round trip -- proved directly with a session double that raises on any attribute access."
    - "The commenter identity for the self-comment filter is read off comment.user.login (the comment's own author), not sender.login (who triggered the delivery) -- closes 10-RESEARCH.md Assumption A4 by introspecting the installed githubkit 0.16.1/githubkit-schemas 26.9.21 package's own typed model before writing the call site, exactly as plan 10-01 did for the REST surface."

key-files:
  created:
    - src/dark_factory/webhook/__init__.py
    - src/dark_factory/webhook/resolve.py
    - src/dark_factory/webhook/app.py
    - tests/unit/test_webhook_resolve.py
    - tests/unit/test_webhook_signature.py
    - tests/db/test_webhook_resolves_answer.py
    - tests/support/webhook_events.py
  modified:
    - src/dark_factory/github/client.py
    - src/dark_factory/persistence/repositories.py
    - src/dark_factory/orchestrator/answers.py
    - tests/conftest.py

key-decisions:
  - "Task 1's unit test file (tests/unit/test_webhook_resolve.py) monkeypatches github_pending_interaction at its call site inside dark_factory.webhook.resolve rather than using the db_session fixture the plan's prose names -- Task 1 declares no PostgreSQL precondition of its own, and the pytest `unit` marker's own contract is 'no database or I/O'. The lookup's own SQL correctness against real PostgreSQL is proved end-to-end (and more thoroughly, through the real receiver route) by Task 3's db-tier file, so nothing is left unproven -- only relocated to the tier that already carries a declared database precondition."
  - "tests/support/webhook_events.py (new, not in the plan's declared files_modified) is shared test infrastructure required by all three of this plan's own test files -- built once via polyfactory (an existing dev dependency) filling in githubkit's own generated pydantic models, then overriding the specific fields each test cares about, so a fixture that parses successfully is proof the real receiver can parse it too."
  - "tests/conftest.py's shared fake_settings fixture gained github_webhook_secret (additive only, no existing consumer affected) so this plan's unit and db test files sign fixture deliveries against the same fake, greppable secret every other redaction-covered credential in that fixture already uses."
  - "build_app's authenticated_login keyword bypasses lazy GitHubClient construction entirely when supplied -- the unit and db test tiers inject a stubbed callable and never construct a real client or need GITHUB_TOKEN; the production default (app = build_app()) constructs exactly one GitHubClient per process, on first use, via GitHubClient.from_settings(get_settings())."
  - "The webhook route's blocking SQLAlchemy/orchestrator.answers work is dispatched off the event loop via starlette.concurrency.run_in_threadpool, called only after signature verification and event-name filtering have already returned early for the cases that need neither -- matches 10-01-SUMMARY.md's recorded reason for pinning Starlette (exact raw-body access plus this exact threadpool pattern for DB calls)."

patterns-established:
  - "A second FakeGitHubClient/authenticated_login-stub pair, one for the intake loader's own call site and one for the webhook receiver's, is how a db test drives both halves of the GitHub round trip (a run created from an issue, then answered from that same issue) with no network call -- mirrors plan 10-03's own two-FakeGitHubClient pattern."

requirements-completed: [GIT-06]

coverage:
  - id: D1
    description: "A separate webhook-receiver process verifies every inbound delivery's signature (githubkit.webhooks.verify, over the exact raw bytes) before any parse or database session, rejecting an absent/malformed/mismatched signature or an unset secret with a fixed, non-echoing 401"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_signature.py (missing signature, mismatched signature, body-altered-after-signing, 401-body-leaks-nothing, unset-secret-refuses-every-delivery -- session_factory double raises on call for every case)"
        status: pass
      - kind: integration
        ref: "tests/db/test_webhook_resolves_answer.py::test_unsigned_and_mis_signed_deliveries_change_nothing (real PostgreSQL)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A resolvable delivery calls the unchanged submit_answer directly and in-process (D-02) -- the webhook path takes the same lease, the same expected_status guard and the same single apply_transition the CLI resume --answer path already takes"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_signature.py::test_a_resolvable_delivery_calls_submit_answer_exactly_once (recording double asserts call count/args)"
        status: pass
      - kind: integration
        ref: "tests/db/test_webhook_resolves_answer.py::test_a_resolvable_reply_resumes_the_same_attempt (real PostgreSQL, real apply_transition)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The same RoleExecution resumes (id and count unchanged, status RESUMING); no new run is ever created, including for a delivery matching no pending interaction, which writes nothing and returns a success acknowledgement"
    requirement: GIT-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_resolves_answer.py::test_a_resolvable_reply_resumes_the_same_attempt, ::test_no_new_run_is_ever_created (real PostgreSQL)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A redelivered webhook for the same logical comment stores exactly one answer, keyed on the GitHub comment id -- never the X-GitHub-Delivery transport header; a redelivery under a different X-GitHub-Delivery for the same comment id is also a no-op"
    requirement: GIT-06
    verification:
      - kind: integration
        ref: "tests/db/test_webhook_resolves_answer.py::test_redelivery_stores_exactly_one_answer (real PostgreSQL: identical redelivery, then same comment id under a different delivery header)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Dark Factory never answers its own clarification comment, on two independent filters: the inbound comment id equalling clarification_comment_id, and the commenter login equalling the token's own authenticated_login()"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_resolve.py::test_self_authored_by_comment_id_is_ignored_even_with_a_foreign_login, ::test_self_authored_by_login_is_ignored_even_with_a_foreign_comment_id"
        status: pass
      - kind: integration
        ref: "tests/db/test_webhook_resolves_answer.py::test_dark_factory_never_answers_itself (real PostgreSQL, both filters proved independently)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Only action == created is acted on; edited/deleted/pinned/unpinned and any delivery whose issue carries a pull_request field are acknowledged and ignored, writing nothing"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_resolve.py (non-created action, pull-request-thread -- both proved with a session double that raises on use)"
        status: pass
      - kind: integration
        ref: "tests/db/test_webhook_resolves_answer.py::test_ignored_action_shapes_change_nothing (real PostgreSQL)"
        status: pass
    human_judgment: false
  - id: D7
    description: "resolve_issue_comment is total: every delivery lands in exactly one of {answered, ignored-as-unresolvable, rejected-unsigned}, and the ignored/rejected outcomes write nothing; an empty comment body resolves to ignored rather than storing an empty answer"
    requirement: GIT-06
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_resolve.py::test_every_documented_input_returns_a_typed_result_never_none, empty/whitespace-body parametrized cases"
        status: pass
    human_judgment: false
  - id: D8
    description: "The receiver never advances the pipeline -- advance/drive are unreachable from the webhook package"
    verification:
      - kind: unit
        ref: "tests/unit/test_webhook_resolve.py::test_webhook_package_never_imports_advance_or_drive (AST import-closure check, not a text grep, since the package's own docstrings discuss the prohibition by name)"
        status: pass
    human_judgment: false
  - id: D9
    description: "Regression: the pause/resume suite, the structural guards, and the full unit+contract tier stay green after this plan's change"
    verification:
      - kind: integration
        ref: "tests/db/test_resume_first_advance.py, tests/db/test_pause_path_atomic.py, tests/db/test_human_interactions_schema.py, tests/db/test_webhook_resolves_answer.py -- 26 passed against real PostgreSQL (Neon)"
        status: pass
      - kind: unit
        ref: "Full unit+contract suite (770 passed, no database) plus mypy --strict and ruff check clean across the whole src tree"
        status: pass
    human_judgment: false
  - id: D10
    description: "A full, unrestricted 'uv run pytest -q' (every tier, no marker filter) is green"
    verification: []
    human_judgment: true
    rationale: "This session's PostgreSQL instance is a remote Neon database with NullPool (a fresh connection per test, no reuse), so each db-tier test costs a real network round trip -- this plan's own new db-tier file alone (6 tests, no fresh-engine-per-test) took 182.72s, and the plan's four-file named regression set (26 tests) took 610.13s. An unrestricted full-suite run was attempted and stopped after observing its rate of progress as clearly impractical within a single dispatch (consistent with 10-06-SUMMARY.md's and 10-03-SUMMARY.md's own disclosed D11-style gap, carried forward rather than repeated as a new discovery). Verified instead, all against real PostgreSQL 18.6 (Neon) unless noted: this plan's own new db-tier file (6/6), the plan's full named regression set (26/26), and the complete unit+contract tier (770/770, no database). A human with faster database access (a local PostgreSQL 17/18, or patience for a multi-hour remote run) should run the full `uv run pytest -q` before this phase is treated as fully proven against the entire existing suite -- the same open item 10-03/10-06 already carry forward."

duration: ~2h10min across two dispatches (Tasks 1-2 to a Task 3 precondition-blocked checkpoint, then continuation with a supplied throwaway Neon connection string through Task 3's completion)
completed: 2026-09-27
status: complete
---

# Phase 10 Plan 04: GitHub Webhook Receiver -- Comment Resume Summary

The first non-CLI deployable in this codebase: a separate Starlette ASGI process that verifies every inbound GitHub `issue_comment` delivery's HMAC signature over the exact raw bytes before it parses or reads anything, resolves whether the comment answers a run's pending question (never on issue number alone, never a comment Dark Factory posted itself), and -- when it does -- calls the existing `submit_answer` in-process, so the webhook path takes the identical lease and `apply_transition` the CLI's `resume --answer` already takes.

## Performance

- **Duration:** ~2h10min total across two dispatches (Tasks 1-2 fully implemented, tested and committed in the first dispatch, reaching Task 3's declared PostgreSQL-reachability precondition and stopping at a `checkpoint:human-verify`; the continuation dispatch received a throwaway Neon connection string, verified `alembic current` reported `0006_github_publishing_columns (head)`, then completed Task 3 and this plan's close-out)
- **Started:** 2026-09-27 (session start)
- **Completed:** 2026-09-27
- **Tasks:** 3/3
- **Files modified:** 11 (7 created, 4 modified)

## Accomplishments

- `GitHubClient.authenticated_login` (`src/dark_factory/github/client.py`): the configured token's own login, cached per instance (never a module-level cache), wrapping SDK failures in `GitHubApiError` exactly like the wrapper's four existing methods.
- `persistence.repositories.github_pending_interaction` (new): the run-and-interaction lookup keyed on `owner`/`repo`/`issue_number` together (never issue number alone) plus `WAITING_HUMAN`/`WAITING`, via SQLAlchemy 2.0's JSONB accessor operators (`Run.normalized_task["metadata"]["owner"].as_string()`, compiling to Postgres's `->>`) rather than any `source_ref` string-matching.
- `dark_factory.webhook` (new package): `webhook/__init__.py`'s typed error surface and the package's two hard boundaries (separate deployable; single mutation is `submit_answer`); `webhook/resolve.py`'s `resolve_issue_comment` -- a pure, total, write-free decision with `IgnoreReason`, `ResolvedAnswer`/`UnresolvableComment`, and two independent self-comment filters; `webhook/app.py`'s `build_app()`/`app` -- the one POST route (verify -> parse -> resolve -> act-or-acknowledge -> map outcome to a status code by retryability).
- `orchestrator.answers.submit_answer` gained one keyword-only `github_comment_id: int | None = None`, threaded straight into the existing `HumanInteractionWrite` -- nothing else about the function changed; the webhook path is a caller of this function, not a second mutation path (D-02), and existing callers (the CLI's `resume --answer`) are unaffected.
- 25 new unit tests (`tests/unit/test_webhook_resolve.py`, `tests/unit/test_webhook_signature.py`) covering every documented branch of the resolution decision and the receiver route's own sequencing, and 6 new db-tier tests (`tests/db/test_webhook_resolves_answer.py`) proving the whole path end to end against real PostgreSQL.
- `tests/support/webhook_events.py` (new): a shared `githubkit`-typed `issue_comment` payload builder (polyfactory-filled, never a hand-rolled dict) used by all three of this plan's own test files.

## Task Commits

1. **Task 1: Which comment answers which run -- the resolution decision, as a pure function** (auto, tdd) -- `9c7cce2` (test, RED -- verified by temporarily removing `dark_factory.webhook.resolve`/`GitHubPendingInteraction` and confirming `ModuleNotFoundError`), `81b39d1` (feat, GREEN)
2. **Task 2: The receiver -- verify first, then resolve, then submit_answer and stop** (auto, tdd) -- `d0a1908` (test, RED -- verified by temporarily removing `dark_factory.webhook.app` and `submit_answer`'s new keyword, confirming `ModuleNotFoundError`), `0d9ee71` (feat, GREEN)
3. **Task 3: Prove it against real runs -- same RoleExecution, no new run, one answer** (auto) -- `6920865` (test, against real PostgreSQL)

**Interim checkpoint (between the two dispatches):** Task 3's db-tier precondition (no reachable PostgreSQL 17 in the first dispatch's environment -- no Docker, no local `initdb`, `DARK_FACTORY_TEST_DATABASE_URL` unset) was genuinely unmet; execution paused at a `checkpoint:human-verify` after Tasks 1-2 completed and committed, per this project's precondition-gate discipline. A human then supplied a throwaway Neon PostgreSQL connection string for this continuation dispatch only; it was never written to any file, committed, or echoed in this document.

**Plan metadata:** commit hash recorded after this file is written (see the final `docs(10-04)` commit).

## Files Created/Modified

- `src/dark_factory/webhook/__init__.py` -- `WebhookError`, `InvalidSignature`, the package's two hard boundaries
- `src/dark_factory/webhook/resolve.py` -- `resolve_issue_comment`, `ResolvedAnswer`, `UnresolvableComment`, `IgnoreReason`
- `src/dark_factory/webhook/app.py` -- `build_app`, `app` (the one POST route)
- `src/dark_factory/github/client.py` -- `GitHubClient.authenticated_login`
- `src/dark_factory/persistence/repositories.py` -- `github_pending_interaction`, `GitHubPendingInteraction`
- `src/dark_factory/orchestrator/answers.py` -- `submit_answer(..., github_comment_id=...)`
- `tests/unit/test_webhook_resolve.py` (new) -- 15 unit tests over the resolution decision
- `tests/unit/test_webhook_signature.py` (new) -- 13 unit tests over the receiver route
- `tests/db/test_webhook_resolves_answer.py` (new) -- 6 db-tier tests against real PostgreSQL
- `tests/support/webhook_events.py` (new) -- shared `githubkit`-typed payload builder
- `tests/conftest.py` -- `fake_settings` gained `github_webhook_secret`

## Decisions Made

See `key-decisions` in frontmatter: Task 1's unit-tier lookup monkeypatch (keeping it DB-free per its own precondition and the `unit` marker's contract); `tests/support/webhook_events.py` as shared, undeclared-but-necessary test infrastructure; `tests/conftest.py`'s additive `github_webhook_secret`; `build_app`'s `authenticated_login` bypass seam; dispatching the route's blocking work via `run_in_threadpool`.

## Deviations from Plan

None beyond the two disclosed, documented adaptations already captured as `key-decisions` above (Task 1's DB-free lookup test and the new `webhook_events.py`/`conftest.py` supporting files) -- both are additive, non-behavioral, and do not change what the plan's `must_haves`/`acceptance_criteria` required. No Rule 1/2/3 auto-fixes were needed; the plan's own instructions (including the confirmed `githubkit` 0.16.1 webhook model field names, resolved by introspecting the installed package before writing any call site, per the plan's own Task 1 instruction) matched the installed package exactly.

## Issues Encountered

**Task 3's db-tier precondition was genuinely unmet in the first dispatch** -- no PostgreSQL reachable (no Docker, no local `initdb` 17, `DARK_FACTORY_TEST_DATABASE_URL` unset), verified read-only via `docker info`, `which initdb`, and the environment variable, matching the identical situation plans 10-01/10-02/10-03/10-06 each hit earlier in this same phase. Execution halted at a `checkpoint:human-verify` after Tasks 1-2's four commits landed. A human then supplied a throwaway Neon PostgreSQL connection string; `alembic current` was verified to report `0006_github_publishing_columns (head)` before any test ran, per the coordinator's explicit instruction rather than assuming migration state.

**The full, unrestricted `uv run pytest -q` was not run to completion** -- see coverage item D10's rationale. Each db-tier test's round trip to this session's remote Neon instance costs tens of seconds (`NullPool`, no connection reuse), and an unrestricted full-suite run was observed making impractically slow progress and stopped rather than run for hours. Prioritized instead: this plan's own new db-tier file (6/6), the plan's own named regression set (26/26, all four files together), and the full unit+contract tier (770/770). This is the same open item 10-03-SUMMARY.md and 10-06-SUMMARY.md already carry forward, not a new gap this plan introduces.

## User Setup Required

**`GITHUB_WEBHOOK_SECRET` is not yet configured in this environment**, and neither is `GITHUB_TOKEN` (carried forward from plan 10-01's disclosed gap). This plan's entire test surface -- unit and db tiers alike -- runs against a fake, greppable webhook secret and a stubbed `authenticated_login` callable, by design, so neither blocked any task. Before this receiver is trusted against a real repository:

1. Set `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`, and `GITHUB_WEBHOOK_SECRET` in `.env` or the environment.
2. Run `uv sync --extra webhook`, then start the receiver: `uv run uvicorn dark_factory.webhook.app:app --host 0.0.0.0 --port 8000`.
3. In the target repository, create a webhook (GitHub -> repository -> Settings -> Webhooks -> Add webhook): content type `application/json`, the same secret as `GITHUB_WEBHOOK_SECRET`, only the "Issue comments" event subscribed, Payload URL pointing at this process's reachable `/webhooks/github` route.
4. Post a real reply on an issue with a run in `WAITING_HUMAN` and confirm (via `dark-factory status <run-id>`) that it resumed.

This is tracked as coverage item D10's sibling live-smoke gap, consistent with every earlier plan in this phase (10-01/10-03/10-06) disclosing the same class of gap for their own GitHub-network-dependent surface.

## Next Phase Readiness

GIT-06 is closed: a GitHub-sourced run can now both ask (`clarification_comment_id`, plan 10-03) and be answered (`github_comment_id`, this plan) entirely through GitHub, with the same `RoleExecution` resuming and no second mutation path. Plan 10-05 (mentioned throughout this plan's own docstrings as the owner of the mechanical `advance`/`drive` import-closure guard for the whole `webhook` package) can build directly on `dark_factory.webhook`'s existing structure with no changes needed here. The one open item is the same D10/D11-style full-suite gap 10-03/10-06 already carry (a full, unrestricted `pytest -q` against a faster PostgreSQL instance) -- recommended before shipping, not before continuing to the next plan.

No blockers for plan 10-05.

---
*Phase: 10-github-issue-intake-idempotent-publishing-comment-resume*
*Completed: 2026-09-27*

## Self-Check: PASSED

All 11 claimed created/modified files verified present on disk; all five claimed commit hashes (`9c7cce2`, `81b39d1`, `d0a1908`, `0d9ee71`, `6920865`) verified present in `git log`.
