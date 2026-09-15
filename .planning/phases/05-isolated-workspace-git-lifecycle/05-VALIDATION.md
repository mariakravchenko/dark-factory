---
phase: "05"
slug: "isolated-workspace-git-lifecycle"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-14"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (pinned in `pyproject.toml`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, markers `unit`/`db`/`integration`/`contract` |
| **Quick run command** | `uv run pytest -q -m unit` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~10-30 seconds (unit); ~50-60 minutes for the full suite (unit+db+integration) against real PostgreSQL 17, per 05-02/05-03's recorded full-suite gate wall-clock times |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m unit`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Task 1 | 05-01 | 1 | GIT-01 | T-05-09 / mitigate | Working branch created from configured base, unique per run; every role shares the same worktree | unit | `uv run pytest tests/unit/test_git_worktree.py -x` | ✅ | ✅ green (05-01) |
| Task 3 | 05-02 | 2 | GIT-01 | T-05-09 / mitigate | Same worktree reused across pause/resume (D-03), not recreated | integration | `uv run pytest tests/integration/test_worktree_lifecycle.py -x` | ✅ | ✅ green (05-02) |
| Task 1 | 05-01 | 1 | GIT-02 | T-05-01 / mitigate | No git mutation happens outside the orchestrator's git package (mirrors `test_single_mutation_path.py`) | unit | `uv run pytest tests/unit/test_git_ownership_boundary.py -x` | ✅ | ✅ green (05-01) |
| Task 3 | 05-03 | 3 | ART-04 | T-05-06 / mitigate | A fresh `git clone` + checkout of the working branch has the run's artifact content available | integration | `uv run pytest tests/integration/test_artifact_cross_clone.py -x` | ✅ | ✅ green (05-03) |
| Task 3 | 05-04 | 4 | ROLE-05 | T-05-05 / mitigate | `write_scope` glob matching: positive, negative, deep-nesting, decoy-directory, zero-tolerance cases | unit | `uv run pytest tests/unit/test_write_scope.py -x` | ✅ | ✅ green (16 passed, verified in this plan's own sandbox) |
| Task 2 | 05-04 | 4 | ROLE-05 | T-05-03 / mitigate | A violating diff is reverted (tracked-edit and new-file cases) and the role fails with the D-09 failure shape | integration | `uv run pytest tests/integration/test_write_scope_enforcement.py -x` | ✅ | ⬜ pending — DB-reachability handoff (see 05-04-SUMMARY.md Test Execution Handoff) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/support/git_repo.py` — new fixture factory for a throwaway real git repo (init, commit, branch); no such fixture exists today (`tests/support/` currently has only `config.py`, `fake_artifacts.py`, `log_sink.py`, `subprocess_runner.py`) (05-01)
- [x] `tests/unit/test_git_worktree.py` — new unit test file (git-repo-backed, no DB, no network) (05-01)
- [x] `tests/unit/test_write_scope.py` — new unit test file (05-04)
- [x] `tests/unit/test_git_ownership_boundary.py` — new unit test file (05-01)
- [x] `tests/integration/test_worktree_lifecycle.py` — new integration test file exercising the full `advance()`/`drive()` loop against a real git repo (05-02)
- [x] `tests/integration/test_artifact_cross_clone.py` — new integration test file (05-03)
- [x] `tests/integration/test_write_scope_enforcement.py` — new integration test file (05-04)
- [x] Migration `0005_wip_commit_sha` + `tests/db/test_role_executions_wip_commit_sha_schema.py` (sibling to existing `tests/db/test_human_interactions_schema.py` pattern) (05-02)

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification per RESEARCH.md's Validation Architecture.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved — plan 05-04 closes Phase 5 (all four Per-Task
Verification Map rows filled with real Task ID/Plan/Wave values, all Wave 0
files present, all six sign-off items satisfied). One row
(`tests/integration/test_write_scope_enforcement.py`, ROLE-05) is authored
and self-consistency-checked in this plan's sandbox but not yet executed
against a real PostgreSQL 17 — see `05-04-SUMMARY.md`'s Test Execution
Handoff, the same recurring DB-reachability pattern 05-02 and 05-03 already
documented. 2026-09-15.
