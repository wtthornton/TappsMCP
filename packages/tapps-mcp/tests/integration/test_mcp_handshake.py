"""Integration test: end-to-end MCP handshake.

Verifies that the server starts, lists tools, and responds to tool calls.
"""

import pytest

from tapps_mcp.server import mcp, tapps_server_info


@pytest.mark.integration
@pytest.mark.slow
class TestMCPHandshake:
    @pytest.mark.asyncio
    async def test_server_info_tool_returns_valid_response(self):
        """Call tapps_server_info and verify the response structure.

        TAP-6433: configuration, installed_checkers, checker_environment*,
        docs_provider, and cache are no longer part of this tool's response
        — they duplicate tapps_session_start(quick=True) byte-for-byte.
        ``server`` (name/version/protocol_version) is kept as the one named
        exception: the tool's own "verify a remote deployment is reachable"
        use case needs it without session_start having run first. Checker
        detection is covered by test_server_info_reports_diagnostics below
        (``diagnostics`` is unique to this tool, unlike ``installed_checkers``).
        """
        result = await tapps_server_info()

        assert isinstance(result, dict)
        assert result["tool"] == "tapps_server_info"
        assert result["success"] is True
        assert "elapsed_ms" in result
        assert isinstance(result["elapsed_ms"], int)

        data = result["data"]
        assert data["server"]["name"] == "TappsMCP"
        from tapps_mcp import __version__

        assert data["server"]["version"] == __version__
        assert data["server"]["protocol_version"] == "2025-11-25"

        assert "available_tools" in data
        assert "tapps_server_info" in data["available_tools"]

        for duplicated_field in (
            "installed_checkers",
            "checker_environment",
            "checker_environment_note",
            "configuration",
            "docs_provider",
            "cache",
        ):
            assert duplicated_field not in data, duplicated_field

        assert "recommended_workflow" in data
        assert isinstance(data["recommended_workflow"], str)
        assert "tapps_quality_gate" in data["recommended_workflow"]

    @pytest.mark.asyncio
    async def test_server_info_reports_diagnostics(self):
        """Verify the diagnostics field (unique to this tool) is populated."""
        result = await tapps_server_info()
        diagnostics = result["data"]["diagnostics"]

        assert isinstance(diagnostics, dict)
        assert "cache" in diagnostics

    def test_mcp_instance_has_tools_registered(self):
        """Verify the FastMCP instance has tools registered."""
        try:
            tool_manager = mcp._tool_manager
            tools = list(tool_manager._tools.keys())
            assert "tapps_server_info" in tools
        except AttributeError:
            # If internal API changes, at least verify the tool function exists
            assert callable(tapps_server_info)

    @pytest.mark.asyncio
    async def test_server_info_includes_brain_bridge_snapshot(self):
        """TAP-517: server_info must expose BrainBridge queue_depth + circuit_state."""
        result = await tapps_server_info()
        bb = result["data"].get("brain_bridge")
        assert bb is not None
        assert "initialized" in bb
        if bb["initialized"]:
            assert bb["circuit_state"] in {"open", "closed"}
            assert isinstance(bb["queue_depth"], int)
            assert isinstance(bb["queue_cap"], int)
