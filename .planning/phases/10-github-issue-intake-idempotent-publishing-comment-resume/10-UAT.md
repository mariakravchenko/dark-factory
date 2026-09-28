---
status: partial
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
source: [10-VERIFICATION.md]
started: 2026-09-27T16:07:52Z
updated: 2026-09-28T00:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Full unrestricted test suite against real PostgreSQL
expected: All 1169 collected tests pass (unit, contract, db, integration — no marker filter). No PostgreSQL instance (Docker, local initdb, or DARK_FACTORY_TEST_DATABASE_URL) was reachable in the verification sandbox; a throwaway remote Neon connection was used for targeted db-tier subsets across this phase's plans, but a full unrestricted sweep was never attempted successfully (a prior attempt in plan 10-06 was killed after ~1.5 hours against remote-Neon round-trip latency).
result: issue
reported: "6 failed, 1162 passed, 1 skipped, 1 warning in 5508.36s (1:31:48) against real Neon Postgres. Failures: tests/db/test_manual_check_loop04_adjacency.py::test_a_one_role_pipeline_fails_immediately_never_bounces (RUN_FAILED payload does not name the adjacency reason: {'role': 'QA'}); tests/integration/test_artifact_cross_clone.py::test_fresh_clone_of_the_working_branch_carries_every_artifact_byte (exit=1); tests/integration/test_artifact_scope_enforcement.py::test_the_identical_shipped_config_with_no_tampering_completes_with_all_artifacts (exit=1 expected=0, run reached terminal FAILED via QA->DEVELOPMENT bounces then QA->FAILED at attempt 3); tests/integration/test_real_pipeline_zero_config.py::test_real_dark_factory_yaml_reaches_completed_with_no_explicit_script (exit=1, same QA->FAILED pattern); tests/integration/test_redaction_interactions.py::test_the_interaction_writer_scrubs_at_the_one_mutation_path_call_site (assert 'redact(' not in runner_src fails -- runner.py now contains a 'redact(' call site); tests/integration/test_role_reassignment_sc2.py::test_reassigned_roles_reach_completed_identically_to_all_fake (exit=1, same QA->FAILED pattern)."
severity: blocker

### 2. Live GitHub API + real webhook end-to-end smoke test
expected: |
  Configure a real `GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET`, point a real repository's
  webhook at a running `dark_factory.webhook.app:app` instance, and drive one real GitHub
  issue through the full loop: `dark-factory run github:<n>` -> a role asks a clarifying
  question -> the question appears as a comment on the real issue -> a human replies on the
  issue -> the run resumes -> QA/gate PASS -> exactly one real pull request opens with the
  correct title/base/body. Every truth in this phase was proven against `FakeGitHubClient`,
  never GitHub's live API or a real inbound webhook delivery.
result: blocked
blocked_by: other
reason: "Deferred pending G-10-1: the real-CLI-subprocess pipeline (test_real_pipeline_zero_config, test_artifact_scope_enforcement, test_artifact_cross_clone, test_role_reassignment_sc2) currently bounces QA<->DEVELOPMENT 3 times and terminates FAILED before ever reaching PUBLISHING, even with fake workers and no GitHub involved. A live GitHub run would hit the same wall before any PR could be created, so it was deferred until the QA/gate bug is diagnosed and fixed."

## Summary

total: 2
passed: 0
issues: 1
pending: 0
skipped: 0
blocked: 1

## Gaps

- gap_id: G-10-1
  truth: "All 1169 collected tests pass (unit, contract, db, integration -- no marker filter) in a full unrestricted sweep against real PostgreSQL."
  status: failed
  reason: "User reported: 6 failed, 1162 passed, 1 skipped, 1 warning in 5508.36s (1:31:48). Failures span an adjacency-reason assertion in test_manual_check_loop04_adjacency, four end-to-end CLI-subprocess integration tests that now exit 1 with the run reaching terminal FAILED after QA bounces to DEVELOPMENT three times then QA->FAILED, and a redaction call-site assertion in test_redaction_interactions expecting no 'redact(' in runner.py's source but finding one."
  severity: blocker
  test: 1
  artifacts: []
  missing: []
