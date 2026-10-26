# API Coverage — GitHub REST API (via `githubkit` 0.16.1)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

**Why this file exists for Phase 11.** The deterministic detector, run at plan time over the
ROADMAP phase section plus an at-that-moment-empty PLAN body, returned `detected: false` — it had
no plan text to read yet. Re-run against the written plans it returns `detected: true`. The phase
adds one genuinely new outbound GitHub REST capability (`actions.create_workflow_dispatch`,
11-CONTEXT.md D-01), so the matrix was produced deliberately at plan time rather than left to seal
time.

**Baseline.** The surface below is GitHub's REST API *as this codebase reaches it* — issue
read/comment, pull-request create/list, authenticated-user identity, inbound webhook verification,
and (new this phase) GitHub Actions. It is not GitHub's entire REST surface. Every row was
re-decided from a full-coverage baseline rather than inherited from Phase 10's decisions.

| capability | decision | reason |
|---|---|---|
| `issues.get` | INTEGRATE | |
| `issues.list_comments` | INTEGRATE | |
| `issues.create_comment` | INTEGRATE | |
| `pulls.create` | INTEGRATE | |
| `pulls.list` | INTEGRATE | |
| `users.get_authenticated` | INTEGRATE | |
| `webhooks.verify` / `webhooks.parse` | INTEGRATE | |
| `actions.create_workflow_dispatch` | INTEGRATE | New this phase (D-01) — the one capability Phase 11 adds. |
| `actions.create_workflow_dispatch` + `return_run_details` | OPT-OUT | No dispatched-run observability requirement in this phase; tracked for Phase 12 (OBS-01/OBS-02). |
| `actions.list_workflow_runs` | OPT-OUT | Not needed: the run's Neon row is the authority, and a second source of truth would contradict STATE-08. |
| `actions.get_workflow_run` | OPT-OUT | Same reason as `list_workflow_runs`; revisit only if Phase 12 surfaces the dispatched run's URL. |
| `actions.re_run_workflow` | OPT-OUT | A failed resume is re-driven by a new `dark-factory resume`, never by replaying an Actions run outside the `advance()` funnel. |
| `actions.cancel_workflow_run` | OPT-OUT | Not needed: the run's lease and status columns already govern whether work proceeds; a second control path would compete. |
| `actions.download_workflow_run_logs` | OPT-OUT | Not needed: artifact content lives on the filesystem with references in Neon; nothing is fetched back from Actions. |
| `actions.list_workflow_run_artifacts` | OPT-OUT | Same reason as `download_workflow_run_logs`. |
| `actions.create_or_update_repo_secret` | OPT-OUT | Out of scope and a credential-boundary violation: `resume.yml`'s secrets are deployer-provisioned (D-04). |
| `actions.list_repo_workflows` | OPT-OUT | Not needed: the workflow file name is a fixed deployer contract (`resume.yml`, D-04); no discovery step. |
| `repos.create_dispatch_event` | OPT-OUT | D-01 selects `workflow_dispatch`; `repository_dispatch` would add event-type routing for no gain. |
| `git.create_ref` | OPT-OUT | Out of scope: Dark Factory owns branch and commit policy through the `git` CLI, not the REST API. |
| `repos.create_or_update_file_contents` | OPT-OUT | Same reason as `git.create_ref` — a second write path would break git ownership. |
| `checks.create` / `statuses.create` | OPT-OUT | Not needed yet: the quality gate is a local command set (GATE-01..04), not a GitHub check run. |
