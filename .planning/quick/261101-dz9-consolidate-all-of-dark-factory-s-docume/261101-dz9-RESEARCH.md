# Quick Task 261101-dz9: Consolidate docs into README - Research

**Researched:** 2026-11-01
**Domain:** Documentation consolidation (no library/stack decisions)
**Confidence:** HIGH — every claim below was verified by reading the named file this session.

## Summary

All 5 `docs/*.md` files and `README.md` were read in full, along with
`src/dark_factory/config/settings.py` (the canonical env-var list) and
`tests/unit/test_resume_workflow_reference_doc.py` (the only test that reads
README's content). The headline finding contradicts one premise in the task
brief: **the env-var docs are NOT currently stale.** A prior quick task this
same session (`261031-lhn`, commits `582ec65` → `70da05e`) already renamed
`GITHUB_TOKEN` → `DARK_FACTORY_GITHUB_TOKEN` *and* updated `docs/CONFIGURATION.md`,
`docs/GETTING-STARTED.md`, `.env.example`, and README in the same breath. A
separate prior session (`261031-jmw`, commits `7e9a09e`/`9355e55`) already
removed webhook/dispatch credentials from `Settings` and rewrote the docs to
describe the single surviving resume path. Cross-checked field-by-field
against `Settings`, all three docs' env-var tables are internally consistent
and complete today (11/11 fields each, no extras, no omissions).

**Primary recommendation:** This is a pure restructuring/consolidation task,
not a correction task. Most of README's own content is already accurate and
usage-focused — the work is (1) pulling the genuinely non-duplicated
reference tables out of the three "still mostly accurate" docs
(CONFIGURATION.md, GETTING-STARTED.md) into README, (2) cutting
ARCHITECTURE.md almost entirely (it's internals, not user-facing), (3)
condensing DEVELOPMENT.md + TESTING.md into one short contributor section,
and (4) fixing the one stale cross-reference `.env.example` has to
`docs/CONFIGURATION.md` once docs/ is deleted.

## Content Migration Map

### docs/ARCHITECTURE.md → mostly CUT

Pure internals: component diagram (mermaid), 9-step data-flow walkthrough
naming internal modules (`persistence/mutations.py`, `orchestrator/lease.py`
etc.), a "key abstractions" table of internal functions/files, the
`src/dark_factory/` directory-rationale tree, and a 5-table breakdown of the
Postgres schema (`runs`, `role_executions`, `run_events`,
`human_interactions`, `artifacts`). None of this is something a developer
*adopting* Dark Factory into their own repo needs — it's "how Dark Factory
is built," not "how to configure/run Dark Factory." README's own pitch
paragraph and "Pause a run for a human" section already give a user
everything they need about the pipeline shape and the resume model at the
right altitude. **Recommendation: cut entirely.** (No discretion note in
CONTEXT.md singles this file out for partial preservation the way
DEVELOPMENT.md/TESTING.md are — this falls under the general "cut historical/
internals" decision.)

### docs/CONFIGURATION.md → mostly FOLD IN, some CUT

| Content | Disposition | Target README section |
|---|---|---|
| Two-tier config framing paragraph (infra `.env` vs. repo `.dark-factory.yaml`) | Fold (short) | Top of "Configuration reference" |
| Full env-var tables (infra + optional worker tables, 11 fields total) | **Fold in full** — README today only documents 4 of 11 fields in prose | New "Environment variables" section (see below) |
| "Why not `GITHUB_TOKEN`?" explanation | Already in README (condensed) | No change needed — README's version is sufficient |
| `.dark-factory.yaml` full key table (`version`, `repository.*`, `workflow.roles`, `roles_dir`, `quality_gate.commands`, `retry.*`, `publishing.create_pr`) | Fold — README today has only prose, no table | Extend "Configuration reference" |
| `.dark-factory/roles/*.yaml` full key table + "Shipped roles" table | Fold (useful reference for hand-authoring/verifying scaffold output) | Extend "Configuration reference" |
| `Settings` validator behavior (lease coherence, worker-timeout positivity, log-level validation) | Fold as 2-3 bullet "fails fast on" note | Environment variables section |
| Secret-handling internals (`known_secret_values()`, `SecretStr` walk) | Cut (internals, not actionable for a user) | — |
| Per-environment-overrides / `.env` precedence note | Cut or 1-line footnote | — |
| Config file format summary table (file/format/location/purpose) | Optional fold (cheap, useful at-a-glance) | Configuration reference (discretion) |

### docs/GETTING-STARTED.md → mostly FOLD IN (narrower bits), rest CUT (duplicate)

| Content | Disposition | Target README section |
|---|---|---|
| Install / scaffold / `.env` / migrate / first-run steps | **Cut — already duplicated** in README's "Install it into your own repository" | — |
| Prerequisites list (worker-runtime CLI + fake-worker callout) | Fold 1-2 lines into README's existing Prerequisites | Prerequisites |
| Scaffold script's full flag table (`--target`, `--github-owner/repo`, `--base-branch`, `--worker[-ba/-architecture/-development/-qa]`, `--quality-gate-command`, `--install-source`, `--force`, `--yes`) | **Fold** — CONTEXT.md decision #3 names the scaffold script as the fast path; README currently shows only 2 example invocations with no flag reference | New subsection under "Install it into your own repository" or "Configuration reference" |
| "Common setup issues" (6 items: alembic/pooled-endpoint, lease-heartbeat validator error, missing worker binary, `MissingWorkerCredentialError`, scaffold "instruction source not found", scaffold/alembic "can't find files") | Fold as a short "Troubleshooting" section — genuinely useful, low overlap with README | New "Troubleshooting" section near the end |
| First-run walkthrough with `dark-factory run text:"..."` output | Cut — README already has the identical transcript | — |
| Fake-worker / `DARK_FACTORY_FAKE_SCRIPT` zero-credential mention | Cut — README's "Pause a run for a human" section already has the fuller worked example | — |

### docs/DEVELOPMENT.md → condensed CONTRIBUTOR note only

Confirmed purely contributor-facing by its own opening line ("This is the
contributor-facing guide to working *on* Dark Factory itself... not about
using Dark Factory... for that, see README.md"). Per CONTEXT.md decision,
fold only a condensed note, combined with TESTING.md's condensed note, into
one short "Contributing" section:
- `git clone` + `uv sync --all-extras --dev` (one-time setup)
- The quality-gate command list (ruff check, ruff format --check, mypy
  --strict, pytest tiers) — table form is fine, condensed
- One line on the `db`/`integration` tiers needing real PostgreSQL 17 via a
  probe ladder (testcontainers → pytest-postgresql → `DARK_FACTORY_TEST_DATABASE_URL`)
- One line: commit convention is Conventional Commits (`type(scope): subject`)
- Cut: PR-process detail, "no CONTRIBUTING.md" disclaimers, branch-naming
  commentary about `dark-factory/run-<uuid>` working branches (interesting
  but not load-bearing for a contributor getting started)

### docs/TESTING.md → condensed CONTRIBUTOR note only (per locked decision)

Fold only: pytest is the framework, the four markers (`unit`/`db`/
`integration`/`contract`) and one line each on what they require, `uv run
pytest` / `-m unit` / `-m db` as the commands to know. Cut: fixture-by-name
documentation, the full CI job breakdown, the `QUAL-01` scenario-to-module
mapping explanation, "no coverage tool" commentary, directory-layout table
detail beyond naming the four marker dirs.

## Environment Variable Audit (verified against `src/dark_factory/config/settings.py`)

The `Settings` class (read in full, lines 102-112) declares exactly these 11 fields — this is the only authoritative list:

```
database_url: SecretStr                        # required, no default
database_url_direct: SecretStr                  # required, no default
dark_factory_github_token: SecretStr | None = None
log_level: str = "INFO"
lease_ttl_seconds: int = 900
lease_heartbeat_seconds: int = 300
anthropic_api_key: SecretStr | None = None
copilot_github_token: SecretStr | None = None
copilot_model: str | None = None
claude_model: str | None = None
worker_timeout_seconds: int = 1800
```

No webhook, dispatch, or signing-secret field exists on `Settings` — confirmed absent (git history shows it was removed in commit `7e9a09e`, "remove webhook credentials and client methods, rewire Settings consumers"). The `src/dark_factory/webhook/` directory still exists on disk but contains only a stale `__pycache__` (no `.py` source files) — the webhook/dispatch *feature* is gone, not just its credentials, consistent with CONTEXT.md's framing that "no webhook receiver exists" and resume via `resume.yml` is the only path.

| Doc | Env vars documented | Matches `Settings`? |
|---|---|---|
| `docs/CONFIGURATION.md` | All 11 (6 in main table + 5 in "additional settings" table) | ✅ Exact match, no stale/extra entries |
| `docs/GETTING-STARTED.md` | All 11 (one combined table) | ✅ Exact match |
| `.env.example` | 5 documented with placeholder values (`DATABASE_URL`, `DATABASE_URL_DIRECT`, `LOG_LEVEL`, `LEASE_TTL_SECONDS`, `LEASE_HEARTBEAT_SECONDS`, `DARK_FACTORY_GITHUB_TOKEN`) — worker-credential vars intentionally omitted (scaffold adds them conditionally per assigned worker, per GETTING-STARTED.md's own framing) | ✅ Consistent, but line 45 comment still says "See docs/CONFIGURATION.md" — **will dangle once docs/ is deleted; needs a one-line fix to point at README instead** |
| `README.md` (current) | Only 4 named explicitly in prose (`DATABASE_URL`, `DATABASE_URL_DIRECT`, `DARK_FACTORY_GITHUB_TOKEN`, generic "a worker-runtime credential") + the two lease knobs in a table | ⚠️ **Incomplete, not stale** — omits `ANTHROPIC_API_KEY`/`COPILOT_GITHUB_TOKEN` as named vars, and omits `COPILOT_MODEL`/`CLAUDE_MODEL`/`WORKER_TIMEOUT_SECONDS`/`LOG_LEVEL` entirely. Since docs/CONFIGURATION.md and docs/GETTING-STARTED.md (the only places with the *complete* list) are being deleted, the consolidated README **must** absorb the full 11-field table or this information is lost from the repo entirely. |

**Correction to the task brief's premise:** the research context's claim that "the docs/*.md files were NOT updated for these changes and are likely stale" does not hold — verified by reading both the files and the git log; they were updated in the same session, before this task started. No stale env-var claim was found anywhere in the 5 docs files.

## Test-Guarded README Content (must not break)

Only one test reads README's actual content: `tests/unit/test_resume_workflow_reference_doc.py`. A repo-wide grep for `README` across `tests/` found 6 other files, all using the literal string `"README.md"` as a throwaway filename inside synthetic test git repos (`tests/unit/test_context_builder.py`, `test_git_lifecycle.py`, `tests/integration/test_worktree_lifecycle.py`, `tests/support/git_repo.py`, `tests/db/test_wip_commit_recovery.py`) or as a prose mention inside an acceptance-criteria string (`tests/integration/test_phase4_acceptance.py:149`) — none of these read Dark Factory's own `README.md`.

`test_resume_workflow_reference_doc.py` guards, by exact string/structure:

1. **Sentinel pair** `<!-- resume-workflow-reference: begin -->` / `<!-- resume-workflow-reference: end -->` — must appear **exactly once each**, with a fenced ` ```yaml ` block immediately inside them. The extracted inner text is parsed with `yaml.safe_load` and asserted to:
   - parse as a mapping
   - declare a `workflow_dispatch` trigger with a required `run_id` input and an optional `answer` input (type `string`)
   - contain exactly one step whose `run:` text contains `dark-factory resume`, and whose combined `run`+`env` text contains the literal substring `inputs.run_id`
   - carry **zero** `if:` keys anywhere in any job or step
   - declare `permissions` equal to **exactly** `{contents: write, issues: write, pull-requests: write}` (whole-mapping equality, not containment — adding or removing a scope breaks this)
   - contain a line with the substring `Install the worker runtime` that appears **before** the line invoking `dark-factory resume`
   - **Conclusion: the entire `resume.yml` YAML block (lines 445-503 of current README.md) must move byte-identically if the section is relocated.** Content outside the fenced block (prose) is free to change.

2. **Heading pair used as text-extraction boundaries** (not sentinel comments, but equally load-bearing): the module-level constants `_CI_HANDOFF_SECTION_HEADING = "## Finish a run in CI — the local → CI handoff"` and `_CI_HANDOFF_SECTION_NEXT_HEADING = "## Configuration reference"` are used to slice out a section of README via plain string `.partition()`. Within that sliced section, parametrized tests assert:
   - every entry in `LIVE_RUNTIMES` (`tests/support/live_runtime.py`) has its `binary` name present somewhere in the section (currently: `claude`, `copilot`, `hermes`)
   - each runtime's credential env-var name appears **on the specific table row naming that worker** (not just anywhere in the section) — this is the worker-runtime table currently at README lines 585-589 (`claude-code`/`claude`/`ANTHROPIC_API_KEY`, `copilot`/`copilot`/`COPILOT_GITHUB_TOKEN`, `hermes`/`hermes`/`ANTHROPIC_API_KEY`)
   - **Conclusion:** if the planner renames or removes either heading, or moves the worker-runtime table out of the section they bound, this test must be updated in the same change (it is not a sentinel-protected block, but it is a structural dependency on exact heading text + table placement). If the plan keeps a "Finish a run in CI" section immediately followed by a "Configuration reference" section with the worker table inside it, no test edit is needed.

No other heading, section, or table in README is read by any test.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ARCHITECTURE.md's content has zero user-facing value and should be cut entirely (vs. folding a trimmed "how it works" paragraph) | Content Migration Map | Low — CONTEXT.md's Claude's-Discretion scope covers section ordering/content depth; worst case the planner adds back one short paragraph, no rework needed |
| A2 | The `.dark-factory.yaml` and role-YAML full key tables should be folded in as full tables rather than left to the scaffold script + condensed prose | Content Migration Map | Low — CONTEXT.md decision #3 explicitly leaves "how much... gets folded in verbatim vs. rewritten" to discretion |

All other claims in this document were verified directly against source files read this session (`Settings`, the three docs, README, the guard test, `.env.example`, and `git log`) and are tagged `[VERIFIED]` by construction of this research pass — no package-legitimacy or external-library research applies to this task.

## Open Questions

1. **Should the full `.dark-factory/roles/*.yaml` key table + "Shipped roles" table move into README, or should README just point at the scaffold's generated output as the reference?**
   - What we know: CONTEXT.md names the scaffold script as "the fast path," implying hand-authoring detail is secondary.
   - What's unclear: whether a user who wants to *edit* a scaffolded role YAML needs the full key table in README, or can rely on inline comments the scaffold writes.
   - Recommendation: fold the table in condensed form (it's ~10 rows, cheap) since docs/CONFIGURATION.md — the only other place it lives — is being deleted.

2. **Exact section order/headings** — left entirely to planner discretion per CONTEXT.md, with the one hard constraint that "Finish a run in CI" and "Configuration reference" headings (or equivalents feeding the same text-slice test) stay adjacent in that order, or the guard test needs a matching edit.

## Sources

### Primary (HIGH confidence — read in full this session)
- `src/dark_factory/config/settings.py` — authoritative 11-field env var list, validators
- `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`, `docs/DEVELOPMENT.md`, `docs/GETTING-STARTED.md`, `docs/TESTING.md` — full content read
- `README.md` — full current content read
- `tests/unit/test_resume_workflow_reference_doc.py` — full content read
- `.env.example` — full content read
- `git log --oneline` on `docs/CONFIGURATION.md`, `docs/GETTING-STARTED.md`, `src/dark_factory/config/settings.py` — confirmed doc/settings update ordering this session
- `.planning/quick/261101-dz9-.../261101-dz9-CONTEXT.md` — locked decisions

## Metadata

**Confidence breakdown:**
- Content migration mapping: HIGH — every source file read in full
- Env var audit: HIGH — direct field-by-field comparison against `Settings` source
- Test-guard inventory: HIGH — guard test read in full; repo-wide grep confirmed no other README-content-reading test exists

**Research date:** 2026-11-01
**Valid until:** N/A — this research is tied to the current commit state (`70da05e`); re-verify settings.py/docs if more commits land before planning executes.
