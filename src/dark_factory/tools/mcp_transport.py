"""``build_mcp_server`` -- the optional MCP transport exposing a role's
granted capabilities over the Model Context Protocol (D-12, D-13, D-15).

RED placeholder (TDD, plan 06-03 Task 2): this is RESEARCH's Pattern 3
sketch, followed literally, before this session's empirical falsification
of two of its assumptions. It fails to satisfy ``tests/unit/test_mcp_adapter.py``
for two independent, verified reasons:

1. ``add_tool`` rejects any leading-underscore parameter name on the
   function it inspects (``InvalidSignature: ... cannot start with '_'``),
   so the literal ``_capability: str = capability`` default-argument bind
   crashes at registration time rather than fixing the late-binding
   pitfall it targets.
2. A literal ``**kwargs: object`` closure parameter is schema'd by the SDK
   as one *required* property literally named ``"kwargs"``, not as "accept
   arbitrary named properties" -- it does not forward a capability's real
   keyword arguments the way it appears to.

See the module's GREEN version (this same file, Task 2's ``feat`` commit)
for the fix: a per-iteration factory function binds the loop variable
one level removed from the function actually passed to ``add_tool``, and
each tool accepts a single ``arguments`` object instead of ``**kwargs``.
"""

from __future__ import annotations

from collections.abc import Sequence

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dark_factory.tools import CapabilityDeniedError
from dark_factory.tools.registry import ToolRegistry

__all__ = ["MCP_SERVER_NAME_PREFIX", "build_mcp_server"]

MCP_SERVER_NAME_PREFIX = "dark-factory-"


def build_mcp_server(
    role: str, granted_tools: Sequence[str], registry: ToolRegistry
) -> MCPServer:
    server = MCPServer(name=f"{MCP_SERVER_NAME_PREFIX}{role}")
    for capability in granted_tools:

        def _tool(_capability: str = capability, **kwargs: object) -> object:
            try:
                return registry.invoke(role, _capability, granted_tools, **kwargs)
            except CapabilityDeniedError as exc:
                raise ToolError(str(exc)) from exc

        server.add_tool(_tool, name=capability)
    return server
