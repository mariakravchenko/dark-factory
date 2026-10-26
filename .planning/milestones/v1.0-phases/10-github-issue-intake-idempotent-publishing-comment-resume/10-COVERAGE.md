# API Coverage — GitHub

**Phase:** 10 — GitHub — Issue Intake, Idempotent Publishing, Comment Resume
**SDK:** `githubkit` (>=0.16,<0.17) — locked by 10-CONTEXT.md D-03
**Produced:** 2026-09-26 (plan-phase)

> **Full API Coverage by Default — Opt Out, Never Opt In.** Every capability in the
> neighbourhood this phase touches (issues, issue comments, pull requests, webhooks,
> authenticated identity) starts as `INTEGRATE`. This table is the *subtraction record*: an
> `OPT-OUT` row is a deliberate, reasoned decision, never an un-noticed hole. Rows are scoped
> to the surface Phase 10's own requirements (INTAKE-03, GIT-03..GIT-06) reach — not to all of
> GitHub's API.

| capability | decision | reason |
|---|---|---|
| `issues.get` — fetch issue title + body | `INTEGRATE` | |
| `issues.get` — issue labels (from the response's `labels` array) | `INTEGRATE` | |
| `issues.list_comments` — the issue's comment thread | `INTEGRATE` | |
| pagination over `issues.list_comments` | `INTEGRATE` | INTAKE-03 says "comments", not "the first page of comments" — an issue with more than one page must be read whole. |
| repository metadata (owner / repo / default branch) | `INTEGRATE` | INTAKE-03 names "repository metadata" explicitly; owner/repo come from `.dark-factory.yaml` per D-04, the rest from the issue response's `repository_url`/`repos.get`. |
| `issues.create_comment` — post a clarification comment | `INTEGRATE` | |
| `users.get_authenticated` (`GET /user`) — Dark Factory's own login | `INTEGRATE` | The self-comment-loop filter (10-RESEARCH Pitfall 2) needs the token's own identity. |
| `pulls.create` — open the pull request | `INTEGRATE` | |
| `pulls.list` filtered by `head` — find existing PR for run's branch | `INTEGRATE` | The GIT-04 crash-safety net: the only check that distinguishes "never attempted" from "succeeded on GitHub, crashed before the commit". |
| `webhooks.verify` — HMAC-SHA256 signature check | `INTEGRATE` | |
| `webhooks.parse` — typed `issue_comment` event model | `INTEGRATE` | |
| built-in retry / rate-limit handling on the client | `INTEGRATE` | Bounded retry on idempotent reads; wired through the one `GitHubClient` wrapper so no call site re-invents it. |
| `issues.update_comment` — edit a previously posted comment | `OPT-OUT` | D-08 locks "posts a fresh issue comment (never edits a prior one)"; an edit path would make "which comment maps to which interaction" ambiguous against the `uq_one_waiting_interaction_per_run` index. |
| `issues.delete_comment` | `OPT-OUT` | No requirement retracts a question; a deleted clarification comment is not a state Dark Factory drives, and deleting a human's answer is never Dark Factory's decision. |
| `issues.create` — open a new issue | `OPT-OUT` | Dark Factory consumes issues as task input; nothing in INTAKE-03..GIT-06 creates one. |
| `issues.update` — close / reopen / retitle the source issue | `OPT-OUT` | Closing the source issue is the maintainer's decision after PR review; the publishing policy stops at PR creation. |
| `issues.add_labels` / `set_labels` on the issue or PR | `OPT-OUT` | No Phase 10 requirement asks Dark Factory to label anything; labels are read-only input for INTAKE-03. |
| `pulls.get` — fetch a PR by number | `OPT-OUT` | `pulls.list(head=...)` already answers the only question asked ("does a PR exist for this run's branch?"); a by-number fetch has no caller. |
| `pulls.update` — retitle / rewrite body / change base after creation | `OPT-OUT` | GIT-04 makes the PR a terminal, write-once side effect: a resumed publish step must never silently revert a human's edits to the PR. |
| `pulls.merge` | `OPT-OUT` | Merge is a human decision; the publishing policy (CLAUDE.md) ends at "PR creation only after QA PASS and Quality Gate PASS". |
| `pulls.request_reviewers` / `pulls.create_review` / review-comment ingestion | `OPT-OUT` | Review ingestion is not in any Phase 10 requirement — QA and the independent Quality Gate (Phase 9) are Dark Factory's verification surface. |
| `git.create_ref` — create the working branch via the REST API | `OPT-OUT` | GIT-01/GIT-02 already own branch creation through the `git` CLI (`git/worktree.py` + `push_working_branch`); a second branch-creation path would split ownership of a durability-critical side effect. |
| `repos.create_webhook` — register the webhook programmatically | `OPT-OUT` | Webhook registration is repo-admin setup, declared as `user_setup` in plan 10-04, not orchestration behaviour. |
| webhook `issue_comment` actions `edited` / `deleted` / `pinned` / `unpinned` | `OPT-OUT` | Only `action == "created"` can answer a pending question; an edited or deleted comment cannot un-answer an interaction that is already `ANSWERED` (D-05's dedup key is the comment id). |
| webhook events other than `issue_comment` (`push`, `pull_request`, etc.) | `OPT-OUT` | No Phase 10 requirement consumes them; trigger generalization across CLI/CI/webhook is explicitly Phase 11's job (TRIG-01/TRIG-04). |
| comments on pull requests (`issue.pull_request` present in the payload) | `OPT-OUT` | Dark Factory only ever asks its questions on issues (GIT-05), so a PR-thread comment can never be the answer to a pending interaction; filtered out before resolution. |
| GraphQL API (`githubkit.graphql`) | `OPT-OUT` | Every call above exists in the typed REST namespace; adding a second transport would duplicate auth, pagination and error-redaction discipline for no capability gain. |
| GitHub App installation auth / OAuth flows | `OPT-OUT` | D-04 reuses the existing `Settings.github_token` PAT as Dark Factory's own identity and introduces no new token type; App identity is an unrelated future migration (10-RESEARCH Assumption A3). |
