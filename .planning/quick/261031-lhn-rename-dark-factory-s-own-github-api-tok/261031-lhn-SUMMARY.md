---
phase: quick
plan: 261031-lhn
subsystem: infra
tags: [github, redaction, settings, pydantic-settings, github-actions, security]

requires: []
provides:
  - "Settings.dark_factory_github_token (DARK_FACTORY_GITHUB_TOKEN env var) replaces Settings.github_token (GITHUB_TOKEN)"
  - "_SENSITIVE_KEYS carries both the new and the retained old spelling (add, not replace)"
  - "Scaffolded resume.yml / run.yml templates and the README reference workflow pass a user-creatable secret, never GitHub's reserved GITHUB_TOKEN"
  - "docs/CONFIGURATION.md documents the GITHUB_TOKEN collision mechanism, including the GET /user platform rule"
affects: [github-client, orchestrator-runner, redaction, scaffold-script, docs]

actuals:
  tokens: 17066
  tasks: 5
  commits: 5

tech-stack:
  added: []
  patterns:
    - "D-15 key-name vocabulary entries are additive on a rename: retain the old spelling for third-party text, add the new spelling for the renamed field"
    - "Known-value redaction label provenance (F3/F4): a label only changes for a value that is an EXACT match against Settings.known_secret_values(); a pattern-shaped value (e.g. a bare ghp_ token not configured anywhere) keeps the shape-matched pattern-table label regardless of any field rename"

key-files:
  created:
    - tests/unit/test_redaction_dark_factory_github_token.py
  modified:
    - src/dark_factory/config/settings.py
    - src/dark_factory/events/redaction.py
    - src/dark_factory/github/client.py
    - src/dark_factory/github/__init__.py
    - src/dark_factory/orchestrator/runner.py
    - src/dark_factory/tools/env.py
    - src/dark_factory/git/client.py
    - src/dark_factory/git/committed.py
    - scripts/scaffold_target_repo.py
    - README.md
    - docs/CONFIGURATION.md
    - docs/GETTING-STARTED.md
    - .env.example
    - .gitignore

key-decisions:
  - "F2 regression closed as an ADD, not a replace: _SENSITIVE_KEYS now carries both dark_factory_github_token (the renamed field) and github_token (retained for third-party workflow text echoed into a WorkerResult)"
  - "Corrected the plan's own F4 pre-classification for tests/integration/test_redaction_interactions.py's two github_token label assertions: empirically verified (via a pure redact() call, no DB) that those two sites are pattern-shaped tokens (_Q_TOKEN/_A_TOKEN), never configured as a known secret value, so their label does not change with the rename -- left unchanged rather than blindly following the plan's literal table"
  - "Gate A's residual set is 4 files, not the plan's literal 3: the new sibling test module (tests/unit/test_redaction_dark_factory_github_token.py) legitimately needs the retained old spelling to prove F2's retention half, the same category of exception test_redaction.py already has -- the plan's F7 three-file list was written before this task's own new test module existed"

patterns-established: []

requirements-completed: [SEC-01, TOOL-04]

coverage:
  - id: D1
    description: "Settings exposes dark_factory_github_token bound to DARK_FACTORY_GITHUB_TOKEN; no github_token attribute survives; a Settings built from an environment providing only the old name leaves the credential unset, one providing the new name populates it"
    requirement: "SEC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_settings.py#test_required_urls_load_and_optional_token_defaults_to_none"
        status: pass
      - kind: other
        ref: "negative-control script asserting old-name-only leaves dark_factory_github_token=None and new-name-only populates it (run via uv run python against Settings directly)"
        status: pass
    human_judgment: false
  - id: D2
    description: "_SENSITIVE_KEYS carries both spellings: a dark_factory_github_token dict key and key=value pair are redacted under the new label; old-spelling third-party text is still redacted under the retained label"
    requirement: "SEC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_redaction_dark_factory_github_token.py#test_a_key_value_pair_with_the_new_key_name_is_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_redaction_dark_factory_github_token.py#test_b_a_mapping_key_with_the_new_key_name_is_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_redaction_dark_factory_github_token.py#test_c_old_spelling_in_assignment_form_is_still_redacted"
        status: pass
      - kind: unit
        ref: "tests/unit/test_redaction_dark_factory_github_token.py#test_d_a_configured_credential_with_no_token_shape_is_redacted_by_label"
        status: pass
    human_judgment: false
  - id: D3
    description: "Seven credential-boundary modules (worker env, claude-code/copilot/hermes workers, shell_execute, git_env, cross-process worker_env_boundary) retargeted to seed and assert DARK_FACTORY_GITHUB_TOKEN, proving the boundary still holds for the renamed credential"
    requirement: "TOOL-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_worker_env.py#test_infrastructure_credentials_and_unrelated_keys_never_appear"
        status: pass
      - kind: integration
        ref: "tests/integration/test_worker_env_boundary.py#test_a_real_spawned_process_reports_no_infrastructure_credential_or_unrelated_key"
        status: pass
    human_judgment: false
  - id: D4
    description: "Both scaffolded workflow templates and the README sentinel-delimited reference workflow declare DARK_FACTORY_GITHUB_TOKEN reading secrets.DARK_FACTORY_GITHUB_TOKEN; zero occurrences of the reserved GITHUB_TOKEN env-key/secrets-expression pair survive in README.md or the scaffold script"
    requirement: "SEC-01"
    verification:
      - kind: other
        ref: "grep -cE 'GITHUB_TOKEN:[[:space:]]*\\$\\{\\{[[:space:]]*secrets\\.GITHUB_TOKEN' README.md scripts/scaffold_target_repo.py -> 0 for both files"
        status: pass
      - kind: other
        ref: "grep -cE 'DARK_FACTORY_GITHUB_TOKEN:[[:space:]]*\\$\\{\\{[[:space:]]*secrets\\.DARK_FACTORY_GITHUB_TOKEN[[:space:]]*\\}\\}' scripts/scaffold_target_repo.py -> 2"
        status: pass
      - kind: unit
        ref: "tests/unit/test_resume_workflow_reference_doc.py (all 14 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "docs/CONFIGURATION.md records why the credential's name is distinguished from GITHUB_TOKEN, including the GET /user platform rule"
    verification: []
    human_judgment: true
    rationale: "Documentation-prose quality (clarity, accuracy of the explanation) is a human-judgment call; the automated checks above only prove the mechanism's structural correctness (templates, label behavior), not whether the prose reads well"
  - id: D6
    description: "Full db- and integration-tier execution (needs real PostgreSQL) — in particular the SC5 secret-sweep proofs touched by Task 2, which this session only collected (no import/fixture errors) rather than executed"
    verification: []
    human_judgment: true
    rationale: "Deferred per the plan's own instruction (db tier is historically ~1h against remote Neon); requires a human to run the full suite against real PostgreSQL and confirm green"

duration: ~25min task-commits across two sessions (interrupted by a session rate-limit reset mid-execution)
completed: 2026-11-01
status: complete
---

# Quick Task 261031-lhn: Rename Dark Factory's Own GitHub API Token Summary

**Renamed `Settings.github_token` / `GITHUB_TOKEN` to `Settings.dark_factory_github_token` / `DARK_FACTORY_GITHUB_TOKEN` across production code, tests, docs, `.env.example`, and the scaffold's generated GitHub Actions workflows — fixing a live 403 caused by the old name colliding with GitHub Actions' reserved installation-token secret.**

## Performance

- **Duration:** ~25 min of task-commit work, across two sessions separated by a session rate-limit reset
- **Started:** 2026-10-31T13:39:28Z
- **Completed:** 2026-11-01T07:02:51Z (wall-clock span includes the inter-session gap, not active work time)
- **Tasks:** 5/5
- **Files modified:** 34 (33 modified + 1 new test module)

## Accomplishments

- `Settings` now exposes `dark_factory_github_token` bound to `DARK_FACTORY_GITHUB_TOKEN`, with no alias and no attribute under the old name — proven by a negative-control script showing the old env var name leaves the credential unset and the new one populates it.
- Closed a real D-15 redaction-coverage regression before it could ship: renaming the field without also adding the new key name to `_SENSITIVE_KEYS` would have let `DARK_FACTORY_GITHUB_TOKEN=<value>` key=value text and `{"DARK_FACTORY_GITHUB_TOKEN": "<value>"}` mapping keys pass through `redact()` in the clear. Proved RED (value survived verbatim) before the fix, GREEN after, in a new sibling test module.
- Fixed the actual reported live bug: both scaffolded GitHub Actions workflow templates (`resume.yml`, `run.yml`) and the README's reference workflow now read `secrets.DARK_FACTORY_GITHUB_TOKEN` — a secret name GitHub permits creating — instead of silently resolving to the reserved, `GET /user`-incapable Actions auto-token under `secrets.GITHUB_TOKEN`.
- Retargeted all seven credential-boundary tests (worker env allowlist, three CLI worker adapters, `shell_execute`, `git_env`, the cross-process subprocess boundary proof) so they keep seeding and asserting a credential dark-factory actually reads, rather than silently testing a name that no longer matters.
- `docs/CONFIGURATION.md` gained a "Why not `GITHUB_TOKEN`?" section stating the mechanism — the reserved name, the auto-injected installation token, and the `GET /user` platform rule — not just the conclusion.

## Task Commits

1. **Task 1: Rename the credential end-to-end through production code, closing the D-15 coverage regression** - `582ec65` (feat, tracer)
2. **Task 2: Update the db- and integration-tier credential call sites and known-value label assertions** - `b183c1f` (test)
3. **Task 3: Retarget the credential-boundary tests at the renamed environment variable** - `7d6ca98` (test)
4. **Task 4: Reword the credential-boundary comments and docstrings in production and test-support code** - `1763523` (docs)
5. **Task 5: Rename the credential in documentation, .env.example, and the scaffold templates** - `70da05e` (fix)

_Task 1 was `tdd="true"`: a single commit carries both the RED-then-GREEN test module and the production `_SENSITIVE_KEYS` fix, since the RED state was verified by temporarily reverting the fix in the working tree (not via a separate commit) and re-running the new tests before restoring it._

## Files Created/Modified

- `src/dark_factory/config/settings.py` — field renamed; class docstring's `copilot_github_token` rationale paragraph extended to record the reserved-name collision
- `src/dark_factory/events/redaction.py` — `_SENSITIVE_KEYS` gains `dark_factory_github_token`, retains `github_token`
- `src/dark_factory/github/client.py`, `src/dark_factory/github/__init__.py` — attribute accesses, hardcoded redaction label, docstrings, error message
- `src/dark_factory/orchestrator/runner.py` — four attribute accesses, three comments
- `src/dark_factory/tools/env.py`, `src/dark_factory/git/client.py`, `src/dark_factory/git/committed.py`, `tests/support/shipped_config.py` — comments/docstrings only (Task 4)
- `tests/conftest.py`, `tests/unit/test_settings.py`, `tests/unit/test_github_client.py`, `tests/unit/test_git_push.py`, `tests/unit/test_log_redaction.py` — field/env renames + label assertions per F4
- `tests/unit/test_redaction_dark_factory_github_token.py` — new sibling of `test_redaction.py`, Tests A–D for the F2 regression
- `tests/db/test_run_report.py`, `tests/db/test_artifacts_show_reads_committed_content.py`, `tests/db/test_secret_redaction_e2e_full_pipeline.py`, `tests/integration/test_capability_denial_no_secret_leak.py`, `tests/integration/test_redaction_interactions.py`, `tests/integration/test_secret_redaction_e2e.py` — `Settings(...)` keyword + constant renames; `test_secret_redaction_e2e.py`'s log-text label assertion changed to the new field name (known-value site)
- `tests/unit/test_worker_env.py`, `tests/unit/test_claude_code_worker.py`, `tests/unit/test_copilot_worker.py`, `tests/unit/test_hermes_worker.py`, `tests/unit/test_shell_execute.py`, `tests/unit/test_git_worktree.py`, `tests/integration/test_worker_env_boundary.py` — credential-boundary seed/assert pairs retargeted
- `scripts/scaffold_target_repo.py` — `.env.example` template, both workflow templates' `env:` key + `secrets.*` expression
- `README.md` — credential bullet, permissions-block prose, sentinel-delimited reference workflow, secrets-this-job-needs sentence, configuration-reference entry
- `docs/CONFIGURATION.md`, `docs/GETTING-STARTED.md` — credential rows and prose mentions, new collision-mechanism section
- `.env.example`, `.gitignore` — assignment/comment renamed

## Decisions Made

- **F2's `_SENSITIVE_KEYS` edit is an ADD, not a replace.** The old `github_token` entry is retained because it is still the spelling a target repo's own CI workflow text, echoed back into a `WorkerResult`, legitimately carries. Proven empirically: temporarily removing the new entry reproduced the regression (values survived verbatim in both the `key=value` and mapping-key redaction paths) before the fix landed.
- **F4's label-provenance rule is the reason this was never a find-and-replace.** `_scrub_known` (exact known-value substitution) runs before the D-15 pattern table inside `_redact_str`, so a value that is an *exact* configured `Settings` secret gets the renamed field's label, while a value that merely *looks* like a token (shape-matched, e.g. a bare `ghp_...` string never passed to `Settings`) keeps the unchanged pattern-table label regardless of the field rename. Verified per-site with a pure, DB-free `redact()` call for every ambiguous assertion rather than trusting a blanket classification.
- **Corrected the plan's own pre-classification for two specific sites.** `tests/integration/test_redaction_interactions.py`'s two `[redacted:github_token]` assertions (in the swept question/answer) were listed in the plan's investigation findings as "known value / changes," but empirical verification showed the tokens asserted there (`_Q_TOKEN`, `_A_TOKEN`) are never configured into `Settings` — they are pattern-shaped-only fixtures distinct from the test's actual configured credential. Left unchanged, per the plan's own explicit instruction to "confirm per site... rather than assuming it from this list."
- **Gate A's residual allowlist grew from 3 files to 4.** The new sibling test module this task created (`tests/unit/test_redaction_dark_factory_github_token.py`) legitimately needs the retained old spelling in one assertion (Test C, proving F2's retention half) — exactly the same category of exception `tests/unit/test_redaction.py` already has. The plan's F7 three-file list was written before this task's own new file existed, so this is a necessary extension of that allowlist, not a violation of it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A stray bare `github_token` spelling in an unrelated local test variable**
- **Found during:** Task 3
- **Issue:** `tests/unit/test_claude_code_worker.py`'s `test_pattern_only_secret_not_in_settings_is_still_redacted` used a local variable named `github_token` (a pattern-shaped test fixture, unrelated to the Settings field) that would have shown up as a false Gate A residual outside the F7 allowlist.
- **Fix:** Renamed the local variable to `pattern_shaped_token`.
- **Files modified:** `tests/unit/test_claude_code_worker.py`
- **Verification:** Gate A's residual-file grep over this file returns zero hits; `uv run pytest tests/unit/test_claude_code_worker.py` passes.
- **Committed in:** `7d6ca98` (Task 3 commit)

**2. [Rule 2 - Missing coverage] Non-vacuity check added to `test_worker_env.py`**
- **Found during:** Task 3
- **Issue:** The plan explicitly called for proving at least one retargeted credential-boundary assertion is not vacuous (i.e., that the seeded credential is genuinely observable before the exclusion check runs).
- **Fix:** Added an assertion reading `os.environ["DARK_FACTORY_GITHUB_TOKEN"]` back out immediately after seeding, before calling `build_worker_env`.
- **Files modified:** `tests/unit/test_worker_env.py`
- **Verification:** `uv run pytest tests/unit/test_worker_env.py` passes with the new assertion in place.
- **Committed in:** `7d6ca98` (Task 3 commit)

**3. [Rule 1 - Bug] My own added comment briefly reintroduced the bare old spelling**
- **Found during:** Task 2 (self-review before the Task 2 commit)
- **Issue:** A comment I wrote in `tests/integration/test_secret_redaction_e2e.py` explaining the F3/F4 label-provenance reasoning named the bare old spelling in prose, which would have failed Gate A (naming_discipline rule 2 forbids this outside README/docs prose).
- **Fix:** Reworded the comment to describe the mechanism ("the generic shape-matched pattern label a token of this prefix would otherwise receive") without naming the old spelling.
- **Files modified:** `tests/integration/test_secret_redaction_e2e.py`
- **Verification:** Gate A's residual-file grep over this file returns zero hits.
- **Committed in:** `b183c1f` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 bug — stray variable name; 1 missing-coverage addition; 1 bug — self-introduced naming-discipline violation caught and fixed before commit)
**Impact on plan:** All three are necessary for Gate A to resolve cleanly and for the non-vacuity requirement the plan itself specified. No scope creep.

## Issues Encountered

None beyond the deviations above.

## User Setup Required

None — no external service configuration required. However, see "Next Phase Readiness" below for an action a human must take in a **separate** repository.

## Next Phase Readiness

- **Deferred to `/gsd-verify-work`:** full db- and integration-tier execution against real PostgreSQL (historically ~1h for the db tier per STATE.md). In particular the SC5 secret-sweep proofs touched by Task 2 (`tests/db/test_secret_redaction_e2e_full_pipeline.py`, `tests/integration/test_capability_denial_no_secret_leak.py`, `tests/integration/test_secret_redaction_e2e.py`) were only collection-checked this session (no import/fixture errors), not executed.
- **`app-int` (a separate repository, intentionally untouched) will break until a human updates it.** Its `.github/workflows/run.yml` / `resume.yml` currently pass a dispatch secret through under the env key `GITHUB_TOKEN: ${{ secrets.DISPATCH_GITHUB_TOKEN }}` — confirmed by direct inspection. That key name is irrelevant to this rename (it's a different, deliberately-separate dispatch credential, not Dark Factory's own `DARK_FACTORY_GITHUB_TOKEN`), but `app-int/DARK_FACTORY_SETUP.md` and `app-int/.env.example` both still document and assign the repo's own Dark-Factory-facing credential under the old `GITHUB_TOKEN` name — that repository secret and `.env` entry must be renamed to `DARK_FACTORY_GITHUB_TOKEN` by a human, or the next run against it will fail to authenticate (Dark Factory now reads nothing under `GITHUB_TOKEN`).
- **`.claude/CLAUDE.md` and `.planning/PROJECT.md` still carry the old spelling by design (F9).** Both describe the credential-boundary principle by naming the credential class; `CLAUDE.md` is generated/mirrored from `PROJECT.md`, which this task deliberately did not touch (editing it directly would be overwritten at the next regeneration and would drift from its source). Flagged here for whoever next regenerates those documents.
- `copilot_github_token` / `COPILOT_GITHUB_TOKEN` (a genuinely separate worker credential) is untouched throughout, confirmed by grep at every task boundary.
- No webhook-subsystem code was resurrected; nothing outside this repository was modified.

## Self-Check: PASSED

- All 5 task commits (`582ec65`, `b183c1f`, `7d6ca98`, `1763523`, `70da05e`) confirmed present in `git log --oneline --all`.
- `src/dark_factory/config/settings.py`, `tests/unit/test_redaction_dark_factory_github_token.py`, `scripts/scaffold_target_repo.py`, `docs/CONFIGURATION.md`, `README.md`, `.env.example` all confirmed present on disk.

---
*Quick task: 261031-lhn*
*Completed: 2026-11-01*
