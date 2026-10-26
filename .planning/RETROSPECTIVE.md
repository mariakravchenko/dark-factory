# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-10-26
**Phases:** 12 | **Plans:** 76 | **Tasks:** 170

### What Was Built
- A durable, crash-safe orchestrator over Neon PostgreSQL — any process on any machine resumes a run from persisted state alone, proven adversarially (killed processes, lease races, crash-injected transactions).
- A configuration-driven four-role pipeline (BA → Architect → Developer → QA) handing off through durable, schema-validated artifacts, running unchanged across three real worker runtimes (Claude Code, Copilot, Hermes) behind one `CodingWorker` contract.
- An independent quality gate and bounded QA/gate feedback loops that trust exit codes and machine JSON, never agent prose.
- Full GitHub lifecycle (issue intake, idempotent PR publishing, clarification-comment resume, webhook dispatch) and an observability/audit surface (`status`, `runs`, `events`, `artifacts`) with secret redaction proven clean across every persisted sink.
- 224 test files covering unit, contract, db, and integration tiers; CI now runs the credential-free subset of every tier.

### What Worked
- The debug-session format (hypothesis → falsification test → AND-gate analysis → fix-acceptance guardrail with mutation testing) consistently found the *actual* root cause rather than the first plausible one — several "bugs" turned out to be stale test expectations contradicting an intentional, documented design decision (D-04, D-05), and the sessions proved that distinction with evidence rather than asserting it.
- Parallelizing independent debug sessions (distinct files, no overlap) cut wall-clock time significantly on the milestone-close cleanup; sequencing only the sessions that shared a file (e.g. two fixes both touching `test_artifact_scope_enforcement.py`) avoided merge conflicts without sacrificing parallelism elsewhere.
- Revert-and-reconfirm as a standard verification step (deliberately re-breaking the fix to prove the test actually catches the original bug) caught several near-misses where a fix looked complete but the regression test would have passed vacuously.

### What Was Inefficient
- Several "newly discovered" issues during milestone close turned out to already be fixed by later phase work — the debug session files were stale, not the code. Debug sessions that pause for a long time (days to weeks, across phase boundaries) should check current HEAD before re-deriving a fix that may have already landed elsewhere.
- Parallel debug sessions sharing an append-only file (`knowledge-base.md`) produced a destructive near-miss: a crafted-blob commit strategy, built to avoid swallowing a concurrent session's uncommitted append, went stale mid-flight and briefly deleted another session's entry. It was caught and forward-fixed, but a plain pathspec-scoped `git commit` would have been strictly safer for an append-only file under concurrent edits.
- One Opus session-limit interruption mid-run lost no committed work (checkpoints are durable) but required manually diffing working-tree state against each debug file's recorded status to resume correctly, rather than a clean restart.

### Patterns Established
- Debug session files are persistent, resumable investigation records, not throwaway scratch — `resolved/` archival plus a `knowledge-base.md` entry turns every investigation into a reusable "known pattern" lookup for future sessions.
- Fix-acceptance guardrail signals (target test, mutation check, no-op-deletion check, adjacent-tier regression, revert-and-reconfirm) are the bar for "confirmed fixed," not just "the new assertion passes."
- Milestone close is itself a GSD-governed workflow with a hard audit gate (open debug sessions, UAT gaps, deferred items) — nothing closes silently; every acknowledged item gets a disclosure row in STATE.md.

### Key Lessons
1. A test asserting the wrong thing about an intentional design decision (e.g. "the worktree should still exist after COMPLETED") looks exactly like a product bug until someone reads the decision record — always check for a named, documented decision before assuming the test is right.
2. When fixing a test's assertion, immediately ask "could this assertion's absence have let a *different* bug through, or let a future regression pass silently?" — several of this milestone's debug sessions found a second, worse instance of the same defect class while verifying the first fix (e.g. the `fake_claude_env` PATH-prepend issue found while verifying the real-CLI-spawn fix).
3. A stale premise encoded as both a prose comment AND an executable assertion is self-sealing — fixing it looks like breaking something, which is exactly why it can survive for phases. Watch for assertions whose own failure would read as confirmation of the status quo.

### Cost Observations
- Sessions: dozens of debug-session agent spawns across the milestone-close pass, mostly `gsd-debug-session-manager` → `gsd-debugger` pairs, run in parallel where files didn't overlap.
- Notable: one Opus usage-limit interruption mid-batch; all in-flight work was recoverable from committed checkpoints with no data loss, confirming the debug workflow's durability design held up under real interruption, not just in theory.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v1.0 | 12 | First milestone; established the debug-session + fix-acceptance-guardrail pattern for milestone-close cleanup |

### Cumulative Quality

| Milestone | Test Files | Phases Shipped |
|-----------|-----------|-----------------|
| v1.0 | 224 | 12/12 |

### Top Lessons (Verified Across Milestones)

1. A documented design decision beats an undocumented test assumption every time — read `*-RESEARCH.md`/`*-CONTEXT.md` decision records before trusting a failing test's premise.
