---
phase: quick
plan: 261029-od8
subsystem: tooling
tags: [scaffold, developer-tool, config-generation, documentation]
status: complete
dependency-graph:
  requires: []
  provides:
    - scripts/scaffold_target_repo.py
  affects:
    - README.md
tech-stack:
  added: []
  patterns:
    - "text-template substitution on {{TOKEN}} markers, never yaml.dump, to preserve explanatory YAML comments"
    - "instruction prose read at runtime from this repo's own .dark-factory/instructions/, never duplicated into the script"
key-files:
  created:
    - scripts/scaffold_target_repo.py
  modified:
    - README.md
decisions:
  - "Role YAML templates modelled on app-int's clean generic files, not this repo's own phase-annotated role YAMLs (DD-4)"
  - "Credential env vars are the union over the four resolved workers, built from one module-level WORKER_CREDENTIAL_ENV_VAR dict so .env.example and resume.yml cannot diverge (DD-5)"
  - "Skip-unless-force (DD-7): every destination file is left untouched unless --force is passed, proven by whole-tree checksum equality across a second non-force run"
  - "Script lives outside src/dark_factory/ and pyproject.toml with no CLI subcommand registration (DD-8)"
metrics:
  duration: "~35min"
  completed: "2026-10-29"
actuals:
  tokens: 6500
  tasks: 3
  commits: 3
plan_head_before: 76b8407b167b6402d8375cb0e757e151ffa3bce9
---

# Quick Task 261029-od8: Standalone scaffold script for target repos Summary

Added `scripts/scaffold_target_repo.py`, a standalone stdlib+PyYAML generator that writes a complete twelve-file Dark Factory configuration tree (`.dark-factory.yaml`, four role YAMLs, four instruction files, `.env.example`, `.github/workflows/resume.yml`, `.gitignore`) into any target repository, and documented it in README's deployment-model section as the stopgap for the hand-authoring steps the README previously deferred entirely.

## What Was Built

**Task 1 — default four-role scaffold.** `scripts/scaffold_target_repo.py` renders the twelve output files via plain string-template substitution on `{{TOKEN}}` markers (never `yaml.dump`, which would silently drop the templates' explanatory YAML comments). The four role YAML templates and the `.env.example`/`resume.yml`/`.gitignore` templates are modelled verbatim on `app-int`'s clean, generic versions (DD-4) rather than this repository's own phase-annotated role YAMLs. The four instruction files are read at runtime from this repository's own `.dark-factory/instructions/` (DD-1) — never duplicated into the script — with a generated "Write-scope enforcement" section appended to each, naming that role's actual resolved write-scope patterns (DD-2) so the copied prose and the enforcement the same run's role YAML will apply can never disagree. `--target` is resolved exactly once with `expanduser().resolve()`, and every output path is that resolved root joined with one of twelve fixed relative-path constants (T-OD8-02) — never a caller-supplied sub-path. After writing, every emitted YAML file is parse-checked with `yaml.safe_load`. Proven end-to-end: a fresh invocation against an empty directory produces all twelve files, and the real `dark_factory.config.loader.load_effective_config` accepts the result without raising — which transitively proves every `extra="forbid"` key set, every worker/action/tool name, and every write-scope pattern resolves correctly.

**Task 2 — parameterization, prompts, no-clobber guard.** Extended the same script with `--base-branch`, `--worker` plus four per-role overrides (`--worker-ba`, `--worker-architecture`, `--worker-development`, `--worker-qa`), repeatable `--quality-gate-command` (defaulting to this repo's own `uv run pytest -q` / `uv run ruff check .` pair when omitted), `--install-source`, `--force`, and `--yes`. Worker names are validated against the closed three-value legal set (`claude-code`, `copilot`, `hermes` — DD-6, deliberately excluding the registry's `fake`); an unrecognised name exits non-zero naming all three legal values before any file is written. Credential env vars are derived from one module-level `WORKER_CREDENTIAL_ENV_VAR` dict (`claude-code`/`hermes` → `ANTHROPIC_API_KEY`, `copilot` → `COPILOT_GITHUB_TOKEN`) read by both the `.env.example` renderer and the `resume.yml` renderer, so the two sites cannot diverge (DD-5). A missing `--github-owner`/`--github-repo` prompts interactively when stdin is a TTY and `--yes` is absent, and exits non-zero naming the missing flag otherwise — every automated invocation stays non-interactive. DD-7's skip-unless-`--force` guard is implemented in `write_output_file()`: an existing destination is left untouched (`skipped (exists)`) unless `--force` is passed (`overwritten`); a per-file status line is printed plus a closing note naming `--force` when anything was skipped. An existing `.gitignore` specifically gets its own gap report naming which template entries it is missing, rather than being silently skipped. Proven: per-role overrides land in the right role YAMLs and pull the right credential into both `.env.example` and `resume.yml`; a custom base branch and quality-gate command land in `.dark-factory.yaml` and still load through `load_effective_config`; a second run without `--force` leaves the whole tree byte-identical (checksum equality) including a manually-added `.gitignore` marker line, while `--force` replaces everything and removes the marker; an unrecognised worker name exits non-zero.

**Task 3 — README documentation.** Replaced the standalone deferral sentence ("There is currently no `dark-factory init` command...") with a new "Scaffolding steps 2 and 3" subsection that restates the `dark-factory init` deferral is still deliberate and on the record, names the script, lists what it writes, shows two invocations (the default case, and a per-role worker override with a custom quality-gate command), and states plainly that the script is a developer tool outside the shipped package — not a `dark-factory` subcommand, not installed by `pip install dark-factory`, and therefore the one place the deployment model's "you do not clone Dark Factory's own repository" premise does not hold. Also notes the no-clobber behavior and that instruction files carry a generated write-scope section. The `resume-workflow-reference` sentinel block and its surrounding fence were left untouched — verified by exact hash match (`d2a767165eb7ef03cdd8248bfa40b754e6a4caf3`) before and after the edit.

## Verification

- `uv run ruff check scripts/` and `uv run ruff format --check scripts/` — clean.
- `uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q` — 13 passed.
- End-to-end smoke: fresh target directory → all twelve files created → `load_effective_config` accepts the result without raising.
- Whole-tree checksum equality proven across a second non-`--force` run; `--force` proven to overwrite and remove a manually-added marker.
- `git status --porcelain` confined to `scripts/scaffold_target_repo.py` and `README.md`.
- `grep -rqi 'scaffold_target_repo' src/dark_factory/ pyproject.toml` — no match (not wired into the package or registered as an entry point).

## Deviations from Plan

None — plan executed exactly as written across all three tasks.

## Self-Check: PASSED

- `scripts/scaffold_target_repo.py` — FOUND
- Commit `3269c97` (Task 1) — FOUND in `git log --oneline`
- Commit `223ef00` (Task 2) — FOUND in `git log --oneline`
- Commit `93e5c16` (Task 3) — FOUND in `git log --oneline`
- README.md `resume-workflow-reference` block hash — matches `d2a767165eb7ef03cdd8248bfa40b754e6a4caf3` (unchanged)
