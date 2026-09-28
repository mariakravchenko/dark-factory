---
status: testing
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
source: [10-VERIFICATION.md]
started: 2026-09-28T12:00:00Z
updated: 2026-09-28T12:00:00Z
---

## Current Test

number: 1
name: Full unrestricted test suite against real PostgreSQL
expected: |
  All currently-collected tests pass, including the four real-CLI-subprocess integration
  tests (test_real_pipeline_zero_config, test_artifact_scope_enforcement,
  test_artifact_cross_clone, test_role_reassignment_sc2) that previously bounced
  QA<->DEVELOPMENT and terminated FAILED (G-10-1), now reaching COMPLETED via the
  neutralized shipped-config harness; the three negative controls in those same modules
  failing for their own stated reason (persisted role-execution error), not gate
  exhaustion; the promoted tests/db/test_loop04_adjacency.py; and the narrowed
  tests/integration/test_redaction_interactions.py guard.
awaiting: user response

## Tests

### 1. Full unrestricted test suite against real PostgreSQL
expected: |
  All currently-collected tests pass, including the four real-CLI-subprocess integration
  tests (test_real_pipeline_zero_config, test_artifact_scope_enforcement,
  test_artifact_cross_clone, test_role_reassignment_sc2) that previously bounced
  QA<->DEVELOPMENT and terminated FAILED (G-10-1), now reaching COMPLETED via the
  neutralized shipped-config harness; the three negative controls in those same modules
  failing for their own stated reason (persisted role-execution error), not gate
  exhaustion; the promoted tests/db/test_loop04_adjacency.py; and the narrowed
  tests/integration/test_redaction_interactions.py guard.
result: [pending]

### 2. Live GitHub API + real webhook end-to-end smoke test
expected: |
  Configure a real `GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET`, point a real repository's
  webhook at a running `dark_factory.webhook.app:app` instance, and drive one real GitHub
  issue through the full loop: `dark-factory run github:<n>` -> a role asks a clarifying
  question -> the question appears as a comment on the real issue -> a human replies on the
  issue -> the run resumes -> QA/gate PASS -> exactly one real pull request opens with the
  correct title/base/body. The full GIT-03/GIT-04/GIT-05/GIT-06 loop works end to end
  against GitHub's real API and a real inbound webhook delivery, not FakeGitHubClient.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

None currently open. G-10-1 (test-harness defect — shipped `.dark-factory.yaml` copied
verbatim into throwaway repos that couldn't satisfy its repo-specific `quality_gate.commands`
and `publishing.create_pr` declarations, plus two independent misdirected test assertions)
was diagnosed at `.planning/debug/qa-gate-exhausts-bounces-terminates-failed.md`, closed by
gap-closure plans 10-07 and 10-08, and independently confirmed closed by this verification
pass (808/808 unit+contract tests passing, up from 805/805; production code untouched). Full
history preserved in git (prior revisions of this file) and in 10-VERIFICATION.md's
`re_verification.gaps_closed`.
