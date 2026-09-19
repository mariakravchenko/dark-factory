"""``build_mcp_server`` -- the D-12 in-memory MCP client proof (Phase 6,
plan 06-03, TOOL-05).

Gated with ``pytest.importorskip("mcp")`` per D-13: this module is skipped
only in an installation that deliberately never runs ``uv sync
--all-extras`` (see A-06-08). This project's standard dev/CI workflow
installs every optional group, so in ordinary runs this module is never
actually skipped.

Every test here is built against a purpose-built :class:`ToolRegistry`
whose capability implementations record their own invocation -- never
against ``default_registry`` -- so a test can assert not just the value a
call returned but *which* implementation actually ran (or, for a denial,
that none did).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp import Client

from dark_factory.tools import CapabilityDeniedError
from dark_factory.tools.mcp_transport import build_mcp_server
from dark_factory.tools.registry import ToolRegistry, default_registry

pytestmark = pytest.mark.unit


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _RecordingRegistry:
    """A purpose-built :class:`ToolRegistry` wrapper: every registered
    implementation appends ``(capability, kwargs)`` to a shared list before
    returning a JSON-serialisable value naming itself, so a test can assert
    both the *value* an MCP call produced and *whether an implementation
    ran at all* -- the second is what an unadvertised/denied-call test
    needs to prove nothing executed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.registry = ToolRegistry()

    def register_echo(self, name: str) -> None:
        def _impl(**kwargs: object) -> dict[str, object]:
            self.calls.append((name, dict(kwargs)))
            return {"ran": name, "kwargs": kwargs}

        self.registry.register(name, _impl)


@pytest.fixture
def recording() -> _RecordingRegistry:
    rr = _RecordingRegistry()
    rr.register_echo("test.alpha")
    rr.register_echo("test.beta")
    rr.register_echo("test.gamma")
    rr.register_echo("test.protected")
    return rr


# --------------------------------------------------------------------------- #
# list_tools() / distinct construction (D-15)
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_list_tools_returns_exactly_the_granted_names(
    recording: _RecordingRegistry,
) -> None:
    granted = ["test.alpha", "test.beta"]
    server = build_mcp_server("DEVELOPMENT", granted, recording.registry)
    async with Client(server, raise_exceptions=True) as client:
        result = await client.list_tools()
    assert {tool.name for tool in result.tools} == set(granted)


def test_two_builds_return_distinct_server_objects(
    recording: _RecordingRegistry,
) -> None:
    granted = ["test.alpha"]
    server_a = build_mcp_server("DEVELOPMENT", granted, recording.registry)
    server_b = build_mcp_server("DEVELOPMENT", granted, recording.registry)
    assert server_a is not server_b


# --------------------------------------------------------------------------- #
# A granted call reaches the real implementation and returns its value
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_granted_call_returns_the_same_value_as_direct_invoke(
    recording: _RecordingRegistry,
) -> None:
    granted = ["test.alpha"]
    server = build_mcp_server("DEVELOPMENT", granted, recording.registry)
    direct = recording.registry.invoke("DEVELOPMENT", "test.alpha", granted, x=1)

    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("test.alpha", {"arguments": {"x": 1}})

    assert result.is_error is False
    via_mcp = json.loads(result.content[0].text)
    assert via_mcp == direct
    assert recording.calls == [("test.alpha", {"x": 1}), ("test.alpha", {"x": 1})]


# --------------------------------------------------------------------------- #
# Denial: not granted (T-06-03) -- invoke()'s own check, not the advertised
# list, is what stops the call. Proven by mutating the authoritative granted
# list *after* the tool was registered/advertised: the tool name still
# appears in list_tools() (nothing un-advertises it), yet invoke() -- which
# re-checks membership fresh on every call, never caching a decision made at
# registration time -- denies it. This is the literal demonstration of "the
# exposed tool list is a convenience, never the enforcement boundary."
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_ungranted_capability_denied_by_invoke_names_role_and_capability(
    recording: _RecordingRegistry,
) -> None:
    granted = ["test.alpha", "test.protected"]
    server = build_mcp_server("QA", granted, recording.registry)

    async with Client(server, raise_exceptions=True) as client:
        still_listed = await client.list_tools()
        assert "test.protected" in {t.name for t in still_listed.tools}

        # Revoke *after* construction/advertisement -- invoke() re-checks
        # fresh on every call rather than trusting what got registered.
        granted.remove("test.protected")

        result = await client.call_tool("test.protected", {"arguments": {}})

    assert result.is_error is True
    message = result.content[0].text
    assert "QA" in message
    assert "test.protected" in message
    assert all(name != "test.protected" for name, _ in recording.calls)


def test_capability_denied_error_message_shape_matches_the_mcp_surface() -> None:
    """Sanity check on the exact exception this transport catches and
    re-raises: :class:`CapabilityDeniedError`'s message already names the
    role and the capability (Phase 6 plan 06-01) -- this transport adds no
    redaction and no extra formatting, it forwards ``str(exc)`` verbatim."""
    with pytest.raises(CapabilityDeniedError) as excinfo:
        default_registry.invoke("QA", "repo.write", [])
    assert "QA" in str(excinfo.value)
    assert "repo.write" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Denial: never advertised to this server at all (T-06-03) -- the SDK's own
# name-based dispatch rejects a `tools/call` for a name this particular
# server never registered via add_tool, before any closure -- and therefore
# before invoke() -- ever runs. This is a *stronger* structural property
# than "invoke() denies it": the call cannot reach an implementation at all,
# by construction, because build_mcp_server only ever registers a closure
# for a name in `granted_tools`. Documented explicitly here because it is
# the one must-have truth this transport satisfies via the SDK's routing
# layer rather than literally inside `ToolRegistry.invoke()` -- the two
# denial mechanisms are equivalent in outcome (no implementation runs) but
# distinct in which layer of code raises.
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_unadvertised_capability_name_never_reaches_an_implementation(
    recording: _RecordingRegistry,
) -> None:
    granted = ["test.alpha"]  # "test.beta" is registered on the underlying
    # ToolRegistry but never granted/advertised on this particular server.
    server = build_mcp_server("DEVELOPMENT", granted, recording.registry)

    async with Client(server, raise_exceptions=True) as client:
        listed = await client.list_tools()
        assert "test.beta" not in {t.name for t in listed.tools}
        result = await client.call_tool("test.beta", {"arguments": {}})

    assert result.is_error is True
    assert all(name != "test.beta" for name, _ in recording.calls)


# --------------------------------------------------------------------------- #
# Late-binding closure regression (RESEARCH Pitfall 1)
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_each_advertised_tool_dispatches_to_its_own_capability(
    recording: _RecordingRegistry,
) -> None:
    granted = ["test.alpha", "test.beta", "test.gamma"]
    server = build_mcp_server("DEVELOPMENT", granted, recording.registry)

    async with Client(server, raise_exceptions=True) as client:
        for name in granted:
            result = await client.call_tool(name, {"arguments": {}})
            assert result.is_error is False
            payload = json.loads(result.content[0].text)
            assert payload["ran"] == name

    assert recording.calls == [(name, {}) for name in granted]


# --------------------------------------------------------------------------- #
# artifacts.write -- the one production-shaped capability this phase has
# (06-01-PLAN.md's <planner_override>, A-06-03) -- actually writes a file
# through the transport, not just returns a value.
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_artifacts_write_through_the_transport_actually_writes_the_file() -> (
    None
):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        server = build_mcp_server("DEVELOPMENT", ["artifacts.write"], default_registry)

        async with Client(server, raise_exceptions=True) as client:
            result = await client.call_tool(
                "artifacts.write",
                {
                    "arguments": {
                        "root": str(root),
                        "role": "DEVELOPMENT",
                        "filename": "out.md",
                        "text": "hello from the MCP transport",
                    }
                },
            )

        assert result.is_error is False
        written = root / "artifacts" / "DEVELOPMENT" / "out.md"
        assert written.is_file()
        assert written.read_text("utf-8") == "hello from the MCP transport"
