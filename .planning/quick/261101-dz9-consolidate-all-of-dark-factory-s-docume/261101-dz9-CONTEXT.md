# Quick Task 261101-dz9: Consolidate all of dark-factory's documentation into a single README.md - Context

**Gathered:** 2026-11-01
**Status:** Ready for planning

<domain>
## Task Boundary

Consolidate all of dark-factory's documentation into a single README.md and delete the docs/ directory entirely (docs/ARCHITECTURE.md, docs/CONFIGURATION.md, docs/DEVELOPMENT.md, docs/GETTING-STARTED.md, docs/TESTING.md). Reposition README's framing around what the tool actually is: a workflow-automation tool that helps a developer build and run an automated engineering pipeline (BA -> Architect -> Developer -> QA -> Quality Gate -> PR) against their OWN repository, driven from either a local CLI invocation or GitHub Actions.

The README must cover, in order: (1) what the tool is and why you'd use it (the pitch), (2) how to install it as a dependency in your own repo (pip install from the dark-factory git URL), (3) how to configure it for your repo -- .dark-factory.yaml, role YAMLs, instruction files (reference scripts/scaffold_target_repo.py as the fast path), (4) the required environment variables / secrets in full, verified against src/dark_factory/config/settings.py, (5) running it via GitHub Actions -- the run.yml/resume.yml reference workflows (preserve README's existing sentinel-guarded reference blocks byte-identically; test_resume_workflow_reference_doc.py guards them), (6) the full resume flow including the WAITING_HUMAN clarification-comment pause and the resume.yml answer input -- the only resume path now, proven live this session (no webhook receiver exists).

</domain>

<decisions>
## Implementation Decisions

### Historical content (phase-by-phase walkthroughs, decision history)
- Cut entirely. The README becomes purely usage-focused: pitch + install + configure + required env vars + CLI + GitHub Actions + resume flow. Development history/decision records belong in git log and .planning/ archives, not a README someone reads to adopt the tool.

### docs/TESTING.md fate
- Keep a condensed contributor section in the README (not a full tier-by-tier breakdown) — enough for someone who wants to contribute to dark-factory itself to run its test suite, but not the detailed marker/fixture documentation currently in TESTING.md.

### Claude's Discretion
- Exact section ordering/headings within the usage-focused structure, as long as the 6 numbered topics above are covered in roughly that order.
- How much of docs/ARCHITECTURE.md's and docs/CONFIGURATION.md's non-historical, still-accurate reference content (e.g. concrete config schema details, env var descriptions) gets folded in verbatim vs. rewritten — fold in whatever is accurate and still relevant to a *user* (not a dark-factory contributor), verified against current source.
- Whether docs/DEVELOPMENT.md has any user-relevant (non-contributor) content worth preserving — read it fully; if it's purely contributor-facing like TESTING.md, fold only a condensed contributor note, not full content.

</decisions>

<specifics>
## Specific Ideas

No specific wording requirements — the user's request was structural: "update docs, remove all and keep only readme, we describe that it is tool to help to develop automated workflow and so on and then describe how to configure on your repo, ci + required env."

</specifics>

<canonical_refs>
## Canonical References

- src/dark_factory/config/settings.py — single source of truth for required env vars (several changed this session: webhook/dispatch credentials removed, GITHUB_TOKEN renamed to DARK_FACTORY_GITHUB_TOKEN).
- scripts/scaffold_target_repo.py — the fast path for generating .dark-factory.yaml / role YAMLs / instructions / workflows in a target repo.
- tests/unit/test_resume_workflow_reference_doc.py — guards README's sentinel-bracketed run.yml/resume.yml reference blocks; must not break.
- The 5 docs/*.md files themselves — read fully before deciding what survives.

</canonical_refs>
