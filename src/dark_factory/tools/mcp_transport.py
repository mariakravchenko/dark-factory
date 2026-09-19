"""``build_mcp_server`` -- the optional MCP transport exposing a role's
granted capabilities over the Model Context Protocol (D-12, D-13, D-15).

This is a minimal skeleton MCP adapter, not a full-featured server: enough
for a client -- in this phase, a test/fake in-memory client -- to list and
call a role's granted capabilities and observe the same deny-by-default
behaviour a direct :meth:`~dark_factory.tools.registry.ToolRegistry.invoke`
caller already gets. No session, no auth negotiation, and no real external
agent-runtime wiring lands this phase (Phase 7+) -- see
``tests/unit/test_no_worker_name_leak.py`` (WORK-03) for why this module
deliberately never names a specific runtime.

**One enforcement point, two transports.** Every tool closure this module
registers calls the exact same
:meth:`~dark_factory.tools.registry.ToolRegistry.invoke` the orchestrator's
own call sites use. ``granted_tools`` decides what to *advertise* -- the
tool names a client's ``list_tools()`` sees -- it is never consulted as a
permission source, and a closure must never pre-filter against it before
calling ``invoke``; the permission decision belongs to ``invoke()`` alone,
checked fresh on every call (threat T-06-03). The advertised list is a
convenience, never the enforcement boundary.

**Removability (ROADMAP SC5).** This module is importable only when the
optional ``mcp`` extra is installed (``pyproject.toml``'s
``[project.optional-dependencies] mcp`` group, D-13). **Nothing under
``src/dark_factory/`` may import this module** -- doing so would put a
third-party dependency on the orchestrator's core import closure.
``tests/unit/test_no_mcp_import_in_core.py`` (D-14, SC5) is the structural
guard proving that never happens; the install graph (this module living
behind an optional-dependencies group) is the other half of the same
removability claim.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dark_factory.tools import CapabilityDeniedError
from dark_factory.tools.registry import ToolRegistry

__all__ = ["MCP_SERVER_NAME_PREFIX", "build_mcp_server"]

MCP_SERVER_NAME_PREFIX = "dark-factory-"
"""Every per-role server built by :func:`build_mcp_server` is named
``f"{MCP_SERVER_NAME_PREFIX}{role}"``."""

_PATH_ARGUMENT_NAMES = frozenset({"root", "worktree", "cwd"})
"""The three keyword-argument names, shared across every registered
capability's implementation (``registry.py`` / ``env.py``), whose value is a
:class:`~pathlib.Path` rather than a JSON-native type. MCP arguments cross
the protocol boundary as JSON, which has no ``Path`` type -- a client-
supplied path always arrives as ``str`` -- so :func:`_coerce_path_arguments`
converts exactly these three names back to :class:`~pathlib.Path` before
forwarding to ``invoke``, and nothing else. This is the one piece of
capability-shape knowledge this otherwise-generic transport carries; it is
data marshalling for the JSON/Python boundary, never a permission decision,
and it does not special-case any individual *capability* -- only these
three cross-cutting *parameter names*."""


def _coerce_path_arguments(arguments: dict[str, object]) -> dict[str, object]:
    """Convert any ``str`` value under a name in :data:`_PATH_ARGUMENT_NAMES`
    back to a :class:`~pathlib.Path` -- see that constant's docstring for why
    this is necessary at all: an MCP argument is JSON, and JSON has no path
    type. A value that is already a :class:`~pathlib.Path` (never possible
    from a real JSON-RPC caller, but true of every direct in-process test
    call) passes through unchanged."""
    return {
        key: Path(value)
        if key in _PATH_ARGUMENT_NAMES and isinstance(value, str)
        else value
        for key, value in arguments.items()
    }


def build_mcp_server(
    role: str, granted_tools: Sequence[str], registry: ToolRegistry
) -> MCPServer:
    """Construct a fresh ``MCPServer`` advertising exactly ``granted_tools``
    for ``role`` (D-12, D-15).

    A new server is built on every call -- no module-level instance, no
    cache, and no mutable state carried between calls. Two successive calls
    with identical arguments return two distinct objects. One ``add_tool``
    closure is registered per name in ``granted_tools``; each closure's only
    job is to call ``registry.invoke(role, capability, granted_tools,
    **kwargs)`` and translate a denial into a legible :class:`ToolError` --
    it performs no permission logic of its own and must never pre-filter on
    ``granted_tools`` before calling ``invoke`` (threat T-06-03): a second,
    silent enforcement point here would make its disagreement with
    ``invoke()`` invisible.

    The loop variable ``capability`` is bound by value once per iteration --
    Python's late-binding closure semantics would otherwise make every
    registered tool dispatch to the *last* value of the loop (RESEARCH
    Pitfall 1); a role granted two or more capabilities is the regression
    this guards against. The binding happens one level removed from the
    function actually registered with ``add_tool``: a per-iteration
    ``_make_tool(*, _capability: str = capability)`` factory captures the
    current loop value as its own default argument (default values are
    evaluated at ``def``-time, so each loop pass's fresh ``def`` freezes
    that pass's ``capability``), then returns the real ``_tool`` closure,
    which reads ``_capability`` from its enclosing ``_make_tool`` call
    rather than exposing it as one of its own parameters. This indirection
    is required, not stylistic: the MCP SDK's schema generator rejects any
    parameter name starting with ``_`` on the function actually passed to
    ``add_tool`` (``InvalidSignature: ... cannot start with '_'``, verified
    against a real ``MCPServer`` this session) -- binding directly on
    ``_tool`` the way a single-level default-argument trick would is not
    possible with this SDK version, and binding on a *non*-underscored,
    client-visible parameter of ``_tool`` would let a caller override which
    capability a tool name actually invokes, defeating the whole per-name
    binding. ``role``, ``registry`` and ``granted_tools`` are the
    *enclosing* ``build_mcp_server`` call's parameters, not loop variables,
    so they need no such binding -- they are the same object on every
    iteration by construction.

    Each tool accepts a single optional ``arguments`` object (a JSON object
    forwarded as ``**kwargs`` to ``invoke``, after :func:`_coerce_path_arguments`
    runs on it) rather than a bare ``**kwargs`` closure parameter: the SDK's
    auto-generated JSON Schema treats a literal ``**kwargs: object``
    signature as one *required* property named ``"kwargs"``, not as "accept
    arbitrary named properties" -- confirmed against a real ``MCPServer``
    instance this session (RESEARCH's Pattern 3 sketch, read literally, does
    not forward a capability's real keyword arguments the way it appears
    to). Wrapping them in a single ``arguments`` object gives every
    capability -- each with its own distinct keyword-argument shape -- one
    uniform, correctly forwarding tool signature, without
    ``build_mcp_server`` needing to know any capability's individual
    parameter *names* -- with exactly one narrow exception: three parameter
    names (``root``, ``worktree``, ``cwd``) are shared *by convention*
    across every capability implementation as the run-tree-relative
    :class:`~pathlib.Path` a call operates under, and JSON has no path type
    to carry that intent across the protocol boundary. Without
    :func:`_coerce_path_arguments`, every path-taking capability
    (``artifacts.read``/``artifacts.write``/``repo.read``/``repo.search``/
    ``repo.write``/``repo.write_tests``/``shell.execute``) would receive a
    bare ``str`` where its implementation calls ``root / relative_path``
    and crash with ``TypeError`` -- discovered empirically this session by
    driving ``artifacts.write`` through this exact transport.

    A :class:`~dark_factory.tools.CapabilityDeniedError` raised inside
    ``invoke()`` is caught here and re-raised as :class:`ToolError` --
    letting it fall through uncaught would surface to an MCP client as an
    opaque ``Error executing tool <name>`` with no reason, discarding
    exactly the "who tried what and was denied why" audit answer the
    denial exists to provide (threat T-06-17). No other exception is caught
    or reshaped.
    """
    server = MCPServer(name=f"{MCP_SERVER_NAME_PREFIX}{role}")
    for capability in granted_tools:

        def _make_tool(*, _capability: str = capability) -> Callable[..., object]:
            def _tool(arguments: dict[str, object] | None = None) -> object:
                try:
                    return registry.invoke(
                        role,
                        _capability,
                        granted_tools,
                        **_coerce_path_arguments(arguments or {}),
                    )
                except CapabilityDeniedError as exc:
                    raise ToolError(str(exc)) from exc

            return _tool

        server.add_tool(
            _make_tool(),
            name=capability,
            description=f"Dark Factory capability: {capability}",
        )
    return server
