---
status: diagnosed
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
source: [10-VERIFICATION.md]
started: 2026-09-27T16:07:52Z
updated: 2026-09-28T00:20:00Z
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
  root_cause: >
    Two serial, test-only defects (no production bug) share one upstream condition: the four
    affected integration tests (test_real_pipeline_zero_config.py, test_artifact_scope_enforcement.py,
    test_artifact_cross_clone.py, test_role_reassignment_sc2.py) copy the shipped
    .dark-factory.yaml verbatim into a throwaway git repo that cannot satisfy its
    repo-specific declarations.
    (1) quality_gate.commands: ["uv run pytest -q", "uv run ruff check ."] became executable
    in Phase 9 (commit 4a7a19e). The throwaway repo has no Python project, so
    `uv run pytest -q` there exits 5 (EXIT_NOTESTSCOLLECTED). QualityGateResult.status
    requires exit_code==0 from every command, so the gate FAILs every attempt -> QA bounces
    to DEVELOPMENT against quality_gate_iterations (cap 2), then the run ends
    quality_gate_max_iterations_exhausted. (The reported "3 bounces exhausting
    qa_developer_max_iterations: 3" is a mis-attribution: it's 2 gate bounces + 1 terminal
    failure = 3 QA-> transitions, driven by the gate counter, not the QA-verdict counter --
    the QA verdict is always PASS from the fakes.)
    (2) Latent, surfaces the instant (1) is fixed: the same shipped config sets
    publishing.create_pr: true but declares no github_owner/github_repo, so the publish
    branch fails immediately after a gate PASS (MissingGitHubCredentialError or "repository
    .github_owner is not set"), and the run still ends FAILED.
    tests/conftest.py's own `_write_config_tree` already defaults create_pr:false and
    quality_gate.commands:[] to protect ~24 db-tier tests -- the four integration tests
    copy the shipped config directly and were never covered by that mitigation. Pre-existing
    since Phase 9, not a Phase 10 regression (git log -S run_quality_gate -- runner.py shows
    one commit, 4a7a19e; the four tests were last touched one phase earlier).
    Two further reported failures are independent test-only defects, unrelated to (1)/(2):
    test_manual_check_loop04_adjacency.py asserts the adjacency reason lands on the
    RUN_FAILED payload, but production deliberately puts it on ROLE_FAILED's `error` field
    (runner.py comment states this verbatim) -- the test reads the wrong event; it is also
    the untracked throwaway STATE.md already flags as a Blocker meant to be deleted.
    test_redaction_interactions.py:306 does an over-broad `"redact(" not in runner_src`
    search; runner.py's two redact( call sites are legitimate Phase 10 GitHub-path additions
    (10-06 cb2f325, 10-03 dc4d36b) scrubbing GitHubError strings, not human-interaction
    question/answer text -- the single-mutation-path contract the test's docstring describes
    is intact.
  artifacts:
    - path: "tests/integration/test_real_pipeline_zero_config.py"
      issue: "_copy_shipped_config_into copies quality_gate.commands and publishing.create_pr:true verbatim into a throwaway repo that cannot satisfy either"
    - path: "tests/integration/test_artifact_scope_enforcement.py"
      issue: "same _copy_shipped_config_into path; also has 3 sibling negative-case tests (expected_exit=1) currently passing for the WRONG reason -- gate exhaustion, not the condition they claim to prove"
    - path: "tests/integration/test_artifact_cross_clone.py"
      issue: "own copy of the shipped config, same unmitigated quality_gate/create_pr keys"
    - path: "tests/integration/test_role_reassignment_sc2.py"
      issue: "same unmitigated quality_gate/create_pr keys"
    - path: "src/dark_factory/orchestrator/runner.py"
      issue: "gate invocation ~:1268-1278, publish branch ~:1309-1376, gate bounce ~:1395-1407 -- confirmed correct; no change needed here"
    - path: "tests/db/test_manual_check_loop04_adjacency.py"
      issue: "asserts adjacency reason on RUN_FAILED payload; production puts it on ROLE_FAILED's error field -- test reads the wrong event (STATE.md already flags this throwaway as a Blocker meant to be deleted)"
    - path: "tests/integration/test_redaction_interactions.py"
      issue: "line ~306: over-broad 'redact(' not in runner_src assertion doesn't account for the two legitimate GitHub-path redact() call sites"
  missing:
    - "Neutralize quality_gate.commands (empty list, or a minimal always-passing command) and set publishing.create_pr: false when copying the shipped config into a throwaway repo, in test_real_pipeline_zero_config.py's _copy_shipped_config_into and the equivalent copy helpers in test_artifact_scope_enforcement.py, test_artifact_cross_clone.py, and test_role_reassignment_sc2.py"
    - "Re-confirm the sibling negative-case tests in test_artifact_scope_enforcement.py that already assert expected_exit=1 (the two artifact-scope tamper cases and the no-fake-binaries-fails-visibly case) actually fail for their OWN stated reason once the gate is neutralized -- assert on the ROLE_FAILED error/event payload content, not just exit code 1"
    - "Fix or delete tests/db/test_manual_check_loop04_adjacency.py::test_a_one_role_pipeline_fails_immediately_never_bounces to read the adjacency reason from the ROLE_FAILED payload's error field (per its own docstring's stated intent), not RUN_FAILED"
    - "Narrow the tests/integration/test_redaction_interactions.py:306 assertion so it tolerates the two legitimate GitHub-path redact() call sites in runner.py while still asserting runner.py never redacts a human-interaction question/answer"
  debug_session: ".planning/debug/qa-gate-exhausts-bounces-terminates-failed.md"
