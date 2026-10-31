---
phase: quick-261031-jmw
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [GIT-06, TRIG-01]

files_modified:
  - src/dark_factory/webhook/__init__.py
  - src/dark_factory/webhook/app.py
  - src/dark_factory/webhook/resolve.py
  - src/dark_factory/config/settings.py
  - src/dark_factory/github/client.py
  - src/dark_factory/orchestrator/answers.py
  - src/dark_factory/persistence/repositories.py
  - tests/unit/test_webhook_import_needs_no_database.py
  - tests/unit/test_webhook_process_boundary.py
  - tests/unit/test_webhook_signature.py
  - tests/unit/test_webhook_resolve.py
  - tests/unit/test_dispatch_token_never_reaches_a_worker.py
  - tests/unit/test_github_ownership_boundary.py
  - tests/unit/test_trigger_carries_no_lifecycle_logic.py
  - tests/unit/test_unit_tier_needs_no_database.py
  - tests/unit/test_qual01_ci_coverage.py
  - tests/unit/test_settings.py
  - tests/unit/test_resume_workflow_reference_doc.py
  - tests/support/webhook_events.py
  - tests/support/fake_github.py
  - tests/conftest.py
  - tests/db/test_webhook_dispatches_resume.py
  - tests/db/test_webhook_resolves_answer.py
  - tests/db/test_clarification_comment_is_redacted.py
  - tests/db/test_run_report.py
  - tests/db/test_artifacts_show_reads_committed_content.py
  - pyproject.toml
  - uv.lock
  - .env.example
  - README.md
  - docs/ARCHITECTURE.md
  - docs/DEVELOPMENT.md
  - docs/GETTING-STARTED.md
  - docs/CONFIGURATION.md
  - scripts/scaffold_target_repo.py

estimate:
  tokens: 150000
  raw_tokens: 75000
  tasks: 7
  confidence: low

must_haves:
  truths:
    - "`src/dark_factory/webhook/` does not exist and no module under `src/` or `tests/` imports it."
    - "`Settings` declares neither `github_webhook_secret` nor `dispatch_github_token`; `Settings()` still constructs from a `.env` that happens to still name them (extra=\"ignore\")."
    - "`GitHubClient` exposes no `dispatch_workflow` and no `for_dispatch`; `from_settings`, `authenticated_login`, `create_comment`, `create_pull_request` and `find_pull_request_for_branch` are untouched."
    - "`dark-factory resume <id> --answer \"...\"` still records an answer and drives the run — the CLI path and `submit_answer`'s guarded WAITING_HUMAN transition are behaviourally unchanged."
    - "`persistence/repositories.py` exposes neither `github_pending_interaction` nor `GitHubPendingInteraction` (D-01), while `pending_question` and `load_run_state` are untouched."
    - "`submit_answer` still declares `github_comment_id: int | None = None` and still threads it into `HumanInteractionWrite` (D-02), so the durable `human_interactions.github_comment_id` column stays writable."
    - "The G-11-1 package-wide `no DATABASE_URL -> every dark_factory module still imports` sweep still runs and still passes (it survives the removal under a non-webhook name)."
    - "README's sentinel-bracketed `resume.yml` reference block and `scripts/scaffold_target_repo.py`'s `RESUME_WORKFLOW_TEMPLATE` both declare an optional `answer` input, so `gh workflow run resume.yml -f run_id=<id> -f answer=<text>` works against a scaffolded repository."
    - "README, docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, docs/GETTING-STARTED.md, docs/CONFIGURATION.md and .env.example describe exactly one resume path: a human replies on the issue, then a human (or any external script) dispatches resume.yml by hand."
    - "`uv sync --all-extras --dev --frozen` succeeds, so `uv.lock` agrees with the `pyproject.toml` that no longer declares a `webhook` extra."
    - "The two-mode redaction proof in tests/db/test_clarification_comment_is_redacted.py still distinguishes known-value substitution from pattern-shape matching, keyed on a credential field that still exists."
  artifacts:
    - tests/unit/test_package_import_needs_no_database.py
    - uv.lock
  key_links:
    - "tests/unit/test_resume_workflow_reference_doc.py <-> README.md's sentinel block: the doc guard must still extract and assert a block that now carries an `answer` input."
    - "tests/conftest.py's `fake_settings` <-> tests/db/test_clarification_comment_is_redacted.py's `_CONFIGURED_*_SECRET` literal: the module's own sanity assertion pins that equality and must keep pinning it."
    - "pyproject.toml optional-dependencies <-> uv.lock <-> ci.yml's `uv sync --all-extras --dev --frozen`: dropping the extra without relocking makes CI fail at the install step."
    - "tests/unit/test_dispatch_token_never_reaches_a_worker.py's two-module allowlist <-> the deletion of webhook/app.py: the guard asserts set equality and fails, not skips, the moment one named reader disappears."
---

<objective>
Remove the webhook receiver subsystem from Dark Factory entirely. The project will not
run a receiver process; the manual `gh workflow run resume.yml -f run_id=<id> -f
answer=<text>` dispatch (proven live against a real `app-int` run) becomes the only
documented cross-machine resume path.

Purpose: delete a whole deployable surface — an ASGI app, an HMAC verification path, two
infrastructure credentials, a `workflow_dispatch` API call and an optional dependency
extra — that nothing will ever run, so no future reader has to reason about it and no
deployer has to provision credentials for it.

Output: `src/dark_factory/webhook/` gone; two `Settings` credential fields gone;
`GitHubClient.dispatch_workflow`/`for_dispatch` gone; the `webhook` optional extra gone
and `uv.lock` relocked; the `answer` input *added* to both shipped `resume.yml`
templates so the surviving manual flow actually works; README, four `docs/` files,
`.env.example` and the scaffold script describing one resume path instead of two.

Scope boundaries, honored throughout:
- `human_interactions` / `submit_answer` / `dark-factory resume --answer` are the
  *answer-submission capability* and are preserved. Only the webhook *delivery*
  mechanism (receiver + auto-dispatch) is removed.
- Nothing about `app-int` is touched, and the separate not-yet-started
  `GITHUB_TOKEN`-rename task is left alone (see Finding 8).
- `.planning/` is a historical record: archived milestone artifacts (including
  `v1.0-REQUIREMENTS.md`, which records GIT-06 as Complete) are NOT rewritten.
- No database migration is involved. Verified: `migrations/` contains zero webhook or
  dispatch references, and `human_interactions.github_comment_id` /
  `clarification_comment_id` are columns this removal does not touch.
</objective>

<investigation_findings>
Read this section before Task 1. Eight findings materially change the task description's
own picture of the work. Each was established by reading source, not inferred.

**Finding 1 — `tests/unit/test_webhook_import_needs_no_database.py` is mostly NOT about
the webhook.** The task description lists it for deletion. Its four tests are:

| Test | Scope |
|---|---|
| `test_every_dark_factory_module_imports_with_no_database_configured` | package-wide `pkgutil.walk_packages` sweep over all of `dark_factory` |
| `test_g11_1_modules_collect_with_no_database_configured` | pytest collect-only under a sanitized child env |
| `test_webhook_app_module_exposes_only_the_build_app_factory` | genuinely webhook-specific |
| `test_the_sweep_harness_detects_a_module_that_constructs_settings_at_import_time` | the non-vacuity control for test 1 |

Deleting the module destroys the G-11-1 regression guard (STATE.md, plan 11-06) for the
entire package, for no reason other than a misleading filename. Task 4 therefore
*renames and narrows* it instead of deleting it. Flagged rather than silently done
either way.

**Finding 2 — `tests/unit/test_dispatch_token_never_reaches_a_worker.py` (141 lines, 4
tests) is missing from the task description's list and will FAIL, not go stale.** Its
`test_exactly_the_named_modules_read_dispatch_github_token` asserts *set equality*
against a two-entry allowlist (`github/client.py`, `webhook/app.py`). Deleting the
webhook package alone breaks it. The whole module exists only for
`dispatch_github_token`, so it is deleted in Task 1.

**Finding 3 — `GitHubClient.for_dispatch` must also go.** The task description names only
`dispatch_workflow`. `for_dispatch` (client.py:171) reads
`settings.dispatch_github_token`, so removing the `Settings` field leaves it
unconstructible. Its only production caller was `webhook/app.py`.
`MissingGitHubCredentialError` stays — `from_settings` still raises it.

**Finding 4 — `authenticated_login()` is NOT dead and must be kept.**
`orchestrator/runner.py:264` calls it for the clarification-comment crash-resume dedup
check. Only its docstring (client.py:284, which cites `dark_factory.webhook.resolve` as
the consumer) needs rewording.

**Finding 5 — three non-webhook test modules construct `Settings(github_webhook_secret=...)`.**
`tests/conftest.py`'s shared `fake_settings` fixture (line 461),
`tests/db/test_run_report.py` (233) and
`tests/db/test_artifacts_show_reads_committed_content.py` (167). None appear in the task
description. `Settings.model_config` sets `extra="ignore"`, so a leftover kwarg is
silently dropped rather than raising — which makes the *downstream* failure the only
signal. That downstream failure is Finding 6.

**Finding 6 — `tests/db/test_clarification_comment_is_redacted.py` uses
`github_webhook_secret` as the subject of its known-value-redaction proof.** The module
deliberately plants two literals to exercise `redact()`'s two independent modes: a
`whsec_`-prefixed value that matches *no* `_PATTERNS` entry (so only known-value
substitution can catch it) and a `ghp_`-shaped value configured in no field at all (so
only the pattern table can catch it). Removing the field makes the first literal
unredactable and the test fails for a real reason. The replacement credential must
(a) be a surviving `SecretStr | None` field on `Settings` and (b) match none of
`events/redaction.py`'s `_PATTERNS` — which rules out `github_token` and
`copilot_github_token` (both `gh*_`/`github_pat_`-shaped) and `database_url*` (the
postgres-URL pattern). `anthropic_api_key` with an `sk-ant-`-prefixed fake value
satisfies both. The module's own line-235 sanity assertion pins the literal to the
fixture and must keep pinning it.

**Finding 7 — the `answer` workflow input DOES NOT EXIST in this repository.** The task
description says it "was added in a prior quick task, 261031-? — grep for it". It was
not: neither README's sentinel block nor
`scripts/scaffold_target_repo.py`'s `RESUME_WORKFLOW_TEMPLATE` declares it, and
STATE.md's nine-row quick-task table records no such task. The `answer` input exists
only in `/Users/maryiakrauchanka/portfolio/app-int/.github/workflows/resume.yml`, which
was hand-edited in that repository. **Consequence: documenting `gh workflow run
resume.yml -f run_id=<id> -f answer=<text>` without adding the input would ship a
documented command that cannot work.** Task 5 adds it to both templates, modelled on the
proven-live app-int file.

**Finding 8 — the proven-live app-int resume.yml also sets `GITHUB_TOKEN: ${{
secrets.DISPATCH_GITHUB_TOKEN }}`**, because the reserved Actions auto-token cannot call
`GET /user` and `authenticated_login()` needs a real PAT. That is the separate,
not-yet-started `GITHUB_TOKEN`-rename task and is explicitly **out of scope** here. This
plan removes `DISPATCH_GITHUB_TOKEN` as a *Dark Factory `Settings` field* and as
*documented receiver credential*; it says nothing about what a deployer names their
Actions secret. Do not "fix" README's `GITHUB_TOKEN` guidance in this task.

**Also confirmed safe (no action needed):**
- `migrations/` — zero webhook/dispatch references. No schema dependency.
- `tests/unit/test_qual01_ci_coverage.py` — its `_QUAL01_SCENARIOS` map deliberately
  excludes `test_webhook_dispatches_resume.py`. Comment-only update.
- `tests/unit/test_unit_tier_needs_no_database.py` — references
  `test_webhook_import_needs_no_database.py` only in *prose*, never by import
  ("reused here as an idiom, not imported"). Prose-only update.
- `tests/support/webhook_events.py` — imported only by the four deleted webhook test
  modules.
- `src/dark_factory/__init__.py` — exports only `__version__`. No webhook re-export.
- `.github/workflows/ci.yml` — uses `uv sync --all-extras`, so dropping an extra needs
  no workflow edit. But `--frozen` makes relocking mandatory (Task 4).
</investigation_findings>

<execution_context>
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/workflows/execute-plan.md
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

@src/dark_factory/config/settings.py
@src/dark_factory/github/client.py
@tests/unit/test_resume_workflow_reference_doc.py
@/Users/maryiakrauchanka/portfolio/app-int/.github/workflows/resume.yml
</context>

<global_rules>
1. **No tombstones.** The removal must be silent in the tree. Do not leave a comment,
   docstring line, changelog entry or doc sentence in `src/`, `tests/`, `docs/`,
   `scripts/`, `README.md`, `.env.example` or `pyproject.toml` that names the removed
   receiver, its credentials or its auto-dispatch — not even to say they were removed.
   The record of this removal lives in this PLAN.md and its SUMMARY, which live under
   `.planning/` and are outside every gate below. A tombstone comment is the single most
   likely way to fail Task 7's sweep.
2. **Never `os.environ.copy()`**, never `shell=True`, never widen a credential's reach —
   CLAUDE.md's standing constraints apply to every edit here.
3. **Reword, don't delete, a docstring that explains surviving behaviour.** Several
   docstrings cite the receiver while documenting something that stays (Findings 4, and
   the `github_comment_id` paragraph D-02 keeps). Rewrite the sentence; do not
   drop the paragraph.
4. **Do not touch `.planning/`** other than the SUMMARY this plan produces and STATE.md
   bookkeeping.
5. **Measured pre-work baseline — do not misread it as a regression.** Captured on the
   unmodified tree before planning:
   - `uv run ruff check .` -> **All checks passed.** Any `ruff check` failure during
     execution is genuinely caused by this task.
   - `uv run mypy src/dark_factory` -> **2 pre-existing errors**, both
     `import-not-found` in `src/dark_factory/tools/mcp_transport.py` (`mcp.server`,
     `mcp.server.mcpserver.exceptions`), because the optional `mcp` extra is not
     installed in this environment. This is the acknowledged STATE.md deferral
     ("12-02 mcp_transport.py mypy import-not-found (optional extra not installed)").
     Task 1's precondition resolves it by installing the extra; if those two errors
     reappear mid-execution, the cause is a missing `mcp` install, not this task — do not
     "fix" `mcp_transport.py` and do not add a `type: ignore` to it.
   - `uv run ruff format --check .` -> pre-existing drift in ~19 files untouched by this
     task (STATE.md deferral, carried since 11-10). Report, never reformat.
   Every `mypy`/`ruff` gate below means "zero errors *beyond* this baseline".
</global_rules>

<decisions_resolved>
Task 1's deletion leaves three pieces of public surface with zero remaining production
callers, plus one shipped-reference shape question. All three were raised as a blocking
decision and answered by the developer as **Q1=A, Q2=A, Q3=A** — every recommended
option. They are recorded here so no task pauses; the tasks below implement them
directly.

**D-01 (Q1=A) — Remove `github_pending_interaction()` and `GitHubPendingInteraction`**
from `src/dark_factory/persistence/repositories.py`, with their two `__all__` entries.
Verified zero remaining callers anywhere in `src/` or `tests/` after Task 1;
`webhook/resolve.py` was the only one. Rationale: this repository enforces a
one-mutation-path / no-dead-surface discipline (AST guards in
`test_single_mutation_path.py`, `test_no_tree_walk.py`), and a query whose only
documented purpose was "what a webhook delivery resolves against" is not a
general-purpose read. `pending_question()` and `load_run_state()` already cover every
surviving caller. Implemented by Task 2.

**D-02 (Q2=A) — Keep `submit_answer(..., github_comment_id=None)`, reword its docstring.**
`webhook/app.py` was the only caller that ever passed it; the CLI's `resume --answer`
omits it. The `human_interactions.github_comment_id` column, its Alembic revision,
`HumanInteractionWrite.github_comment_id` and `mutations.py`'s writer all stay regardless
— they are proven by `tests/db/test_github_publishing_columns_schema.py` and
`tests/unit/test_mutations.py`, neither of which touches `submit_answer`. Rationale: the
column exists and is durable, the parameter is the only way to populate it, and removing
it would make the column unwritable by any future answer-submission entry point while the
schema still carries it. Implemented by Task 2.

**D-03 (Q3=A) — Mirror the proven-live `app-int` resume-step shape** (step `env:`
bindings for `RUN_ID`/`RUN_ANSWER` plus a shell branch inside `run:`) rather than
interpolating `${{ inputs.* }}` directly into the command text, and widen
`test_the_reference_workflow_resumes_exactly_once` to accept the run id reaching the
command either directly in `run:` or through a step-`env` binding of `inputs.run_id`.
Rationale: it ships the artifact that was actually proven to work against a real run, and
env indirection is the standard hardening against expression injection from a
`workflow_dispatch` input (T-jmw-04). The shell `if` is invisible to
`test_the_reference_workflow_carries_no_run_state_branch`, which inspects YAML `if:` keys
only, so that guard is unaffected. Implemented by Task 5.
</decisions_resolved>

<tasks>

<task type="tracer">
  <name>Task 1: Delete the subsystem and its eight test modules end-to-end, unit tier green</name>
  <files>
src/dark_factory/webhook/__init__.py,
src/dark_factory/webhook/app.py,
src/dark_factory/webhook/resolve.py,
tests/unit/test_webhook_process_boundary.py,
tests/unit/test_webhook_signature.py,
tests/unit/test_webhook_resolve.py,
tests/unit/test_dispatch_token_never_reaches_a_worker.py,
tests/db/test_webhook_dispatches_resume.py,
tests/db/test_webhook_resolves_answer.py,
tests/support/webhook_events.py,
tests/unit/test_github_ownership_boundary.py,
tests/unit/test_trigger_carries_no_lifecycle_logic.py
  </files>
  <read_first>
tests/unit/test_github_ownership_boundary.py,
tests/unit/test_trigger_carries_no_lifecycle_logic.py
  </read_first>
  <precondition>`uv sync --all-extras --dev` has been run in this working tree so the optional `mcp` extra is importable and `uv run mypy src/dark_factory` reports zero errors — otherwise the two `mcp_transport.py` `import-not-found` errors recorded in global rule 5 will make every later `mypy` gate fail for a reason unrelated to this task. Assert this before deleting anything; halt and report if `mypy` is not clean on the unmodified tree.</precondition>
  <action>
This is the thinnest slice that touches every layer the removal affects (package source,
unit tier, db tier, shared test support, structural guards) and must end with a green
unit tier — that is what proves no hidden coupling survives.

Delete outright, including `src/dark_factory/webhook/__pycache__/`:
- the whole `src/dark_factory/webhook/` directory (`__init__.py`, `app.py`, `resolve.py`)
- `tests/unit/test_webhook_process_boundary.py` (all 10 tests are webhook-boundary tests;
  its `test_core_closure_never_imports_starlette_or_uvicorn` becomes meaningless once the
  extra is gone in Task 4)
- `tests/unit/test_webhook_signature.py`, `tests/unit/test_webhook_resolve.py`
- `tests/db/test_webhook_dispatches_resume.py`, `tests/db/test_webhook_resolves_answer.py`
- `tests/support/webhook_events.py` (consumed only by the four modules above)
- `tests/unit/test_dispatch_token_never_reaches_a_worker.py` — per Finding 2 this is a
  hard FAIL after the deletion, not a stale pass, and the module exists for no other
  purpose.

Do NOT delete `tests/unit/test_webhook_import_needs_no_database.py` in this task — Task 4
renames and narrows it per Finding 1.

Then repair the two structural guards that go stale (both would otherwise keep passing
*vacuously*, which is worse than failing):

`tests/unit/test_github_ownership_boundary.py` — narrow `_ALLOWED` (line ~61) to the
single remaining entry, `_SRC_ROOT / "github" / "client.py"`. Delete the two module
docstring bullets that justified the removed entries. Keep the `_detect_violations` AST
detector, the `_modules()` walk and every synthetic-positive-control test exactly as they
are; the guard's value is unchanged and its allowlist is now genuinely one module.

`tests/unit/test_trigger_carries_no_lifecycle_logic.py` — delete
`test_the_webhook_receiver_calls_neither` (line ~163) and the now-unused `_WEBHOOK_ROOT`
constant (line ~52). Reword the module docstring's opening TRIG-01 restatement and the
`_PERMITTED_CALL_SITES` docstring so neither names the receiver as a trigger, while both
still assert the surviving claim: `cli.py` is the one call site, and a dispatched CI job
reaches `drive` through that same `cli.py` with no CI-specific module. Leave
`_LIFECYCLE_ENTRY_POINTS`, `_PERMITTED_CALL_SITES`'s one-entry value and every other test
untouched.

Do not touch `Settings`, `GitHubClient` or any doc in this task — later tasks own those.
Expect `mypy` and the db tier to still be red here (Settings/client cleanup is Task 3);
the unit tier is this task's gate.
  </action>
  <verify>
    <automated>test ! -e src/dark_factory/webhook && uv run pytest -q -m unit</automated>
  </verify>
  <done>`src/dark_factory/webhook/` does not exist, the eight listed test modules are gone, `uv run pytest -q -m unit` passes, and neither surviving guard contains a reference to a non-existent path or an assertion that walks an empty directory.</done>
</task>

<task type="auto">
  <name>Task 2: Retire the two now-caller-less orchestration surfaces (D-01, D-02)</name>
  <files>
src/dark_factory/persistence/repositories.py,
src/dark_factory/orchestrator/answers.py
  </files>
  <read_first>
src/dark_factory/persistence/repositories.py,
src/dark_factory/orchestrator/answers.py
  </read_first>
  <action>
Implements D-01 and D-02 from `<decisions_resolved>` — both already answered, nothing to
ask here. Separated from Task 3 deliberately: these two files are orchestration/persistence
surface whose fate the deletion decided, not `Settings` consumers, and Task 3 is already a
ten-file task.

**`src/dark_factory/persistence/repositories.py` (D-01) — remove both symbols.** Delete
the `GitHubPendingInteraction` pydantic model (line ~271) and the
`github_pending_interaction()` function (lines ~283-33x) in full, plus their two `__all__`
entries (lines ~57 and ~60). Confirm with a grep over `src/` and `tests/` that neither
name survives anywhere before committing — after Task 1 the only references were in the
deleted `webhook/resolve.py` and `tests/unit/test_webhook_resolve.py`.

Then check whether removing them orphans a module-level import. `BaseModel` / `ConfigDict`
from pydantic and `HumanInteraction` from the ORM models may now be unused, or may still
be used by another model or query in the same file — read the file, do not assume either
way. `ruff check` (rule set includes `F`) is the arbiter and is in this task's gate.

Leave `pending_question()` (line ~256) exactly as it is, including its docstring: it names
`orchestrator/answers.submit_answer` as its consumer, which is true and stays true, and it
does not mention the receiver.

**`src/dark_factory/orchestrator/answers.py` (D-02) — keep the parameter, reword the
docstring.** Do NOT touch the `github_comment_id: int | None = None` signature (line 72)
or the `github_comment_id=github_comment_id` argument (line 157); the column is durable
and this parameter is the only way to populate it.

Rewrite the docstring paragraph at lines 78-85. Drop the two sentences that frame the
receiver as the consumer ("the webhook receiver's durable, business-level dedup key" and
"the webhook path is a *caller* of this function, not a second mutation path (D-02)").
Keep, in substance: that `github_comment_id` is the id of the GitHub comment that answered
the question, threaded straight into the `HumanInteractionWrite` this function already
builds, serving as a durable business-level dedup key (Phase 10, D-05); and that today's
only caller — the CLI's `resume --answer` — omits it, leaving it `None` and changing
nothing about the precondition checks, the lease, the re-read or the `expected_status`
guard. Global rule 1 applies: the rewritten paragraph must not say the receiver was
removed.

Leave the `Raises:` block, the exception classes and every line of the function body
untouched. This task changes no behaviour and must change no test.
  </action>
  <verify>
    <automated>uv run ruff check . && uv run mypy src/dark_factory && uv run pytest -q -m "unit or contract"</automated>
  </verify>
  <done>`ruff check` and `mypy src/dark_factory` are clean; the unit and contract tiers pass; `grep -rn 'github_pending_interaction\|GitHubPendingInteraction' src/ tests/` returns nothing; `submit_answer`'s signature still declares `github_comment_id: int | None = None` and `git diff` shows zero changes under `tests/`.</done>
</task>

<task type="auto">
  <name>Task 3: Strip the two credential fields, the two client methods, and rewire every Settings consumer</name>
  <files>
src/dark_factory/config/settings.py,
src/dark_factory/github/client.py,
tests/support/fake_github.py,
tests/conftest.py,
tests/unit/test_settings.py,
tests/db/test_clarification_comment_is_redacted.py,
tests/db/test_run_report.py,
tests/db/test_artifacts_show_reads_committed_content.py
  </files>
  <read_first>
src/dark_factory/config/settings.py,
src/dark_factory/github/client.py,
tests/db/test_clarification_comment_is_redacted.py
  </read_first>
  <action>
**`src/dark_factory/config/settings.py`** — delete the `github_webhook_secret` and
`dispatch_github_token` field declarations (lines 117-118) and the two class-docstring
paragraphs documenting them (lines 84-105). Leave `known_secret_values()` byte-identical:
it walks `model_fields` with an `isinstance(SecretStr)` check precisely so a field coming
or going needs no code change, and that property is the reason this removal is a
two-line field deletion.

**`src/dark_factory/github/client.py`** — delete `for_dispatch` (lines 170-185, Finding 3)
and `dispatch_workflow` (lines 298-322). Delete the module-docstring bullet describing
`gh.rest.actions.create_workflow_dispatch` (lines 36-48). Reword
`authenticated_login`'s docstring (lines 278-288) so the self-comment-filter sentence
cites its surviving consumer — `orchestrator/runner.py`'s crash-resume dedup check before
posting a clarification comment (Finding 4) — instead of the deleted resolver; keep the
"must be genuinely stable for the lifetime of one client / one token" claim, which is
still load-bearing for that consumer. Leave `__all__` unchanged: every name in it
(including `MissingGitHubCredentialError`, still raised by `from_settings`) survives.

**`tests/support/fake_github.py`** — delete the `dispatch_workflow` double (lines 135-150).
Reword the class docstring's `authenticated_login` cross-reference only if it names the
receiver.

Task 2 already handled `orchestrator/answers.py` and `persistence/repositories.py`; do
not revisit either file here.

**`tests/conftest.py`** — in `fake_settings` (lines ~450-463): drop the
`github_webhook_secret=` kwarg. Per Finding 6, replace `_FAKE_WEBHOOK_SECRET` with a
non-pattern-matching fake value bound to a surviving field —
`_FAKE_ANTHROPIC_KEY = "sk-ant-FAKEfakeFAKEfake0000000000000000"` passed as
`anthropic_api_key=`. Before committing, confirm against
`src/dark_factory/events/redaction.py`'s `_PATTERNS` list that the chosen literal matches
none of them (postgres URL, `github_pat_`, `gh[porsu]_`, bearer-auth, 40/64-char hex) —
if it does, `redact()` would catch it by shape and the two-mode proof collapses. Rewrite
the fixture's explanatory comment block to describe the new value's purpose (a
>=8-char, greppable, shape-unmatched known value for redaction coverage) without naming
the removed subsystem.

**`tests/db/test_clarification_comment_is_redacted.py`** — rename
`_CONFIGURED_WEBHOOK_SECRET` to a neutral name (e.g. `_CONFIGURED_KNOWN_VALUE_SECRET`),
set it to the exact literal `fake_settings` now configures, and update all nine usage
sites (lines 83, 93, 235-238, 268, 278, 354, 417, 429). Retarget the line-235/237 sanity
assertion from `fake_settings.github_webhook_secret` to `fake_settings.anthropic_api_key`
— that assertion is the drift guard tying this module to the fixture and must keep
tying it. Rewrite `_NON_SECRET_WORDING` (line 90) so the question prose no longer talks
about rotating a webhook secret while still being plausible human-question text that
carries both planted literals. Leave `_PATTERN_ONLY_TOKEN`, the module's two-mode
structure and `test_build_clarification_comment_still_contains_both_planted_literals`
(the non-vacuity control) structurally intact.

**`tests/db/test_run_report.py`** (lines 142, 233) and
**`tests/db/test_artifacts_show_reads_committed_content.py`** (lines 67, 167) — delete the
local `_FAKE_WEBHOOK_SECRET` constant and the `github_webhook_secret=` kwarg. Neither
module asserts on the value, so no replacement is needed. Note that `extra="ignore"`
means leaving the kwarg in place would *silently* do nothing rather than raise — so these
two must be found by grep, not by a failing test.

**`tests/unit/test_settings.py`** — delete the six field-specific tests (lines 279-340:
the two `*_defaults_to_none`, the two `known_secret_values_maps_*`, the two
`known_secret_values_omits_unset_*`) and the two `_set_env` dictionary entries with their
explanatory comments (lines 26-38, keeping `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`,
`COPILOT_GITHUB_TOKEN` and the rest). Verified: this module contains no exact-field-set
or `model_fields` inventory assertion, so no additional edit is needed.
  </action>
  <verify>
    <automated>uv run mypy src/dark_factory && uv run ruff check . && uv run pytest -q -m "unit or contract"</automated>
  </verify>
  <done>`mypy --strict` over `src/dark_factory` is clean, `ruff check` is clean, the unit and contract tiers pass, `Settings` declares neither removed field, `GitHubClient` exposes neither removed method, and `grep -n 'anthropic_api_key' tests/conftest.py` shows the fixture configuring the replacement known-value credential.</done>
</task>

<task type="auto">
  <name>Task 4: Drop the webhook extra, relock, and rescue the package-wide import guard</name>
  <files>
pyproject.toml,
uv.lock,
tests/unit/test_webhook_import_needs_no_database.py,
tests/unit/test_package_import_needs_no_database.py,
tests/unit/test_unit_tier_needs_no_database.py,
tests/unit/test_qual01_ci_coverage.py
  </files>
  <read_first>
pyproject.toml,
tests/unit/test_webhook_import_needs_no_database.py
  </read_first>
  <action>
**`pyproject.toml`** — delete the `webhook = ["starlette>=0.42,<1", "uvicorn>=0.34,<1"]`
entry from `[project.optional-dependencies]` (lines 44-47) and the second half of the
preceding comment block (lines 31-38) that explains the extra's isolation rule. Keep the
`mcp` extra, its first-paragraph comment (lines 26-30) and
`tests/unit/test_no_mcp_import_in_core.py` untouched — that boundary still exists.

**`uv.lock`** — regenerate with `uv lock` (not `uv lock --upgrade`: this must be a
removal, not a dependency bump). `.github/workflows/ci.yml` installs with
`uv sync --all-extras --dev --frozen`, so a stale lock fails CI at the install step
before a single test runs. Inspect the resulting diff: it should remove only the
`starlette`/`uvicorn` nodes and the `webhook` extra reference, and leave `httpx`
(pulled transitively by `githubkit`) in place. Anything else in the diff is a signal to
stop and report, not to proceed.

**Rename, do not delete, the package-wide import guard (Finding 1).** Move
`tests/unit/test_webhook_import_needs_no_database.py` to
`tests/unit/test_package_import_needs_no_database.py` with `git mv` so the rename is
visible in history, then:
- delete `test_webhook_app_module_exposes_only_the_build_app_factory` (line ~233), the
  only genuinely webhook-specific test in the module
- keep all three remaining tests unchanged, including
  `test_the_sweep_harness_detects_a_module_that_constructs_settings_at_import_time`
  (the non-vacuity control for the package sweep — without it the sweep could pass for
  the wrong reason)
- rewrite the module docstring to describe what it actually guards: importing
  `dark_factory` and every module `pkgutil.walk_packages` yields beneath it must never
  require a reachable database (G-11-1). Keep the three load-bearing explanations
  verbatim in substance: why `cwd=tmp_path` is mandatory (the repo's git-ignored `.env`
  would make the sweep pass vacuously), why the two database variables are *absent*
  rather than empty strings, and why `tests/support/subprocess_runner.py`'s helpers
  cannot serve this module.

**Prose-only follow-ups to the rename** (both verified to be comments, never imports):
- `tests/unit/test_unit_tier_needs_no_database.py` — update the three references at lines
  2, 27 and 101 to the new module name. Its `_ENV_ALLOWLIST` is its own tuple, reused as
  an idiom and not imported, so no code change.
- `tests/unit/test_qual01_ci_coverage.py` — line 59's comment names
  `tests/db/test_webhook_dispatches_resume.py` as a module deliberately excluded from
  `_QUAL01_SCENARIOS`. Rewrite the comment to retain its surviving rule (do not add
  `test_cross_machine_resume.py`; a guard whose green depends on another plan's
  completion order is a false failure waiting to happen) without naming the deleted
  module. `_QUAL01_SCENARIOS` itself needs no change — verified that none of its eight
  scenario entries maps to a deleted module.
  </action>
  <verify>
    <automated>uv sync --all-extras --dev --frozen && uv run pytest -q tests/unit/test_package_import_needs_no_database.py tests/unit/test_unit_tier_needs_no_database.py tests/unit/test_qual01_ci_coverage.py</automated>
  </verify>
  <done>`pyproject.toml` declares only the `mcp` extra; `uv sync --all-extras --dev --frozen` succeeds against the regenerated `uv.lock`; `tests/unit/test_package_import_needs_no_database.py` exists with three passing tests and `tests/unit/test_webhook_import_needs_no_database.py` does not exist; `git log --follow` shows the rename rather than a delete-plus-add.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Add the answer input to both shipped resume.yml templates and retarget the doc guard</name>
  <files>
README.md,
scripts/scaffold_target_repo.py,
tests/unit/test_resume_workflow_reference_doc.py
  </files>
  <read_first>
tests/unit/test_resume_workflow_reference_doc.py,
/Users/maryiakrauchanka/portfolio/app-int/.github/workflows/resume.yml
  </read_first>
  <behavior>
- The sentinel-bracketed README block parses as YAML and declares a
  `workflow_dispatch` input named `answer` with `required: false` and `type: string`,
  alongside the existing `required: true` `run_id`.
- `scripts/scaffold_target_repo.py`'s `RESUME_WORKFLOW_TEMPLATE` declares the identical
  `answer` input, so a freshly scaffolded repository supports
  `gh workflow run resume.yml -f run_id=<id> -f answer=<text>` with no hand-editing.
- The reference block still contains exactly one step invoking `dark-factory resume`, and
  the run id still reaches that command from the workflow input rather than a literal.
- The reference block still carries zero YAML `if:` keys on any job or step.
- The reference block's `permissions:` mapping still equals
  `{contents: write, issues: write, pull-requests: write}` exactly.
- No test asserts that `DISPATCH_GITHUB_TOKEN` appears in `README.md` or `.env.example`.
  </behavior>
  <action>
This task adds a capability the surviving documented flow depends on (Finding 7) — it is
not a docs-only edit. Implements D-03 from `<decisions_resolved>` (mirror the proven-live
app-int shape); nothing to ask here.

Write the guard changes first, watch them fail, then edit the two templates.

**`tests/unit/test_resume_workflow_reference_doc.py`:**
- Add a test asserting the `answer` input's presence and shape (`required: false`,
  `type: string`) beside the existing `run_id` assertion, modelled on
  `test_the_reference_workflow_declares_a_run_id_input`'s structure and failure messages.
- Delete `test_the_dispatch_credential_is_named_consistently` (line ~243) and the
  `_DISPATCH_TOKEN_NAME` constant (line ~56). Check whether `_ENV_EXAMPLE_PATH` (line 33)
  has any other reader; if not, delete it too, and `ruff check` will confirm.
- Rewrite `test_the_reference_workflow_grants_exactly_the_needed_permissions`'s docstring
  (line ~249): keep the whole-mapping-equality rationale and the per-scope justification
  verbatim in substance, but replace the explanation of why `actions:` is absent. It is
  now absent because nothing in Dark Factory dispatches a workflow at all — the dispatch
  is a human action outside any job's token — not because a separate process holds a
  separate credential.
- Widen `test_the_reference_workflow_resumes_exactly_once` (D-03) so the run id may reach
  the command either directly in the step's `run:` text or via a step `env:` binding whose
  value references the workflow input. Assert against the step's combined `run` + `env`
  text, keep the exactly-one-step count, and keep the "not a literal id" failure message's
  intent. Note for the next reader why the assertion widened: the reference workflow now
  binds inputs through `env:` rather than interpolating them into the command, so a guard
  reading only `step["run"]` would reject the hardened shape.
- Leave the sentinel constants, `_INSTALL_GUIDANCE_SUBSTRING`, the CI-handoff-section
  extractor and both `LIVE_RUNTIMES`-parametrized worker-runtime tests alone. The
  install-guidance ordering test keys on the commented `Install the worker runtime` step,
  which must stay above the resume step in both templates.

**`README.md`'s sentinel block and `scripts/scaffold_target_repo.py`'s
`RESUME_WORKFLOW_TEMPLATE`** — make the same two edits to both, keeping them in sync
(they are independent copies; the STATE.md blocker from quick task `261031-cp4` records
what happens when they drift):
1. Add the `answer` input under `workflow_dispatch.inputs` with
   `description: "Answer to the run's open human question (omit to just re-drive)"`,
   `required: false`, `type: string` — the exact shape proven live in app-int.
2. Rework the `Resume the run` step per D-03, mirroring app-int: a multi-line `run:` that
   invokes `dark-factory resume "$RUN_ID" --answer "$RUN_ANSWER"` when the answer variable
   is non-empty and `dark-factory resume "$RUN_ID"` otherwise, with `RUN_ID` and
   `RUN_ANSWER` bound in the step's `env:` block from the workflow inputs. Keep every
   existing `env:` entry (`DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`, the
   worker credential / `{{WORKER_CREDENTIAL_ENV}}` placeholder) unchanged — per Finding 8,
   the `GITHUB_TOKEN` question belongs to a different task.

Preserve the scaffold template's `{{INSTALL_SOURCE}}` and `{{WORKER_CREDENTIAL_ENV}}`
placeholders and the `Install uv` step added by quick task `261031-cp4` exactly as they
are. Note that the scaffold template is a Python string containing `${{ ... }}` GitHub
expressions — confirm the existing escaping convention in that file before adding new
expression text, and do not change it.
  </action>
  <verify>
    <automated>uv run pytest -q tests/unit/test_resume_workflow_reference_doc.py && uv run python -c "import pathlib,re,yaml; t=pathlib.Path('scripts/scaffold_target_repo.py').read_text(); m=re.search(r'RESUME_WORKFLOW_TEMPLATE = \"\"\"\\\\\n(.*?)\n\"\"\"', t, re.S); assert m, 'RESUME_WORKFLOW_TEMPLATE not found'; d=yaml.safe_load(m.group(1).replace('{{INSTALL_SOURCE}}','x').replace('{{WORKER_CREDENTIAL_ENV}}','')); i=d['on']['workflow_dispatch']['inputs']; assert set(i)=={'run_id','answer'}, i; assert i['answer']['required'] is False; print('scaffold resume template OK')"</automated>
  </verify>
  <done>Every test in `tests/unit/test_resume_workflow_reference_doc.py` passes including the new `answer`-input assertion; both the README sentinel block and the scaffold template declare `run_id` (required) and `answer` (optional); no test asserts `DISPATCH_GITHUB_TOKEN`'s presence in any file; the scaffold template still parses as a GitHub Actions workflow after placeholder substitution.</done>
</task>

<task type="auto">
  <name>Task 6: Rewrite the documented resume flow across README, four docs files, and both env templates</name>
  <files>
README.md,
docs/ARCHITECTURE.md,
docs/DEVELOPMENT.md,
docs/GETTING-STARTED.md,
docs/CONFIGURATION.md,
.env.example,
scripts/scaffold_target_repo.py
  </files>
  <read_first>README.md</read_first>
  <action>
Every edit below replaces a two-path story (automatic webhook resume, with manual resume
as a fallback) with a one-path story (a human replies on the issue; a human — or any
external script — then dispatches `resume.yml`). Global rule 1 applies throughout: no
sentence anywhere may say the receiver was removed.

**`README.md`** — seven regions:
- line 34: drop the GitHub-webhook item from the "after a crash, a local-to-CI handoff,
  ..." list of things a committed step survives. The claim is about durability and still
  holds; only the enumeration changes.
- lines 113-114: delete the `DISPATCH_GITHUB_TOKEN` bullet from the environment-variable
  list.
- lines 321-327 ("What this is"): rewrite so the handoff is the human dispatching
  `resume.yml` after replying on the issue. Keep the invariant sentence — *the trigger
  carries no lifecycle logic; every entry point reaches the same `advance(run_id)`* — and
  narrow its enumeration to the local CLI and a dispatched CI job.
- line 340: delete deployment-model step 4 and renumber step 5 to 4.
- lines 394-396: the `actions: write`-is-absent justification. Replace with: nothing in
  Dark Factory dispatches a workflow, so no job and no Dark Factory process needs that
  scope; the dispatch is a human action using the human's own `gh` credentials.
- lines 411-427 ("The full flow"): rewrite the six numbered steps as the proven manual
  flow — (1) `dark-factory run github:<owner>/<repo>#<n>` creates and drives the run and
  may pause `WAITING_HUMAN` with a clarifying comment on the issue; (2) the human replies
  on the issue; (3) the human runs
  `gh workflow run resume.yml -f run_id=<id> -f answer=<text>` against the target
  repository (or any external script does, since the dispatch carries no Dark Factory
  logic); (4) a fresh runner checks out, installs `dark-factory`, and
  `dark-factory resume <run_id> --answer <text>` records the answer and re-materializes
  everything from Neon plus a fresh git worktree; (5) the run reaches `COMPLETED`
  (possibly publishing a PR) or pauses again and the loop repeats from step 2. Also note
  that `--answer` may be omitted to simply re-drive a run that is not waiting on a human
  — that is what the optional `answer` input buys.
- lines 431-436: the sentinel-block preamble says a test "asserts it still parses and
  still says what the dispatcher sends". Reword: the test asserts it still parses and
  still declares the inputs the documented `gh workflow run` command passes.
- lines 522-526: same `actions`-scope justification as line 394; apply the same
  replacement, and drop the forward reference to "The dispatch credential".
- lines 576-578: delete the "This table says nothing about `DISPATCH_GITHUB_TOKEN`"
  paragraph that follows the worker-runtime table.
- lines 580-595: delete the whole `### The dispatch credential` subsection.
- lines 597-608: delete the whole `### When the resume does not fire` subsection — all
  four rows are receiver log events. Keep its surviving idea by folding one sentence into
  the "full flow" rewrite: the human's answer is recorded durably by
  `dark-factory resume --answer` itself, and a run can always be resumed again from any
  machine with `dark-factory resume <run_id>`.

Confirm after editing that `## Configuration reference` still immediately follows the
`### The worker runtime` section — `tests/unit/test_resume_workflow_reference_doc.py`'s
`_CI_HANDOFF_SECTION_NEXT_HEADING` constant is `"## Configuration reference"` and bounds
the region two parametrized tests search. Deleting the two subsections above moves that
boundary; the worker-runtime table and every binary/credential string in it must stay
inside the bounded region.

**`docs/ARCHITECTURE.md`** — line 25: narrow the "any process on any machine" enumeration
to a local CLI invocation and a GitHub Actions job. Lines 34-35: drop the receiver from
the secondary-concerns sentence. Lines 42 and 61: delete the `WEBHOOK` node and the
`WEBHOOK --> ANSWERS` edge from the mermaid component diagram. Lines 82-85: the
`pyproject.toml`-enforces-two-boundaries sentence becomes one boundary (`mcp`), still
proven by `test_no_mcp_import_in_core.py`. Lines 139-144 (pause-and-resume step 8):
`dark-factory resume --answer` becomes the only way out of `WAITING_HUMAN`; delete the
sentence about the webhook path also dispatching a `workflow_dispatch`. Line 187: delete
the `webhook/` row from the directory tree. Lines 197-203: drop `webhook/` from the
"each isolated behind their own package" list, keeping `git/` and `github/`.

**`docs/DEVELOPMENT.md`** — line 20: the `uv sync --all-extras --dev` comment names
"the mcp/webhook extras"; make it the `mcp` extra. Lines 35-40: rewrite from "Two of the
three optional-dependency extras" to the single `mcp` extra, cite only
`tests/unit/test_no_mcp_import_in_core.py`, and drop the reference to the renamed import
guard (Task 4 moved it and it is not an extras-isolation proof).

**`docs/GETTING-STARTED.md`** — delete the `DISPATCH_GITHUB_TOKEN` (line 138) and
`GITHUB_WEBHOOK_SECRET` (line 139) rows from the environment-variable table. Delete the
whole `## Step 7 (optional)` section (lines 255-267), preserving its one surviving
sentence — a run can start from a GitHub issue with
`dark-factory run github:<owner>/<repo>#<n>` — by folding it into Step 6 or wherever
GitHub-issue intake is already introduced; check whether issue intake is documented
anywhere else in the file first, and do not lose it. If Step 7 was the last numbered
step, confirm no later cross-reference points at it.

**`docs/CONFIGURATION.md`** — delete the `DISPATCH_GITHUB_TOKEN` row (line 37) from the
`.env.example` table and the `GITHUB_WEBHOOK_SECRET` row (line 45) from the
"declared on `Settings` but not in `.env.example`" table. Both tables enumerate real
`Settings` fields, so after Task 3 these rows would be documenting fields that do not
exist.

**`.env.example`** — delete the `DISPATCH_GITHUB_TOKEN` block (the comment paragraph plus
its assignment, the last entry in the file). Note the file declares no
`GITHUB_WEBHOOK_SECRET` assignment at all — it only mentioned the name inside the
dispatch comment — so that reference disappears with the block.

**`scripts/scaffold_target_repo.py`** — the generated `.env.example` template carries a
`DISPATCH_GITHUB_TOKEN` entry (lines ~237-238) and a `GITHUB_WEBHOOK_SECRET` entry
(lines ~243-244). Delete both, with their comment paragraphs. Leave
`RUN_WORKFLOW_TEMPLATE`, the `workflow_dispatch` triggers at lines 260 and 319 (those are
the generated workflows' own legitimate manual triggers, unrelated to the receiver), the
`Install uv` steps and `GITIGNORE_CONTENT` untouched. If a scaffold-output test asserts
the generated `.env.example`'s exact content, update it in the same commit.
  </action>
  <verify>
    <automated>uv run pytest -q -m "unit or contract" && uv run python -c "import pathlib,re; bad={p:[(n,l.rstrip()) for n,l in enumerate(pathlib.Path(p).read_text().splitlines(),1) if re.search(r'webhook|dispatch_github_token|DISPATCH_GITHUB_TOKEN|GITHUB_WEBHOOK_SECRET|dispatch_workflow',l,re.I)] for p in ['README.md','docs/ARCHITECTURE.md','docs/DEVELOPMENT.md','docs/GETTING-STARTED.md','docs/CONFIGURATION.md','.env.example','scripts/scaffold_target_repo.py','pyproject.toml']}; bad={k:v for k,v in bad.items() if v}; assert not bad, bad; print('docs clean')"</automated>
  </verify>
  <done>The unit and contract tiers pass; the eight listed files contain zero case-insensitive matches for the removed subsystem, its two credentials or its dispatch call; README's `### The worker runtime` section still immediately precedes `## Configuration reference`; and both the README reference block and the scaffold template still carry the commented `Install the worker runtime` step above the resume step.</done>
</task>

<task type="auto">
  <name>Task 7: Whole-tree sweep and full gate run</name>
  <files>tests/, src/, docs/, README.md, .env.example, pyproject.toml, scripts/scaffold_target_repo.py</files>
  <action>
Close the removal with one sweep over everything outside `.planning/`, then run every
gate CI runs.

Sweep (report, then fix or justify each hit — do not suppress):
- Case-insensitive `webhook` across `src/ tests/ docs/ scripts/ README.md .env.example
  pyproject.toml uv.lock .github/`. Expect zero. Filter comment lines out of any count
  you turn into a gate (`grep -v '^#' | grep -c`) so a header comment cannot
  self-invalidate the check.
- `dispatch_workflow`, `for_dispatch`, `dispatch_github_token`,
  `DISPATCH_GITHUB_TOKEN`, `github_webhook_secret`, `GITHUB_WEBHOOK_SECRET`,
  `starlette`, `uvicorn`, `/webhooks/github`, `webhook_events` across the same set.
  Expect zero everywhere except `uv.lock`, which should also be zero after Task 4's
  relock — if `starlette` or `uvicorn` survives there, something else now depends on it
  and that is a finding to report, not to delete.
- `git status --porcelain` shows no stray `__pycache__` directory under a deleted package
  and no untracked leftover test file.

Then run, in order, every gate `.github/workflows/ci.yml` runs:
1. `uv run ruff check .`
2. `uv run ruff format --check .` — note that `[tool.ruff] extend-exclude` already scopes
   formatting to real code. Pre-existing format drift in files this task never touched is
   a known, acknowledged deferral (STATE.md: 19 files, carried since 11-10); report it,
   do not fix it here.
3. `uv run mypy src/dark_factory`
4. `uv run pytest -q tests/unit/test_no_worker_name_leak.py`
5. `uv run pytest -q -m "unit or contract"`
6. `uv run pytest -q -m db` — this tier needs a reachable PostgreSQL 17 and is where
   Task 3's three rewired modules (`test_clarification_comment_is_redacted.py`,
   `test_run_report.py`, `test_artifacts_show_reads_committed_content.py`) are actually
   proven. If no `DATABASE_URL` is reachable, run `uv run pytest -q -m db --collect-only`
   as the available substitute and record the db tier as DEFERRED in the SUMMARY, naming
   those three modules explicitly as the unverified surface. Do not report the task green
   on a collect-only run without that explicit deferral.

Finally, record in the SUMMARY: (a) that D-01/D-02/D-03 were resolved as Q1=A, Q2=A,
Q3=A by the developer before execution, and that each was implemented as stated
(repositories.py symbols removed; `submit_answer`'s parameter kept with a reworded
docstring; the reference workflow binding inputs through `env:`); (b) the eight
investigation findings that diverged from the task description, especially Finding 7 (the
`answer` input did not exist and was added here, so the documented command now works) and
Finding 1 (the package-wide import guard was rescued, not deleted); (c) that GIT-06 is
deliberately retired by this removal while `.planning/milestones/v1.0-REQUIREMENTS.md`
still records it Complete, because archived milestone artifacts are a historical record
this task does not rewrite; (d) the db-tier verification status.
  </action>
  <verify>
    <automated>uv run ruff check . && uv run mypy src/dark_factory && uv run pytest -q tests/unit/test_no_worker_name_leak.py && uv run pytest -q -m "unit or contract" && uv run python -c "import pathlib,re,subprocess; roots=['src','tests','docs','scripts','.github']; files=[p for r in roots for p in pathlib.Path(r).rglob('*') if p.is_file() and p.suffix in {'.py','.md','.yml','.yaml','.toml','.example'}]+[pathlib.Path(x) for x in ['README.md','.env.example','pyproject.toml','uv.lock']]; pat=re.compile(r'webhook|dispatch_workflow|for_dispatch|dispatch_github_token|github_webhook_secret|starlette|uvicorn|webhook_events',re.I); hits=[(str(p),n,l.strip()) for p in files for n,l in enumerate(p.read_text(errors='replace').splitlines(),1) if pat.search(l)]; assert not hits, hits[:25]; print('tree clean:',len(files),'files swept')"</automated>
  </verify>
  <done>`ruff check`, `mypy src/dark_factory`, the worker-name leak guard and the unit+contract tiers all pass; the sweep over `src/ tests/ docs/ scripts/ .github/ README.md .env.example pyproject.toml uv.lock` finds zero references to the removed subsystem, its credentials, its client methods or its dependency extra; `git status --porcelain` is clean of stray artifacts; and the SUMMARY records the decision answers, the eight findings, the deliberate GIT-06 retirement and the db-tier verification status.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub -> Dark Factory (inbound HTTP) | **Eliminated by this task.** The unauthenticated network edge that accepted signed `issue_comment` deliveries ceases to exist, along with the HMAC verification path, the 401/400 non-echoing responses and the self-comment filter that guarded it. |
| Settings -> persisted/logged/committed text | `redact()` substitutes known secret values; two fields leave the known-value set here, and one test's proof of that mechanism is rewired. |
| `workflow_dispatch` input -> CI shell | A `resume.yml` `answer` input is untrusted human text that reaches a shell command in a job. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-jmw-01 | Information disclosure | `tests/db/test_clarification_comment_is_redacted.py` two-mode proof | high | mitigate | Task 3 re-sources the known-value literal onto a surviving `SecretStr` field and verifies against `events/redaction.py`'s `_PATTERNS` that the literal matches no pattern. If it did, the test would pass via shape-matching while the known-value substitution path went unproven — a silent loss of coverage over the mechanism that keeps real credentials out of Neon, event payloads, artifacts and PR diffs. The module's own fixture-equality sanity assertion is retargeted, not deleted, so the two files cannot drift apart. |
| T-jmw-02 | Information disclosure | `Settings.known_secret_values()` | low | accept | Removing two fields shrinks the known-value set. Any value a deployer still has in `.env` under the old names is now unknown to `redact()` — but it is also no longer read, passed, logged or persisted by any code path, so there is nothing to redact it out of. `extra="ignore"` means a leftover `.env` line is inert, not an error. |
| T-jmw-03 | Elevation of privilege | `DISPATCH_GITHUB_TOKEN` as a provisioned credential | low | mitigate | Documentation telling deployers to provision an `Actions: Read and write` PAT is deleted, so the task strictly reduces the credential surface a deployment is told to create. Task 7's sweep proves no code path reads it. Per Finding 8, what a deployer names their own Actions secret is out of scope and untouched. |
| T-jmw-04 | Tampering | `resume.yml`'s `answer` input reaching a shell command | medium | mitigate | D-03 (resolved) binds `inputs.run_id`/`inputs.answer` through the step's `env:` block and references them as shell variables, rather than interpolating `${{ }}` expression text directly into the command — the standard hardening against expression injection from a `workflow_dispatch` input. The rejected alternative (direct interpolation) was explicitly flagged as placing untrusted input into a shell command, so the chosen shape is a decision rather than an accident. |
| T-jmw-05 | Denial of service | `uv.lock` / `pyproject.toml` skew | medium | mitigate | `ci.yml` installs with `--frozen`; a lock not regenerated after dropping the extra fails every CI job at the install step. Task 4 relocks and gates on `uv sync --all-extras --dev --frozen`, and instructs stopping if the lock diff contains anything beyond the two removed packages. |
| T-jmw-06 | Repudiation | vacuously-passing structural guards | medium | mitigate | Three guards would pass for the wrong reason after a naive deletion: `test_the_webhook_receiver_calls_neither` (rglob over a missing directory yields zero offenders), `test_github_ownership_boundary`'s two dead allowlist entries, and the package-wide import sweep if it were deleted outright (Finding 1). Tasks 1 and 4 repair each one so the surviving assertions still bite. A guard that cannot fail is worse than no guard: it reports safety it never checked. |
| T-jmw-SC | Tampering | npm/pip/cargo installs | n/a | accept | No package is installed by this task. `uv lock` only *removes* `starlette` and `uvicorn` nodes, so no package-legitimacy gate applies. Task 4 requires inspecting the lock diff specifically to confirm it is removal-only. |
</threat_model>

<verification>
1. `uv run ruff check .` — clean.
2. `uv run mypy src/dark_factory` — clean under `--strict`.
3. `uv run pytest -q tests/unit/test_no_worker_name_leak.py` — passes (QUAL-04).
4. `uv run pytest -q -m "unit or contract"` — passes.
5. `uv sync --all-extras --dev --frozen` — succeeds against the regenerated `uv.lock`.
6. `uv run pytest -q -m db` — passes, or is recorded DEFERRED with the three rewired db
   modules named (Task 7).
7. Task 7's tree sweep — zero references to the removed subsystem outside `.planning/`.
8. `dark-factory resume --answer` behaviour unchanged: the CLI path, `submit_answer`'s
   WAITING_HUMAN preconditions, the lease and the `expected_status` guard are all
   untouched, proven by the surviving `tests/db/test_pause_path_atomic.py`,
   `test_cross_machine_resume.py`, `test_pause_mechanism_generic.py` and
   `tests/integration/test_redaction_interactions.py`.
</verification>

<success_criteria>
- `src/dark_factory/webhook/` is gone and nothing under `src/` or `tests/` imports it.
- `Settings` declares neither `github_webhook_secret` nor `dispatch_github_token`;
  `known_secret_values()` is byte-identical.
- `GitHubClient` exposes neither `dispatch_workflow` nor `for_dispatch`;
  `authenticated_login` and every other method survive with no behaviour change.
- The `webhook` optional extra is gone from `pyproject.toml` and `uv.lock` agrees.
- `tests/unit/test_package_import_needs_no_database.py` exists and its three tests pass —
  the G-11-1 package-wide import guard was rescued, not lost.
- Both shipped `resume.yml` templates declare an optional `answer` input, so the newly
  documented `gh workflow run resume.yml -f run_id=<id> -f answer=<text>` command works
  against a scaffolded repository.
- README, the four `docs/` files, `.env.example` and the scaffold script document exactly
  one resume path, with no tombstone naming what was removed.
- The answer-submission capability (`human_interactions`, `submit_answer`,
  `dark-factory resume --answer`) is behaviourally unchanged.
- D-01 applied: `github_pending_interaction` / `GitHubPendingInteraction` are gone.
- D-02 applied: `submit_answer`'s `github_comment_id` parameter survives with a reworded
  docstring, and no test under `tests/` changed for it.
- D-03 applied: both `resume.yml` templates bind `run_id`/`answer` through the resume
  step's `env:` block rather than interpolating them into the command text.
- No Alembic revision was added or modified.
</success_criteria>

<output>
Create `.planning/quick/261031-jmw-remove-the-webhook-receiver-subsystem-fr/261031-jmw-SUMMARY.md` when done.
</output>
