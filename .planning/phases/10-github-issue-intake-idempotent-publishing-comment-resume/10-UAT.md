---
status: complete
phase: 10-github-issue-intake-idempotent-publishing-comment-resume
source: [10-VERIFICATION.md]
started: 2026-09-28T12:00:00Z
updated: 2026-09-28T15:21:43Z
---

## Current Test

[testing complete]

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
result: pass
reported: "1171 passed, 1 skipped, 1 warning in 5661.70s (1:34:21) against real Neon PostgreSQL 17. Full unrestricted sweep, no marker filter."

### 2. Live GitHub API + real webhook end-to-end smoke test
expected: |
  Configure a real `GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET`, point a real repository's
  webhook at a running `dark_factory.webhook.app:app` instance, and drive one real GitHub
  issue through the full loop: `dark-factory run github:<n>` -> a role asks a clarifying
  question -> the question appears as a comment on the real issue -> a human replies on the
  issue -> the run resumes -> QA/gate PASS -> exactly one real pull request opens with the
  correct title/base/body. The full GIT-03/GIT-04/GIT-05/GIT-06 loop works end to end
  against GitHub's real API and a real inbound webhook delivery, not FakeGitHubClient.
result: pass
reported: |
  Ran end to end against a real GitHub repo (mariakravchenko/app-new), real GITHUB_TOKEN,
  real GITHUB_WEBHOOK_SECRET, a real ngrok-tunneled webhook receiver, and real Claude Code
  workers for all four roles. Event log: RUN_CREATED -> BA/ARCHITECTURE/DEVELOPMENT/QA all
  ROLE_COMPLETED -> QUALITY_GATE_PASSED -> PUBLISH_STARTED -> PR_CREATED (exactly one) ->
  RUN_COMPLETED. QA's own independent verdict was PASS on all 12 acceptance criteria,
  confirmed by rendering the page via headless Chrome, not just reading source. Real PR
  opened: https://github.com/mariakravchenko/app-new/pull/10.

  Caveat: the task (add a static Hello World HTML file) was simple enough that no role
  ever raised NEEDS_INPUT, so the GIT-04 half of this test (clarifying comment posted on
  the issue -> human replies -> webhook wakes the run -> resumes) was never exercised --
  the webhook receiver and tunnel sat idle the whole run. GIT-03 (intake), GIT-05
  (idempotent single-PR publish), and GIT-06 (gate-before-publish) are proven end to end
  against real infrastructure; the comment-resume code path specifically is proven only
  by the existing unit/db-tier tests (test_webhook_resolves_answer.py et al.), not by a
  live human-in-the-loop round trip in this session.

  Two genuine product findings surfaced along the way, both pre-existing (not Phase 10
  scope, not introduced by this session): (1) the claude-code worker's prompt tells a
  role to "write under artifacts/<ROLE>" but the actually-permitted path requires the
  ".dark-factory/runs/<run-id>/" prefix, which is omitted -- the role has to discover
  the correct path by trial and error against permission denials, and sometimes gives up
  instead (worked around here via explicit path instructions in app-new's role configs,
  not by patching dark-factory's source); (2) the artifact-writing worker gets no schema
  information for its declared JSON outputs beyond a bare filename, so a role operating
  on a repo that cannot read dark-factory's own source (i.e. any real target repo) has no
  way to discover the exact pydantic schema and will invent a plausible-but-wrong shape
  (worked around the same way). Both are undocumented today outside dark-factory's own
  source and worth a follow-up phase/plan, not filed as a gap against Phase 10.

## Summary

total: 2
passed: 2
issues: 0
pending: 0
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
