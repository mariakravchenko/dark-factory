---
phase: quick
plan: 261030-mcz
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/scaffold_target_repo.py
  - README.md
autonomous: true
requirements: [QUICK-MCZ]

estimate:
  tokens: 28000
  raw_tokens: 22000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "Both generated workflows (.github/workflows/run.yml and .github/workflows/resume.yml) declare a permissions block whose parsed mapping is exactly contents: write, issues: write, pull-requests: write"
    - "A CI job started from either generated workflow can post a clarification comment and open a pull request without the Actions auto-token's permission scoping returning 403"
    - "README's '#### Scaffolding steps 2 and 3' subsection names all three permission keys and says what each one unblocks"
    - "The README resume-workflow-reference sentinel block is byte-identical to its pre-task content"
  artifacts:
    - "scripts/scaffold_target_repo.py — RESUME_WORKFLOW_TEMPLATE and RUN_WORKFLOW_TEMPLATE permissions blocks"
    - "README.md — the '#### Scaffolding steps 2 and 3' subsection"
  key_links:
    - "generated workflow permissions block -> the job's GITHUB_TOKEN env entry -> GitHubClient.create_comment (rest.issues.create_comment) and GitHubClient.create_pull_request (rest.pulls.create)"
    - "README's scaffolding prose -> the same three-key block the script actually emits (prose and template must not drift)"
---

<objective>
The two GitHub Actions workflows `scripts/scaffold_target_repo.py` generates declare
`permissions: contents: write` only. Both jobs pass the reserved Actions auto-token
through as `GITHUB_TOKEN`, and that token's REST authority is scoped by *exactly* that
block — so Dark Factory's own API calls inside the job are under-scoped: posting a
clarification comment (`POST /repos/{owner}/{repo}/issues/{n}/comments`) needs
`issues: write`, and opening the PR (`POST /repos/{owner}/{repo}/pulls`) needs
`pull-requests: write`. Add both keys to both templates, and update the README
subsection that currently explains only `contents: write`.

Purpose: a scaffolded repository's first real run currently 403s at the first
clarification comment or at PR publication — the exact two side effects the whole
local-pause/CI-resume loop exists to produce.

Output: a corrected three-key permissions block in both generated workflows, and
README prose that explains all three keys without drifting from what the script emits.
</objective>

<execution_context>
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/workflows/execute-plan.md
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/quick/261029-p12-extend-scripts-scaffold-target-repo-py-t/261029-p12-SUMMARY.md
@scripts/scaffold_target_repo.py
@README.md
</context>

<grounded_findings>
Established by reading the code before planning — treat as facts, do not re-derive:

1. **Scopes confirmed from the actual calls** (not assumed):
   - `GitHubClient.create_comment` (`src/dark_factory/github/client.py:246`) calls
     `rest.issues.create_comment` → `POST /repos/{owner}/{repo}/issues/{n}/comments`
     → needs **`issues: write`**. Reached on the run/resume path from
     `src/dark_factory/orchestrator/runner.py:1788` (the `WAITING_HUMAN`
     clarification comment).
   - `GitHubClient.create_pull_request` (`client.py:265`) calls `rest.pulls.create`
     → `POST /repos/{owner}/{repo}/pulls` → needs **`pull-requests: write`**.
     Reached from `src/dark_factory/orchestrator/publish.py:341`.
   - Reads already covered by those two writes: `fetch_issue` (`issues.get` +
     `issues.list_comments`, used for a `github:`-prefixed source) and
     `find_pull_request_for_branch` (`pulls.list`, the publish idempotency probe).
   - **`actions: write` is deliberately NOT added.** The only `actions`-scoped call,
     `dispatch_workflow` (`client.py:298`), is made solely from
     `src/dark_factory/webhook/app.py:377` via `GitHubClient.for_dispatch` using the
     separate `DISPATCH_GITHUB_TOKEN` — outside both generated workflows.

2. **There are no existing test assertions on the permissions block shape to update.**
   No file under `tests/` references `scaffold_target_repo` at all; the prior quick
   task (261029-p12) verified the generated `run.yml` with a throwaway harness, not a
   committed test. So "update the assertions" here means: this plan's own `<automated>`
   checks must expect the three-key block. Do not go hunting for a test to edit, and
   do not add a new committed test file (out of scope for this task).

3. **`tests/unit/test_resume_workflow_reference_doc.py` guards the README sentinel
   block** by asserting: exactly one begin/end sentinel, a fenced block immediately
   inside them, that it parses as a YAML mapping, a required `run_id` input, exactly
   one resume invocation, no run-state branching, and consistent dispatch-credential
   naming. It does **not** assert anything about `permissions`. That block is still
   out of scope for this task (see `<out_of_scope>`).
</grounded_findings>

<out_of_scope>
- **The README `resume-workflow-reference` sentinel block (README.md:384-428) must not
  be edited.** It carries the same `permissions: contents: write` gap, and the prose
  that follows it (README.md:436-453) justifies only `contents: write`. This is a real,
  separate finding and the plan's final report must surface it as an unresolved
  decision for the user — see `<flagged_finding>`. Not silently fixed; not left
  unmentioned.
- No changes under `src/dark_factory/`.
- No changes to `pyproject.toml`.
- No new committed test files.
- This repository's own `.github/workflows/*` files.
</out_of_scope>

<tasks>

<task type="auto">
  <name>Task 1: Grant issues and pull-requests write in both generated workflow templates</name>
  <files>scripts/scaffold_target_repo.py</files>
  <action>
In `RESUME_WORKFLOW_TEMPLATE` (the `permissions:` / `contents: write` pair around
line 267) and in `RUN_WORKFLOW_TEMPLATE` (the identical pair around line 311), extend
each two-line permissions block to four lines by adding, in this order after
`contents: write`: an `issues` key set to write, then a `pull-requests` key set to
write. Both templates get the identical block — they are a symmetric pair maintained
as a four-point diff per 261029-p12's DD-1, and permissions is not one of the four
intended differences.

Precede each block with a short comment (identical text in both templates, matching
the explanatory-comment style the other templates in this file already use — which is
exactly why this module never uses `yaml.dump`) naming what each of the three scopes
buys: contents for pushing each role's work, issues for the clarification comment
Dark Factory posts, pull-requests for opening the PR after QA PASS and Quality Gate
PASS. Write that comment using the bare key names only; do not spell out the
`key: value` pairs inside the comment text.

Do not add `actions: write`, do not collapse to `permissions: write-all`, and do not
touch `fetch-depth: 0`, the `env:` blocks, the job keys, or the step names.

Then create the verification harness at the absolute path
`/tmp/df-261030-mcz-verify.py` (deliberately outside the repository so it leaves no
untracked residue). It must, using only the standard library plus PyYAML:
  - make a fresh temporary target directory
  - invoke `scripts/scaffold_target_repo.py` as a subprocess against it with
    `--github-owner acme --github-repo widget --yes`, asserting exit code 0
  - `yaml.safe_load` both `.github/workflows/run.yml` and
    `.github/workflows/resume.yml` from that target and assert each parsed
    `permissions` mapping equals exactly the three-entry mapping
    `{"contents": "write", "issues": "write", "pull-requests": "write"}` — compare the
    parsed mapping, never grep the text, so the new comment lines cannot affect the
    result
  - assert both files still carry `fetch-depth: 0` on the checkout step and still pass
    the script's own `parse_check` (exit 0 above already covers the latter)
  - print `PERMISSIONS_OK` as its last line and exit non-zero on any failure
  </action>
  <verify>
    <automated>uv run python /tmp/df-261030-mcz-verify.py</automated>
  </verify>
  <done>
`PERMISSIONS_OK` printed. Both generated workflows parse with a permissions mapping of
exactly three entries — contents, issues and pull-requests, each set to write — and no
other generated content changed.
  </done>
  <reversibility rating="reversible">A template string edit in a standalone developer script; revertible in one commit, and it only widens scope on workflows a deployer regenerates.</reversibility>
</task>

<task type="auto">
  <name>Task 2: Explain all three permission keys in README's Scaffolding steps 2 and 3</name>
  <files>README.md</files>
  <action>
Rewrite the sentence in the `#### Scaffolding steps 2 and 3` subsection (README.md,
the paragraph at lines 334-342 describing the generated `run.yml`) that currently
reads that it "carries the same `permissions: contents: write` block for the same
reason the resume one does". Replace it with prose covering all three keys the script
now emits, stating for each one what it unblocks and why the job cannot do without it:

  - `contents: write` — the existing reason, kept: a run commits and pushes each
    role's work, and `actions/checkout`'s persisted credential is scoped by this block,
    so it is what stands between that push and a 403.
  - `issues: write` — the job hands the reserved Actions auto-token to
    `dark-factory` as `GITHUB_TOKEN`, and that token's REST authority is scoped by
    this same block; Dark Factory posts its own clarification comment on the issue
    when a run pauses `WAITING_HUMAN` (and reads the issue when the source is
    `github:`-prefixed).
  - `pull-requests: write` — publication after QA PASS and an independent Quality
    Gate PASS creates the pull request through the API, which this scope authorizes.

Make it explicit that both generated workflows carry the identical block, and that the
scope stops there deliberately — `actions: write` is absent because the only
workflow-dispatch call Dark Factory makes happens in the webhook receiver on the
separate `DISPATCH_GITHUB_TOKEN`, never inside these jobs.

Keep the existing surrounding paragraphs (the `uv run` examples, the `--force` /
instruction-copy paragraph, the "developer tool, not a subcommand" paragraph) intact.
Stay inside this subsection: everything from `### The full flow` (README.md:357)
onward, and in particular the `resume-workflow-reference` sentinel block and the
`permissions: contents: write` reasoning paragraphs that follow it, must remain
byte-identical.

Then extend `/tmp/df-261030-mcz-verify.py` with a second, region-scoped stage that:
  - slices `README.md` from the `#### Scaffolding steps 2 and 3` heading up to the
    next `### ` heading and asserts that region mentions both new scope keys and still
    mentions contents
  - extracts the text inclusive of the two `resume-workflow-reference` sentinel
    comments and asserts its SHA-1 hex digest is exactly
    `7333ea66ca7f46be14d8a2ca76a76aa86a29427c` (the pre-task value, computed over the
    inclusive begin-sentinel-through-end-sentinel slice)
  - prints `README_OK` after `PERMISSIONS_OK` and exits non-zero on any failure
  </action>
  <verify>
    <automated>uv run python /tmp/df-261030-mcz-verify.py && uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q</automated>
  </verify>
  <done>
`PERMISSIONS_OK` and `README_OK` both printed, the sentinel-block SHA-1 matches the
pre-task value, and `tests/unit/test_resume_workflow_reference_doc.py` passes. The
Scaffolding subsection explains contents, issues and pull-requests and says why
`actions` is absent.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions job → GitHub REST API | The reserved Actions auto-token crosses here as `GITHUB_TOKEN`; the workflow's `permissions:` block is the *only* thing scoping its authority. |
| Generated workflow file → deployer's repository | Dark Factory authors the file; the deployer owns, reviews and commits it. Over-granting here silently widens a third party's CI blast radius. |
| Dark Factory job → worker CLI subprocess | The worker runtime runs inside the same job; its env is built from an allowlist in `src/dark_factory` (unchanged by this plan). |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-mcz-01 | Elevation of Privilege | `permissions:` block in both generated workflows | medium | mitigate | Grant only the two scopes the confirmed REST calls need (`issues: write` for `rest.issues.create_comment`, `pull-requests: write` for `rest.pulls.create`). Task 1 explicitly forbids `permissions: write-all` and forbids `actions: write`, and the verify asserts the parsed mapping has *exactly* three entries — so an over-grant fails the gate. |
| T-mcz-02 | Information Disclosure | worker CLI subprocess sharing the job with a now-wider auto-token | medium | accept | The widened token is job-scoped and was already reachable as `GITHUB_TOKEN` by anything in the job; this edit changes its *scope*, not its reachability, and adds no new leak path. The worker credential boundary (explicit env allowlist, never `os.environ.copy()`) lives in `src/dark_factory` and is out of scope here. Accepted for this template change; revisit if a role is ever granted an unsandboxed shell in CI. |
| T-mcz-03 | Information Disclosure | README permission prose | low | accept | The documented rationale names scope keys and endpoint shapes only — no token values, no connection strings, no secret names beyond the already-documented Actions secret identifiers. |
| T-mcz-04 | Spoofing | PR opened by the Actions auto-token rather than a human | low | accept | Pre-existing and intended: publication is gated on QA PASS plus independent Quality Gate PASS before any PR is created. This plan grants the scope that gate already assumes; it does not relax the gate. |
| T-mcz-SC | Tampering | npm/pip/cargo installs | n/a | accept | Not applicable — this plan adds no package-manager install task and introduces no new dependency. The generated workflows' existing `pip install "{{INSTALL_SOURCE}}"` step is untouched. |
</threat_model>

<verification>
1. `uv run python /tmp/df-261030-mcz-verify.py` prints `PERMISSIONS_OK` then `README_OK`.
2. `uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q` passes.
3. `uv run ruff check scripts/scaffold_target_repo.py` and `uv run ruff format --check scripts/scaffold_target_repo.py` both clean (template strings are long; confirm no line-length regression).
4. Only `scripts/scaffold_target_repo.py` and `README.md` appear in the task diffs.
</verification>

<success_criteria>
- Both `RUN_WORKFLOW_TEMPLATE` and `RESUME_WORKFLOW_TEMPLATE` emit a permissions mapping of exactly `contents: write`, `issues: write`, `pull-requests: write`.
- No `actions: write`, no `write-all`.
- README's `#### Scaffolding steps 2 and 3` explains all three keys and the deliberate absence of `actions`.
- The `resume-workflow-reference` sentinel block SHA-1 is unchanged at `7333ea66ca7f46be14d8a2ca76a76aa86a29427c`.
- Two atomic commits (feat for the script, docs for the README).
</success_criteria>

<flagged_finding>
**MANDATORY — the SUMMARY and the final report to the user must carry this verbatim as an
unresolved, separate finding. Do not fix it in this task.**

The README reference workflow inside the `resume-workflow-reference` sentinel block
(README.md:384-428) **has the identical permissions gap**: it declares
`permissions:` / `contents: write` and nothing else. The ~18 lines of reasoning that
follow it (README.md:436-453) justify `contents: write` in depth and never mention the
issue-comment or pull-request scopes at all.

Consequence: a deployer who follows the documented path of copying that reference
block — which the README explicitly instructs ("Copy the block below into your own
repository at `.github/workflows/resume.yml`") — gets an under-scoped workflow even
after this task ships, because the fix here only reaches repositories scaffolded by
the script. The two paths now disagree.

Accuracy note on the guard: `tests/unit/test_resume_workflow_reference_doc.py` asserts
sentinel count, fenced-block presence, YAML-mapping parse, the required `run_id`
input, exactly-one-resume-invocation, absence of run-state branching, and
dispatch-credential naming. It does **not** assert on `permissions`, so adding the two
keys would not, by itself, fail that test — the block is out of scope here by
instruction and because its surrounding prose would also need rewriting, not because
the test mechanically blocks it.

Decision for the user: either (a) a follow-up quick task that adds the two keys to the
sentinel block and extends the `permissions` reasoning prose to cover all three scopes,
or (b) an explicit decision to leave the reference block minimal and have the prose say
so. Doing nothing leaves the README internally inconsistent.
</flagged_finding>

<output>
Create `.planning/quick/261030-mcz-fix-scripts-scaffold-target-repo-py-gene/261030-mcz-SUMMARY.md` when done, with `<flagged_finding>` reproduced in full under a clearly-labelled unresolved-findings heading.
</output>
