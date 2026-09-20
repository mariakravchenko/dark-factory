# Phase 07: User Setup Required

**Generated:** 2026-09-20
**Phase:** 07-claude-code-the-first-real-worker
**Status:** Incomplete

Complete this item for the new `.github/workflows/ci.yml` to actually run. Claude authored
and structurally verified the workflow file locally (parses as valid YAML, four named steps
present, all Task/plan-level `<verify>` commands green); the one thing it cannot do is create
a GitHub-hosted remote on your behalf.

## Environment Variables

None required. The `quality` job requests no secrets — it declares only
`permissions: contents: read` and runs no `db`/`integration` tier tests.

## Account Setup

[Skip if you already have a GitHub account and access to create repositories under it]

- [ ] **Create the GitHub repository**
  - URL: https://github.com/new
  - Skip if: A remote repository already exists for this project

## Dashboard Configuration

- [ ] **Add the GitHub repository as `origin` and push the current branch**
  - Location: local shell, after creating the repo on github.com
  - Commands:
    ```bash
    git remote add origin <url>
    git push -u origin <branch>
    ```
  - Notes: `git remote -v` is currently empty in this working copy — no build has run yet
    because there is nowhere for GitHub Actions to run it.

- [ ] **Confirm Actions is enabled and the `ci` workflow appears on the first push**
  - Location: GitHub repository → Actions tab
  - Set to: Actions enabled (default for new repositories)
  - Notes: The `ci` workflow triggers on `push` (`branches: ["**"]`) and `pull_request`, so it
    should appear and start running immediately after the first push.

## Verification

After completing setup, verify with:

```bash
git remote -v
git push -u origin <branch>
```

Then visit the repository's **Actions** tab on GitHub.

Expected results:
- `git remote -v` shows an `origin` pointing at your GitHub repository.
- The `ci` workflow run appears in the Actions tab after the push.
- The `quality` job's four named steps (`Lint (ruff)`, `Types (mypy)`,
  `Worker-name leak guard (QUAL-04)`, `Unit and contract tiers`) all show green checkmarks.

---

**Once all items complete:** Mark status as "Complete" at top of file.
