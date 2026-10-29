#!/usr/bin/env python3
"""Scaffold a Dark Factory configuration tree into a target repository.

This is a standalone developer tool deliberately kept outside the shipped
``dark_factory`` package: it is not a ``dark-factory`` CLI subcommand, is not
installed by ``pip install dark-factory``, and is run from a checkout of
*this* repository (``uv run python scripts/scaffold_target_repo.py ...``).

It writes thirteen files: the twelve steps 2 and 3 of README's "deployment
model" describe a deployer hand-authoring -- ``.dark-factory.yaml``, the
four role YAMLs under ``.dark-factory/roles/``, the four instruction
Markdown files under ``.dark-factory/instructions/``, ``.env.example``,
``.github/workflows/resume.yml``, and ``.gitignore`` -- plus a thirteenth,
``.github/workflows/run.yml``, a second generated workflow that starts a
run in CI the same way the resume one finishes one. All thirteen are
parameterized by GitHub owner/repo, base branch, per-role worker
assignment, and quality-gate commands.

Nothing under ``src/dark_factory/`` is imported or touched; this module uses
only the standard library plus PyYAML, which it uses solely to *parse-check*
what it has already written (never ``yaml.dump``, since the templates below
carry explanatory comments a dumper would silently delete).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

__all__ = ["main"]

# ---------------------------------------------------------------------------
# Fixed vocabulary
# ---------------------------------------------------------------------------

ROLE_ORDER = ("BA", "ARCHITECTURE", "DEVELOPMENT", "QA")

ROLE_LOWERCASE = {
    "BA": "ba",
    "ARCHITECTURE": "architecture",
    "DEVELOPMENT": "development",
    "QA": "qa",
}

ROLE_WRITE_SCOPE: dict[str, tuple[str, ...]] = {
    "BA": (),
    "ARCHITECTURE": (),
    "DEVELOPMENT": ("src/**",),
    "QA": ("tests/**",),
}

DEFAULT_QUALITY_GATE_COMMANDS = ("uv run pytest -q", "uv run ruff check .")

DEFAULT_INSTALL_SOURCE = "dark-factory"
DEFAULT_WORKER = "claude-code"
DEFAULT_BASE_BRANCH = "main"

REPO_CONFIG_RELATIVE_PATH = ".dark-factory.yaml"
ENV_EXAMPLE_RELATIVE_PATH = ".env.example"
RESUME_WORKFLOW_RELATIVE_PATH = ".github/workflows/resume.yml"
RUN_WORKFLOW_RELATIVE_PATH = ".github/workflows/run.yml"
GITIGNORE_RELATIVE_PATH = ".gitignore"


def _role_yaml_relative_path(role: str) -> str:
    return f".dark-factory/roles/{role}.yaml"


def _instruction_relative_path(role: str) -> str:
    return f".dark-factory/instructions/{ROLE_LOWERCASE[role]}.md"


# ---------------------------------------------------------------------------
# Templates -- text substitution on {{TOKEN}} markers, never yaml.dump (DD-3)
# ---------------------------------------------------------------------------

DARK_FACTORY_YAML_TEMPLATE = """\
# Dark Factory repo behaviour. Read once per run, at creation; the resolved
# effective-config snapshot is persisted on the run and is what every resume
# replays -- editing this file never changes an in-flight run. No secrets
# here: infrastructure credentials live in .env.
version: 1

repository:
  base_branch: {{BASE_BRANCH}}
  github_owner: {{GITHUB_OWNER}}
  github_repo: {{GITHUB_REPO}}

workflow:
  roles: [BA, ARCHITECTURE, DEVELOPMENT, QA]

roles_dir: .dark-factory/roles

quality_gate:
  commands:
{{QUALITY_GATE_COMMANDS}}

retry:
  qa_developer_max_iterations: 3
  quality_gate_max_iterations: 2

publishing:
  create_pr: true
"""

ROLE_YAML_TEMPLATES: dict[str, str] = {
    "BA": """\
# Business Analyst role definition. Editing this file changes the resolved
# role in the next run's snapshot with no Python change.
name: BA
worker: {{WORKER}}
instructions: ../instructions/ba.md

tools: [repo.read, repo.search, artifacts.read, artifacts.write]
# BA is read-only with respect to repository source code -- zero tolerance,
# any changed path at all is a violation.
permissions:
  write_scope: []

before: [ensure_clean_worktree]
after: []

inputs: []
outputs: [requirements.md, acceptance_criteria.json]
examples: []
""",
    "ARCHITECTURE": """\
# Architect role definition. Editing this file changes the resolved role in
# the next run's snapshot with no Python change.
name: ARCHITECTURE
worker: {{WORKER}}
instructions: ../instructions/architecture.md

tools: [repo.read, repo.search, artifacts.read, artifacts.write]
# ARCHITECTURE is read-only with respect to repository source code -- zero
# tolerance, any changed path at all is a violation.
permissions:
  write_scope: []

before: [ensure_clean_worktree]
after: []

inputs: [acceptance_criteria.json]
outputs: [design.md, constraints.json]
examples: []
""",
    "DEVELOPMENT": """\
# Developer role definition. Editing this file changes the resolved role in
# the next run's snapshot with no Python change.
name: DEVELOPMENT
worker: {{WORKER}}
instructions: ../instructions/development.md

tools:
  [
    repo.read,
    repo.search,
    repo.write,
    repo.write_tests,
    shell.execute,
    artifacts.read,
    artifacts.write,
  ]
# Developer may write anywhere under src/ -- production code, not tests.
permissions:
  write_scope: ["src/**"]

before: [ensure_clean_worktree]
after: [collect_diff]

inputs: [design.md, constraints.json]
# Feedback-loop artifacts: verdict.json carries QA's structured issues on a
# QA-FAIL bounce; quality_gate.json carries the gate's real command output on
# a gate-FAIL bounce. Both are absent on the first attempt.
optional_inputs: [verdict.json, quality_gate.json]
outputs: [implementation_summary.json]
examples: []
""",
    "QA": """\
# QA role definition.
name: QA
worker: {{WORKER}}
instructions: ../instructions/qa.md

# QA writes tests, never production source -- repo.write stays absent, which
# is the "cannot publish" half of its contract.
tools:
  [
    repo.read,
    repo.search,
    repo.write_tests,
    shell.execute,
    artifacts.read,
    artifacts.write,
  ]
# QA may write only under tests/ -- fixtures and test utilities, never
# production code.
permissions:
  write_scope: ["tests/**"]

before: [ensure_clean_worktree]
after: [collect_test_results, collect_diff]

inputs: [acceptance_criteria.json, implementation_summary.json]
outputs: [test_report.json, verdict.json]
examples: []
""",
}

ENV_EXAMPLE_TEMPLATE = """\
# {{GITHUB_REPO}} -- environment variable reference for running Dark Factory
# against this repository. Copy this file to `.env` and fill in real values.
# `.env` is git-ignored -- never commit it, never paste real values here.

# --- Dark Factory's own run-state database (your Neon project) -------------

# Pooled Neon connection string (host contains "-pooler") -- used by the
# application at runtime. Rewrite the scheme to postgresql+psycopg://.
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@ep-example-000000-pooler.us-east-2.aws.neon.tech/dbname

# Direct (non-pooled) Neon connection string (host WITHOUT "-pooler") -- used
# by Alembic only, because DDL and PgBouncer transaction pooling do not mix.
DATABASE_URL_DIRECT=postgresql+psycopg://USER:PASSWORD@ep-example-000000.us-east-2.aws.neon.tech/dbname

# --- GitHub credentials -----------------------------------------------------

# Dark Factory's own comment/PR credential. Needs: read issues/comments,
# write issue comments, create pull requests, push to branches on this repo.
# Classic PAT with `repo` scope, or a fine-grained PAT scoped to this repo
# with Contents (read/write), Issues (read/write), and Pull requests
# (read/write) permissions.
GITHUB_TOKEN=

# Dispatch-only credential, used ONLY by the webhook receiver to trigger
# resume.yml via workflow_dispatch after a human's answer is recorded.
# Fine-grained PAT scoped to THIS repo only, "Actions: Read and write"
# permission -- nothing else. Deliberately separate from GITHUB_TOKEN above.
DISPATCH_GITHUB_TOKEN=

# Shared secret configured on this repo's webhook (GitHub repo Settings ->
# Webhooks -> your webhook -> Secret). Used to verify inbound deliveries are
# genuinely from GitHub before anything is parsed.
GITHUB_WEBHOOK_SECRET=

# --- Worker runtime credential(s) -------------------------------------------

{{WORKER_CREDENTIALS}}
# --- Optional -----------------------------------------------------------

LOG_LEVEL=INFO
"""

RESUME_WORKFLOW_TEMPLATE = """\
name: resume

"on":
  workflow_dispatch:
    inputs:
      run_id:
        description: "The Dark Factory run id to resume"
        required: true
        type: string

permissions:
  contents: write

jobs:
  resume:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install dark-factory
        run: pip install "{{INSTALL_SOURCE}}"

      # - name: Install the worker runtime
      #   # Required whenever a role is assigned to a worker that shells out
      #   # to a CLI binary -- see the "worker runtime" table your README
      #   # documents for the binary name your roles need on PATH. The
      #   # install command itself comes from that runtime's own
      #   # documentation: Dark Factory neither ships nor verifies it.
      #   run: <install your worker runtime's CLI here, per its own docs>

      - name: Resume the run
        run: dark-factory resume "${{ inputs.run_id }}"
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          DATABASE_URL_DIRECT: ${{ secrets.DATABASE_URL_DIRECT }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
{{WORKER_CREDENTIAL_ENV}}
"""

RUN_WORKFLOW_TEMPLATE = """\
name: run

"on":
  workflow_dispatch:
    inputs:
      source:
        description: "The source to run: a text: string, a spec: file path, or a github: issue number"
        required: true
        type: string

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install dark-factory
        run: pip install "{{INSTALL_SOURCE}}"

      # - name: Install the worker runtime
      #   # Required whenever a role is assigned to a worker that shells out
      #   # to a CLI binary -- see the "worker runtime" table your README
      #   # documents for the binary name your roles need on PATH. The
      #   # install command itself comes from that runtime's own
      #   # documentation: Dark Factory neither ships nor verifies it.
      #   run: <install your worker runtime's CLI here, per its own docs>

      - name: Start the run
        run: dark-factory run "${{ inputs.source }}"
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          DATABASE_URL_DIRECT: ${{ secrets.DATABASE_URL_DIRECT }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
{{WORKER_CREDENTIAL_ENV}}
"""

GITIGNORE_CONTENT = """\
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.dark-factory/runs/
.DS_Store
"""


# ---------------------------------------------------------------------------
# Render functions -- pure, no I/O
# ---------------------------------------------------------------------------


def _render_quality_gate_commands(commands: tuple[str, ...]) -> str:
    lines = [f'    - "{command}"' for command in commands]
    return "\n".join(lines)


def render_dark_factory_yaml(
    *,
    base_branch: str,
    github_owner: str,
    github_repo: str,
    quality_gate_commands: tuple[str, ...],
) -> str:
    text = DARK_FACTORY_YAML_TEMPLATE
    text = text.replace("{{BASE_BRANCH}}", base_branch)
    text = text.replace("{{GITHUB_OWNER}}", github_owner)
    text = text.replace("{{GITHUB_REPO}}", github_repo)
    text = text.replace(
        "{{QUALITY_GATE_COMMANDS}}",
        _render_quality_gate_commands(quality_gate_commands),
    )
    return text


def render_role_yaml(role: str, worker: str) -> str:
    return ROLE_YAML_TEMPLATES[role].replace("{{WORKER}}", worker)


def _instructions_source_dir() -> Path:
    """``.dark-factory/instructions/`` in *this* repository (DD-1)."""
    return Path(__file__).resolve().parents[1] / ".dark-factory" / "instructions"


def _write_scope_section(write_scope: tuple[str, ...]) -> str:
    """The generated trailing section appended to each copied instruction
    file (DD-2), naming the role's actual resolved write-scope patterns."""
    if not write_scope:
        body = (
            "This role is read-only with respect to repository source: any "
            "changed path at all is a violation that is reverted and fails "
            "this role's attempt."
        )
    else:
        patterns = ", ".join(f"`{pattern}`" for pattern in write_scope)
        body = (
            f"This role may write only under: {patterns}. Any changed path "
            "outside these patterns is a violation that is reverted and "
            "fails this role's attempt."
        )
    return f"\n\n## Write-scope enforcement (generated)\n\n{body}\n"


def render_instruction_file(role: str) -> str:
    """Read this repository's own instruction prose for ``role`` and append
    a generated write-scope section (DD-1, DD-2).

    Exits non-zero naming the missing path if the source file is absent --
    never falls back to invented prose.
    """
    source_path = _instructions_source_dir() / f"{ROLE_LOWERCASE[role]}.md"
    if not source_path.is_file():
        print(
            f"ERROR: instruction source file not found: {source_path}", file=sys.stderr
        )
        raise SystemExit(1)
    text = source_path.read_text("utf-8")
    return text + _write_scope_section(ROLE_WRITE_SCOPE[role])


def render_worker_credentials_block(role_workers: dict[str, str]) -> str:
    """The ``.env.example`` worker-runtime section (DD-5): one entry per
    distinct credential env var, each with a comment naming which roles
    need it."""
    var_to_roles: dict[str, list[str]] = {}
    for role in ROLE_ORDER:
        worker = role_workers[role]
        var = WORKER_CREDENTIAL_ENV_VAR[worker]
        var_to_roles.setdefault(var, []).append(f"{role} ({worker})")
    blocks = []
    for var in sorted(var_to_roles):
        roles_desc = ", ".join(var_to_roles[var])
        blocks.append(f"# Required by: {roles_desc}.\n{var}=")
    return "\n\n".join(blocks) + "\n"


def render_env_example(*, github_repo: str, role_workers: dict[str, str]) -> str:
    text = ENV_EXAMPLE_TEMPLATE
    text = text.replace("{{GITHUB_REPO}}", github_repo)
    text = text.replace(
        "{{WORKER_CREDENTIALS}}", render_worker_credentials_block(role_workers)
    )
    return text


def render_worker_credential_env_block(role_workers: dict[str, str]) -> str:
    """The extra ``env:`` entries in the generated ``resume.yml`` (DD-5),
    the union of credential env vars over the four resolved workers."""
    var_names = sorted(
        {WORKER_CREDENTIAL_ENV_VAR[worker] for worker in role_workers.values()}
    )
    lines = [f"          {var}: " + "${{ secrets." + var + " }}" for var in var_names]
    return "\n".join(lines)


def render_resume_workflow(*, install_source: str, role_workers: dict[str, str]) -> str:
    text = RESUME_WORKFLOW_TEMPLATE
    text = text.replace("{{INSTALL_SOURCE}}", install_source)
    text = text.replace(
        "{{WORKER_CREDENTIAL_ENV}}", render_worker_credential_env_block(role_workers)
    )
    return text


def render_run_workflow(*, install_source: str, role_workers: dict[str, str]) -> str:
    text = RUN_WORKFLOW_TEMPLATE
    text = text.replace("{{INSTALL_SOURCE}}", install_source)
    text = text.replace(
        "{{WORKER_CREDENTIAL_ENV}}", render_worker_credential_env_block(role_workers)
    )
    return text


# WORKER_CREDENTIAL_ENV_VAR is defined after the render functions above read
# it so every call site below sees the same module-level mapping (DD-5):
# claude-code and hermes both read ANTHROPIC_API_KEY (hermes has no
# dedicated credential of its own -- HERMES_CREDENTIAL_ENV_VAR is the same
# constant), copilot reads COPILOT_CREDENTIAL_ENV_VAR.
WORKER_CREDENTIAL_ENV_VAR: dict[str, str] = {
    "claude-code": "ANTHROPIC_API_KEY",
    "copilot": "COPILOT_GITHUB_TOKEN",
    "hermes": "ANTHROPIC_API_KEY",
}

LEGAL_WORKERS: tuple[str, ...] = tuple(sorted(WORKER_CREDENTIAL_ENV_VAR))


def build_contents(
    *,
    base_branch: str,
    github_owner: str,
    github_repo: str,
    quality_gate_commands: tuple[str, ...],
    role_workers: dict[str, str],
    install_source: str,
) -> dict[str, str]:
    """Render every output file's content, keyed by its path relative to the
    target repository root. Exits non-zero (via ``render_instruction_file``)
    before any content is returned if an instruction source file is
    missing -- nothing is written in that case.
    """
    contents: dict[str, str] = {
        REPO_CONFIG_RELATIVE_PATH: render_dark_factory_yaml(
            base_branch=base_branch,
            github_owner=github_owner,
            github_repo=github_repo,
            quality_gate_commands=quality_gate_commands,
        ),
    }
    for role in ROLE_ORDER:
        contents[_role_yaml_relative_path(role)] = render_role_yaml(
            role, role_workers[role]
        )
    for role in ROLE_ORDER:
        contents[_instruction_relative_path(role)] = render_instruction_file(role)
    contents[ENV_EXAMPLE_RELATIVE_PATH] = render_env_example(
        github_repo=github_repo, role_workers=role_workers
    )
    contents[RESUME_WORKFLOW_RELATIVE_PATH] = render_resume_workflow(
        install_source=install_source, role_workers=role_workers
    )
    contents[RUN_WORKFLOW_RELATIVE_PATH] = render_run_workflow(
        install_source=install_source, role_workers=role_workers
    )
    contents[GITIGNORE_RELATIVE_PATH] = GITIGNORE_CONTENT
    return contents


_YAML_CHECK_RELATIVE_PATHS = (
    REPO_CONFIG_RELATIVE_PATH,
    *[_role_yaml_relative_path(role) for role in ROLE_ORDER],
    RESUME_WORKFLOW_RELATIVE_PATH,
    RUN_WORKFLOW_RELATIVE_PATH,
)


def parse_check(target_root: Path) -> None:
    """Parse-check the emitted YAML files with ``yaml.safe_load``; fail
    loudly if any does not parse as a mapping."""
    for relative_path in _YAML_CHECK_RELATIVE_PATHS:
        path = target_root / relative_path
        data = yaml.safe_load(path.read_text("utf-8"))
        if not isinstance(data, dict):
            print(
                f"ERROR: {path} did not parse as a mapping (got {type(data).__name__})",
                file=sys.stderr,
            )
            raise SystemExit(1)


def _gitignore_missing_entries(existing_text: str, template_text: str) -> list[str]:
    """Template entries absent from an already-existing ``.gitignore`` (DD-7
    extension): a deployer with a real ``.gitignore`` learns what to add by
    hand rather than being told only that the file was skipped."""
    existing_lines = {
        line.strip() for line in existing_text.splitlines() if line.strip()
    }
    return [
        line.strip()
        for line in template_text.splitlines()
        if line.strip() and line.strip() not in existing_lines
    ]


def write_output_file(path: Path, text: str, *, force: bool) -> str:
    """Write ``text`` to ``path``, returning ``"created"``, ``"overwritten"``
    or ``"skipped (exists)"`` (DD-7). Never clobbers an existing file unless
    ``force`` is set."""
    existed = path.is_file()
    if existed and not force:
        return "skipped (exists)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "overwritten" if existed else "created"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Dark Factory configuration tree (.dark-factory.yaml, "
            "role YAMLs, instruction files, .env.example, resume.yml, "
            "run.yml, .gitignore) in a target repository. A standalone "
            "developer tool: not a dark-factory CLI subcommand."
        ),
    )
    parser.add_argument(
        "--target", required=True, type=Path, help="Target repository root directory"
    )
    parser.add_argument("--github-owner", default=None, help="GitHub repository owner")
    parser.add_argument("--github-repo", default=None, help="GitHub repository name")
    parser.add_argument(
        "--base-branch",
        default=DEFAULT_BASE_BRANCH,
        help="Base branch recorded in repository:",
    )
    parser.add_argument(
        "--worker",
        default=DEFAULT_WORKER,
        help=f"Default worker for all four roles (legal values: {', '.join(LEGAL_WORKERS)})",
    )
    parser.add_argument("--worker-ba", default=None, help="Per-role override for BA")
    parser.add_argument(
        "--worker-architecture", default=None, help="Per-role override for ARCHITECTURE"
    )
    parser.add_argument(
        "--worker-development", default=None, help="Per-role override for DEVELOPMENT"
    )
    parser.add_argument("--worker-qa", default=None, help="Per-role override for QA")
    parser.add_argument(
        "--quality-gate-command",
        dest="quality_gate_command",
        action="append",
        default=None,
        help="Repeatable; defaults to this repository's own uv/ruff pair when omitted",
    )
    parser.add_argument(
        "--install-source",
        default=DEFAULT_INSTALL_SOURCE,
        help="pip install target the generated resume.yml and run.yml workflows install",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files instead of skipping them",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Suppress interactive prompting; requires --github-*",
    )
    return parser


def _resolve_github_locator(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve ``--github-owner``/``--github-repo``, prompting interactively
    when one is absent and stdin is a TTY, or exiting non-zero naming the
    missing flag otherwise -- every automated invocation stays
    non-interactive."""
    owner = args.github_owner
    repo = args.github_repo
    if owner and repo:
        return owner, repo

    missing_flag = "--github-owner" if not owner else "--github-repo"
    if args.yes:
        print(f"ERROR: {missing_flag} is required when --yes is set", file=sys.stderr)
        raise SystemExit(1)
    if not sys.stdin.isatty():
        print(
            f"ERROR: {missing_flag} is required when stdin is not a TTY",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not owner:
        owner = input("GitHub owner: ").strip()
    if not repo:
        repo = input("GitHub repo: ").strip()
    if not owner or not repo:
        print(
            "ERROR: both --github-owner and --github-repo are required", file=sys.stderr
        )
        raise SystemExit(1)
    return owner, repo


def _resolve_role_workers(args: argparse.Namespace) -> dict[str, str]:
    """Resolve each role's worker from its per-role override or the shared
    ``--worker`` default, then validate every resolved value against the
    three legal names (DD-6). Never offers the registry's ``fake`` worker."""
    overrides = {
        "BA": args.worker_ba,
        "ARCHITECTURE": args.worker_architecture,
        "DEVELOPMENT": args.worker_development,
        "QA": args.worker_qa,
    }
    resolved = {role: overrides[role] or args.worker for role in ROLE_ORDER}
    bad = sorted(
        {worker for worker in resolved.values() if worker not in LEGAL_WORKERS}
    )
    if bad:
        print(
            f"ERROR: unrecognised worker name(s) {bad!r}; legal worker values "
            f"are {list(LEGAL_WORKERS)!r}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # T-OD8-02: --target is resolved exactly once; every output path below is
    # that resolved root joined with a fixed relative-path constant from a
    # closed set -- never a caller-supplied sub-path.
    target_root = args.target.expanduser().resolve()

    github_owner, github_repo = _resolve_github_locator(args)
    role_workers = _resolve_role_workers(args)
    quality_gate_commands = tuple(
        args.quality_gate_command or DEFAULT_QUALITY_GATE_COMMANDS
    )

    contents = build_contents(
        base_branch=args.base_branch,
        github_owner=github_owner,
        github_repo=github_repo,
        quality_gate_commands=quality_gate_commands,
        role_workers=role_workers,
        install_source=args.install_source,
    )

    any_skipped = False
    for relative_path, text in contents.items():
        output_path = target_root / relative_path
        if (
            relative_path == GITIGNORE_RELATIVE_PATH
            and output_path.is_file()
            and not args.force
        ):
            missing = _gitignore_missing_entries(output_path.read_text("utf-8"), text)
            if missing:
                print("NOTE: existing .gitignore is missing these template entries:")
                for line in missing:
                    print(f"  {line}")
        status = write_output_file(output_path, text, force=args.force)
        print(f"{status}: {relative_path}")
        if status == "skipped (exists)":
            any_skipped = True

    parse_check(target_root)

    if any_skipped:
        print(
            "Some files already existed and were left untouched. Pass --force to overwrite them."
        )
    print(f"Scaffold written to {target_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
