---
status: testing
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
source: [10-VERIFICATION.md]
started: 2026-09-27T16:07:52Z
updated: 2026-09-27T16:07:52Z
---

## Current Test

number: 1
name: Run a full, unrestricted `uv run pytest -q` (every tier — unit, contract, db, integration, no marker filter) against a real reachable PostgreSQL instance
expected: |
  All 1169 collected tests pass, including the 195 db-tier and 169 integration-tier tests
  that were only ever run in targeted subsets across plans 10-01/10-02/10-03/10-04/10-06 and
  this verification pass, never as one unrestricted sweep.
awaiting: user response

## Tests

### 1. Full unrestricted test suite against real PostgreSQL
expected: All 1169 collected tests pass (unit, contract, db, integration — no marker filter). No PostgreSQL instance (Docker, local initdb, or DARK_FACTORY_TEST_DATABASE_URL) was reachable in the verification sandbox; a throwaway remote Neon connection was used for targeted db-tier subsets across this phase's plans, but a full unrestricted sweep was never attempted successfully (a prior attempt in plan 10-06 was killed after ~1.5 hours against remote-Neon round-trip latency).
result: [pending]

### 2. Live GitHub API + real webhook end-to-end smoke test
expected: |
  Configure a real `GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET`, point a real repository's
  webhook at a running `dark_factory.webhook.app:app` instance, and drive one real GitHub
  issue through the full loop: `dark-factory run github:<n>` -> a role asks a clarifying
  question -> the question appears as a comment on the real issue -> a human replies on the
  issue -> the run resumes -> QA/gate PASS -> exactly one real pull request opens with the
  correct title/base/body. Every truth in this phase was proven against `FakeGitHubClient`,
  never GitHub's live API or a real inbound webhook delivery.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
