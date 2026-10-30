---
phase: quick
plan: 261030-mng
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/unit/test_resume_workflow_reference_doc.py
  - README.md
autonomous: true
requirements: [QUICK-MNG]

estimate:
  tokens: 18000
  raw_tokens: 18000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "The README's resume-workflow-reference sentinel block declares a permissions block whose parsed YAML mapping is exactly {contents: write, issues: write, pull-requests: write}"
    - "A deployer who hand-copies the sentinel block into .github/workflows/resume.yml gets a job whose GITHUB_TOKEN can post the WAITING_HUMAN clarification comment and open the post-QA PR without a 403"
    - "The prose immediately following the block explains all three scopes, and the pre-existing contents: write / persist-credentials / fetch-depth reasoning survives verbatim"
    - "tests/unit/test_resume_workflow_reference_doc.py fails if a fourth permission key is added to the block, if any of the three is removed, or if the block collapses to write-all"
  artifacts:
    - "README.md — the resume-workflow-reference sentinel block's permissions key, and the permissions-reasoning paragraph that follows the block"
    - "tests/unit/test_resume_workflow_reference_doc.py — a new exact-mapping permissions assertion plus its module-level expected-mapping constant"
  key_links:
    - "sentinel block permissions: -> the job's GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }} env entry -> GitHubClient.create_comment (reached from runner.py's ROLE_NEEDS_INPUT branch) and GitHubClient.create_pull_request (reached from publish.py)"
    - "_extract_reference_workflow_yaml() sentinel extraction -> yaml.safe_load -> the new exact-mapping assertion (the only mechanism preventing this gap from silently reappearing)"
    - "the new prose's 'this job's token carries no actions scope' claim -> the existing '### The dispatch credential' subsection (README.md:527-535), which explains actions: write as DISPATCH_GITHUB_TOKEN's own permission — the two must agree, not contradict"
---

<objective>
The README's hand-copyable reference workflow — the block bracketed by
`<!-- resume-workflow-reference: begin -->` / `: end -->` at README.md:398-442 — declares
`permissions:` / `contents: write` and nothing else. Quick task 261030-mcz fixed this
exact bug in `scripts/scaffold_target_repo.py`'s two generated templates but deliberately
left this block alone, flagging it as an unresolved finding. The two documented deployment
paths therefore disagree today: a repo scaffolded by the script is correctly scoped, a repo
set up by copying the README block is not.

Close that gap on the README path: add `issues: write` and `pull-requests: write` inside
the sentinel block, extend the reasoning prose that follows it to cover the two new scopes,
and add a guard assertion so the gap cannot silently reappear.

Purpose: a deployer who follows the README's own explicit instruction ("Copy the block
below into your own repository at `.github/workflows/resume.yml`") currently gets a job
that 403s at the first clarification comment or at PR publication — the two side effects
the whole local-pause/CI-resume loop exists to produce.

Output: a three-key `permissions:` block inside the sentinel comments, prose that explains
all three keys without disturbing the existing `contents: write` reasoning, and a test that
fails on any drift from exactly those three keys.
</objective>

<execution_context>
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/workflows/execute-plan.md
@/Users/maryiakrauchanka/portfolio/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/quick/261030-mcz-fix-scripts-scaffold-target-repo-py-gene/261030-mcz-SUMMARY.md
@tests/unit/test_resume_workflow_reference_doc.py
@README.md
</context>

<resolved_during_planning>
Two questions from the task framing are already answered — do not re-investigate them:

1. **There is no hash/checksum drift check to recompute.** `tests/unit/test_resume_workflow_reference_doc.py`
   contains no digest, checksum, or byte-comparison against any other source. Its drift
   detection is entirely structural: sentinel-count extraction
   (`_extract_reference_workflow_yaml`), markdown-fence shape, `yaml.safe_load` into a
   mapping, the `run_id` input, exactly-one-`dark-factory resume`, zero `if:` keys, the
   `DISPATCH_GITHUB_TOKEN` name appearing in both README.md and .env.example, worker
   binary/credential table rows parametrized from `LIVE_RUNTIMES`, and install-guidance
   ordering. The SHA-1 digest mentioned in 261030-mcz's SUMMARY lived in a throwaway
   `/tmp` verification harness for that task only — it was never committed and there is
   nothing stale anywhere in the suite. The test file also asserts nothing about
   `permissions` today, which is precisely why this gap could exist.

2. **`actions: write` already legitimately appears in the prose region after the end
   sentinel**, at README.md:531, inside `### The dispatch credential`. That occurrence is
   correct and must survive: it describes the fine-grained PAT behind
   `DISPATCH_GITHUB_TOKEN`, which belongs to the webhook receiver, not to this job. The new
   prose must forward-reference and agree with it, not contradict it, and must not be
   verified by any whole-region absence check.

Baseline measured during planning: `uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q`
→ `13 passed`. Task 2 must therefore land on `14 passed`.
</resolved_during_planning>

<tasks>

<task type="auto">
  <name>Task 1: Add an exact-mapping permissions guard to the reference-workflow doc test (RED)</name>
  <files>tests/unit/test_resume_workflow_reference_doc.py</files>
  <behavior>
    The new assertion must fail for each of these block states, and pass for exactly one:
    - PASS: permissions maps contents, issues and pull-requests, each to write
    - FAIL (today's state): permissions maps contents: write only — the under-scoping this task fixes
    - FAIL: any fourth key added, including actions: write, which belongs only to DISPATCH_GITHUB_TOKEN
    - FAIL: permissions collapsed to the write-all string instead of a mapping
    - FAIL: permissions key absent from the workflow entirely
    - FAIL: any of the three keys scoped down to read
  </behavior>
  <action>
    Add one module-level constant and one test function to the existing file, following the
    conventions already in it: load-bearing expectations live as module-level constants beside
    `_SENTINEL_BEGIN` / `_DISPATCH_TOKEN_NAME`, and every assertion carries an f-string message
    naming what was expected and what was observed.

    Declare the expected mapping as a module-level constant near `_DISPATCH_TOKEN_NAME`, holding
    the three keys contents, issues and pull-requests each mapped to the string write, in that
    order. Note in its comment that YAML parses the hyphenated key as a plain string key, so no
    normalisation is needed.

    Add the test function after `test_the_dispatch_credential_is_named_consistently`. It calls the
    existing `_extract_reference_workflow_yaml()`, feeds the result to `yaml.safe_load`, reads the
    top-level permissions key with `.get()` (so an absent key surfaces as None in the failure
    message rather than raising KeyError), and asserts equality against the constant.

    Use equality against the whole mapping rather than a per-key containment loop — that is what
    makes this guard bidirectional, and the reason belongs in the docstring: a containment check
    would catch the under-scoping fixed here but would silently tolerate a later widening, which
    is the more dangerous direction for a credential-scoping block that a deployer copies verbatim.
    State in the docstring that the mapping is deliberately minimal, that the scopes correspond to
    the job's own REST calls (contents for the post-role push, issues for the clarification comment
    posted when a role reaches ROLE_NEEDS_INPUT, pull-requests for the PR opened after QA PASS plus
    Quality Gate PASS), and that the actions scope is absent by design because the only
    actions-scoped call — dispatching this very workflow — runs from the webhook receiver on the
    separate DISPATCH_GITHUB_TOKEN documented under "The dispatch credential", never from inside
    this job.

    Name the function so it reads as a claim about the workflow, matching the file's existing
    `test_the_reference_workflow_*` naming. Do not modify any existing test, constant, helper or
    the module docstring. Do not touch README.md in this task — this task is expected to end red.
  </action>
  <verify>
    <automated>uv run ruff check tests/unit/test_resume_workflow_reference_doc.py &amp;&amp; uv run ruff format --check tests/unit/test_resume_workflow_reference_doc.py &amp;&amp; uv run mypy tests/unit/test_resume_workflow_reference_doc.py &amp;&amp; { uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q; [ $? -eq 1 ]; }</automated>
  </verify>
  <done>
    Lint, format and mypy --strict all pass on the test file. `uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q`
    reports exactly one failure (13 passed, 1 failed) and exits 1. The failure output is the new
    permissions test, and its message shows the observed mapping as the single-key contents/write
    mapping — proving the guard genuinely catches today's gap rather than passing vacuously.
    No other test's status changed.
  </done>
</task>

<task type="auto">
  <name>Task 2: Grant issues and pull-requests write inside the sentinel block and extend its reasoning prose (GREEN)</name>
  <files>README.md</files>
  <action>
    Two edits to README.md, both scoped — use Edit, never a whole-file Write.

    Edit A — inside the sentinel block (README.md:398-442, deliberate and user-approved this time).
    Extend the `permissions:` key at README.md:410-411 from its single contents entry to all three
    entries, keeping the key order used by the already-fixed templates in
    `scripts/scaffold_target_repo.py` (contents, then issues, then pull-requests, each mapped to
    write, two-space indented). Immediately above the `permissions:` key, add the same three-line
    explanatory YAML comment those templates carry at scripts/scaffold_target_repo.py:267-269 and
    316-318 — copy it verbatim so the two deployment paths read identically. The in-block comment is
    not redundant with the README prose: a deployer copies the fenced block out and the surrounding
    prose stays behind, so the comment is the only explanation that travels to the file they end up
    owning. Change nothing else inside the sentinels — not the quoted `"on":` key, the `run_id`
    input, `fetch-depth: 0`, the commented "Install the worker runtime" step (its name string is
    load-bearing for an existing test), the resume step, or its env block.

    Edit B — extend the reasoning prose. Insert one new paragraph between the existing
    `contents: write` paragraph (README.md:450-467) and the `fetch-depth: 0` paragraph
    (README.md:469-478). Leave both of those paragraphs byte-identical: the persist-credentials
    analysis, the two failure modes hit in order while proving cross-machine resume, and the
    merge-base reasoning are all still fully correct and are not being revised. The new paragraph
    covers only the two added scopes and the one deliberate omission:
      - issues gives the job authority to post the clarification comment when a role reaches
        ROLE_NEEDS_INPUT and the run pauses WAITING_HUMAN — step 1 of the full flow above, and the
        thing that makes the whole pause/resume loop legible to the human
      - pull-requests gives it authority to open the PR after QA PASS and Quality Gate PASS, the
        publication the policy gates on
      - the job's token stops there: no actions scope, because the only actions-scoped call is the
        dispatch of this very workflow, made by the webhook receiver on the separate
        DISPATCH_GITHUB_TOKEN. Forward-reference the existing "### The dispatch credential"
        subsection rather than re-explaining it — that subsection at README.md:527-535 already
        documents that permission under its fine-grained-token label, and the two statements must
        read as one consistent story
    Frame both additions the way the existing paragraph frames contents: scoped to the REST calls
    the job actually makes, with the concrete failure a deployer sees if the scope is missing — the
    Actions auto-token's authority is bounded by exactly this block, so an absent scope surfaces as
    a 403 from the GitHub API, not as a git-level error.

    Also check whether the Actions-secrets paragraph at README.md:484-488 still reads correctly now
    that the block is three keys; it describes GITHUB_TOKEN as covering "the comment/PR operations
    Dark Factory performs on your behalf", which stays accurate — leave it alone unless it has
    become actively wrong.

    Out of scope, do not touch: anything under src/dark_factory/, pyproject.toml,
    scripts/scaffold_target_repo.py (fixed in 261030-mcz), and the
    "#### Scaffolding steps 2 and 3" subsection at README.md:308 onward (updated by that same task).
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q &amp;&amp; uv run python -c "
import pathlib, yaml
t = pathlib.Path('README.md').read_text(encoding='utf-8')
_, _, a = t.partition('&lt;!-- resume-workflow-reference: begin --&gt;')
inner, _, after = a.partition('&lt;!-- resume-workflow-reference: end --&gt;')
wf = yaml.safe_load('\n'.join(inner.strip('\n').splitlines()[1:-1]))
assert wf['permissions'] == {'contents': 'write', 'issues': 'write', 'pull-requests': 'write'}, wf['permissions']
prose, _, _ = after.partition('## Running the tests')
for s in ['issues: write', 'pull-requests: write', 'ROLE_NEEDS_INPUT', 'Quality Gate PASS']:
    assert s in prose, 'new prose missing: ' + s
for s in ['persist-credentials', 'fetch-depth: 0', 'no merge base', 'Write access to repository not granted']:
    assert s in prose, 'pre-existing prose lost: ' + s
print('OK')
"</automated>
  </verify>
  <done>
    `uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q` reports 14 passed, 0 failed
    (up from the 13-passed baseline, with Task 1's new test now green). The sentinel block's parsed
    permissions mapping equals exactly contents/issues/pull-requests each mapped to write. The prose
    region after the end sentinel names both new scopes and the two conditions that reach them, and
    still contains every load-bearing phrase from the pre-existing contents/fetch-depth reasoning.
    The block's own YAML comment matches the scaffold templates verbatim, so a deployer reading
    either path gets the same explanation.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions job → GitHub REST API | The job presents the reserved Actions auto-token; its REST authority is bounded by exactly the `permissions:` block being edited here |
| README block → deployer's own repository | The block is hand-copied, unvalidated and unversioned by Dark Factory; whatever it says becomes a real credential scope in a repository this project does not control |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-MNG-01 | Elevation of Privilege | README sentinel block `permissions:` → the job's `GITHUB_TOKEN` | medium | mitigate | Grant exactly the three scopes the job's own REST calls need; Task 1's equality assertion (not a containment check) fails on any added key or a `write-all` collapse, so a later over-grant cannot land silently |
| T-MNG-02 | Elevation of Privilege | the `actions` scope on this job's token | medium | mitigate | Keep `actions` off this token; the only actions-scoped call runs from the webhook receiver on the separate `DISPATCH_GITHUB_TOKEN`. Enforced by T-MNG-01's exact-mapping assertion and stated in the new prose |
| T-MNG-03 | Information Disclosure | the fenced block's `secrets.*` references | low | accept | The change introduces no new secret name and no literal credential value — only GitHub Actions `secrets.` indirections already present. No infrastructure credential is added to the block, prose, or test |
| T-MNG-04 | Tampering | doc/test drift between the README path and the scaffold path | low | mitigate | The in-block YAML comment is copied verbatim from the scaffold templates, and the committed test asserts the README block's mapping — the same mapping the scaffold script emits |
| T-MNG-SC | Tampering | npm/pip/cargo installs | n/a | accept | No package-manager install tasks in this plan; the dependency set and `uv.lock` are unchanged, so no legitimacy gate applies |
</threat_model>

<source_audit>
Quick-mode task: no ROADMAP phase goal, REQUIREMENTS entry, RESEARCH.md, or CONTEXT.md D-XX
decisions apply. Audited against the invocation's own constraints instead — every one is covered,
none deferred:

| Source item | Covered by |
|-------------|------------|
| CONSTRAINT: add `issues: write` + `pull-requests: write` inside the sentinel block | Task 2, Edit A |
| CONSTRAINT: match key ordering/style of the fixed scaffold templates | Task 2, Edit A (order + verbatim comment from scripts/scaffold_target_repo.py:267-273) |
| CONSTRAINT: extend the following prose for both new scopes, with the established reasoning | Task 2, Edit B |
| CONSTRAINT: existing contents:write / persist-credentials / fetch-depth prose survives untouched | Task 2, Edit B (explicit byte-identical instruction) + Task 2 verify's pre-existing-phrase assertions |
| CONSTRAINT: test asserts `permissions` is exactly the three keys, no more no less | Task 1 (equality against a module constant) |
| CONSTRAINT: explicitly forbid `actions: write` creeping in | Task 1 (equality rejects a fourth key) + Task 1 docstring + Task 2 prose + T-MNG-02 |
| CONSTRAINT: identify and correctly handle any hash/checksum drift check | Resolved during planning — no such check exists in the committed suite; see `<resolved_during_planning>` |
| CONSTRAINT: no changes to src/dark_factory/, pyproject.toml, scripts/scaffold_target_repo.py | Task 2 explicit out-of-scope list; `files_modified` is the two files only |
| FINDING (261030-mcz SUMMARY, option (a)): follow-up task adding the keys + extending the prose | This plan, in full |
</source_audit>

<verification>
1. `uv run pytest tests/unit/test_resume_workflow_reference_doc.py -q` → 14 passed (baseline was 13).
2. `uv run ruff check tests/unit/test_resume_workflow_reference_doc.py && uv run ruff format --check tests/unit/test_resume_workflow_reference_doc.py && uv run mypy tests/unit/test_resume_workflow_reference_doc.py` → all clean.
3. The sentinel block's parsed `permissions` mapping equals exactly `{contents: write, issues: write, pull-requests: write}` (Task 2 verify).
4. `git diff --stat` touches exactly `README.md` and `tests/unit/test_resume_workflow_reference_doc.py` — no src/, no pyproject.toml, no scripts/.
5. `git diff README.md` shows additions only inside the `permissions:` key region of the block plus one new prose paragraph; the `contents: write` and `fetch-depth: 0` paragraphs show no modified lines.
6. Guard direction spot-check (do not commit): temporarily add a fourth key to the block, confirm the new test fails, revert.
</verification>

<success_criteria>
- A deployer copying the README block gets a `resume.yml` whose token can push role work, post the WAITING_HUMAN clarification comment, and open the post-QA PR — no 403 on any of the three.
- The README path and the `scripts/scaffold_target_repo.py` path now agree on the permission scopes and explain them in the same words; 261030-mcz's unresolved finding is closed via its option (a).
- The gap cannot silently reappear: a committed test fails on under-scoping, on over-scoping, and on a `write-all` collapse.
- The pre-existing `contents: write` reasoning — persist-credentials, the two ordered failure modes, and the merge-base/fetch-depth analysis — survives verbatim.
</success_criteria>

<output>
Create `.planning/quick/261030-mng-fix-the-identical-permissions-gap-in-rea/261030-mng-SUMMARY.md` when done.
</output>
