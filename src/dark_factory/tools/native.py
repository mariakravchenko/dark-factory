"""The D-02 native-tool translation contract, as typed data.

This module is the **design contract** D-02 promises -- concrete enough that
Phase 7 (the ``claude-code`` adapter) and Phase 8 (``copilot`` / ``hermes``)
implement the per-worker native-tool restriction *from* it, instead of
re-deriving the mapping from first principles. As of Phase 7 (plan 07-04),
:mod:`dark_factory.workers.claude_code` is its **first real runtime
consumer**: ``ClaudeCodeWorker`` builds its ``--allowedTools`` argv element
from :data:`NATIVE_TOOL_CONTRACT`'s capability vocabulary.
``tests/unit/test_native_tool_contract.py`` no longer proves total
inertness -- it guards an explicit consumer allowlist (``_ALLOWED_CONSUMERS``)
instead, so a *new* consumer must still be added to that allowlist
deliberately, never silently.

The boundary D-02 draws, stated plainly: :class:`~dark_factory.tools.registry.ToolRegistry`
governs Dark-Factory-initiated calls (``orchestrator/runner.py``'s own
``artifacts.read`` call site) and, once a later plan adds a transport, calls a
worker routes *through Dark Factory*. It cannot intercept an external agent
CLI's own native filesystem or shell tools -- a Claude Code / Copilot / Hermes
process invoked as a subprocess reads and writes files with its own tools,
outside any Python call `invoke()` could gate. That is precisely why a
per-adapter **native** restriction must be derived from the same ``tools:``
grants this registry enforces: the grant is the single source of truth for
"may this role do X"; the *mechanism* differs depending on whether X happens
through Dark Factory (gated by :meth:`~dark_factory.tools.registry.ToolRegistry.invoke`)
or through the worker's own CLI (gated by whatever native flag the adapter
passes at spawn time, translated from this table).

Values are drawn from ``CLAUDE.md``'s "Invoking the agent CLIs" table: Claude
Code restricts via ``--allowedTools`` (worktree confinement coming from the
subprocess ``cwd``, not from ``--permission-mode`` -- see
:data:`WORKTREE_CONFINEMENT_NOTE`); Copilot CLI via narrow, repeated
``--allow-tool`` values (never ``--allow-all-tools``); Hermes documents no
per-tool native restriction flag at all, so its entries say that honestly
rather than inventing one -- an adapter that cannot enforce a restriction
natively must not claim that it can.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

__all__ = ["NATIVE_TOOL_CONTRACT", "WORKTREE_CONFINEMENT_NOTE", "NativeToolGrant"]

WORKTREE_CONFINEMENT_NOTE = (
    "Worktree confinement is a property of the subprocess working directory "
    "(cwd=<worktree>) the adapter sets at spawn -- not of any "
    "approval-policy flag."
)


class NativeToolGrant(BaseModel):
    """One capability's native-tool translation, per worker runtime.

    ``claude_code`` / ``copilot`` / ``hermes`` name the native flag fragment
    a Phase 7+ adapter emits at spawn time when the role **holds** this
    grant. ``absent_behaviour`` states what the adapter must do when the
    role does **not** hold it -- the deny half a translation table normally
    forgets, and the half that actually keeps a worker inside its
    configured boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: str
    claude_code: str
    copilot: str
    hermes: str
    absent_behaviour: str


NATIVE_TOOL_CONTRACT: Mapping[str, NativeToolGrant] = {
    "repo.read": NativeToolGrant(
        capability="repo.read",
        claude_code=f"--allowedTools 'Read,Glob'. {WORKTREE_CONFINEMENT_NOTE}",
        copilot="a narrow --allow-tool 'read' entry (never --allow-all-tools)",
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce a read restriction natively and must not claim "
            "that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: omit the read tool from "
            "--allowedTools/--allow-tool entirely, so the CLI itself refuses "
            "the read. Hermes: since there is no native enforcement "
            "mechanism, the adapter must not spawn Hermes for a role denied "
            "this grant at all -- there is no flag to fall back to."
        ),
    ),
    "repo.search": NativeToolGrant(
        capability="repo.search",
        claude_code=f"--allowedTools 'Grep,Glob'. {WORKTREE_CONFINEMENT_NOTE}",
        copilot="a narrow --allow-tool 'read' entry covering search (Copilot has no separate search tool)",
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce a search restriction natively and must not "
            "claim that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: omit Grep/Glob (or the search-capable "
            "read tool) from the allow-list. Hermes: the adapter must not "
            "spawn Hermes for a role denied this grant."
        ),
    ),
    "repo.write": NativeToolGrant(
        capability="repo.write",
        claude_code=f"--allowedTools 'Write,Edit'. {WORKTREE_CONFINEMENT_NOTE}",
        copilot="a narrow --allow-tool 'write' entry (never --allow-all-tools)",
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce a write restriction natively and must not claim "
            "that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: omit Write/Edit from the allow-list "
            "entirely, so the CLI itself refuses the write. Hermes: the "
            "adapter must not spawn Hermes for a role denied this grant."
        ),
    ),
    "repo.write_tests": NativeToolGrant(
        capability="repo.write_tests",
        claude_code=(
            "the identical --allowedTools 'Write,Edit' fragment as "
            "repo.write -- Claude Code has no native path-scoped write "
            "flag, so the adapter must also pass a prompt-level instruction "
            "restricting edits to test paths; write_scope (ROLE-05) still "
            f"enforces the boundary post-hoc regardless. {WORKTREE_CONFINEMENT_NOTE}"
        ),
        copilot=(
            "the identical narrow --allow-tool 'write' entry as repo.write "
            "-- Copilot has no native path-scoped write flag either"
        ),
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce a write restriction natively and must not claim "
            "that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: omit Write/Edit from the allow-list "
            "entirely. Hermes: the adapter must not spawn Hermes for a "
            "role denied this grant."
        ),
    ),
    "shell.execute": NativeToolGrant(
        capability="shell.execute",
        claude_code=f"--allowedTools 'Bash'. {WORKTREE_CONFINEMENT_NOTE}",
        copilot="a narrow --allow-tool 'shell(<command>)' entry per allowed command (never --allow-all-tools)",
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce an execution restriction natively and must not "
            "claim that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: omit Bash/shell(...) from the "
            "allow-list entirely, so the CLI itself refuses to execute a "
            "command. Hermes: the adapter must not spawn Hermes for a role "
            "denied this grant."
        ),
    ),
    "artifacts.read": NativeToolGrant(
        capability="artifacts.read",
        claude_code=(
            "--allowedTools "
            "'Read(.dark-factory/runs/<run_id>/artifacts/**)' -- a "
            "path-scoped rule specifier over the run's artifacts subtree, "
            "not a bare Read grant; a real worker reads a prior role's "
            "artifact content with its own native read tool, not through "
            f"Dark Factory. {WORKTREE_CONFINEMENT_NOTE}"
        ),
        copilot="a narrow --allow-tool 'read' entry, same scope as Claude Code",
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce a read restriction natively and must not claim "
            "that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: exclude the artifacts subtree from the "
            "read tool's scope entirely. Hermes: the adapter must not "
            "spawn Hermes for a role denied this grant."
        ),
    ),
    "artifacts.write": NativeToolGrant(
        capability="artifacts.write",
        claude_code=(
            "--allowedTools 'Edit(.dark-factory/runs/<run_id>/"
            "artifacts/<role>/**)' -- a path-scoped rule specifier over "
            "the run's own artifacts/<role>/ subtree, not a bare Write/Edit "
            "grant; a real worker writes its own declared output files "
            "with its own native write tool, not through Dark Factory; the "
            "orchestrator-mediated ToolRegistry.invoke('artifacts.write', "
            "...) path exists for a future transport a worker calls back "
            f"into Dark Factory over. {WORKTREE_CONFINEMENT_NOTE}"
        ),
        copilot="a narrow --allow-tool 'write' entry, same scope as Claude Code",
        hermes=(
            "no documented per-tool native restriction flag -- the adapter "
            "cannot enforce a write restriction natively and must not "
            "claim that it can"
        ),
        absent_behaviour=(
            "Claude Code / Copilot: exclude the artifacts subtree from the "
            "write tool's scope entirely. Hermes: the adapter must not "
            "spawn Hermes for a role denied this grant."
        ),
    ),
}
