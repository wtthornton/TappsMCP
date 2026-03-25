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
        """Call tapps_server_info and verify the response structure."""
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

        assert "installed_checkers" in data
        assert isinstance(data["installed_checkers"], list)

        assert data["checker_environment"] == "mcp_server"
        assert "MCP server" in data["checker_environment_note"]

        assert "configuration" in data
        assert "project_root" in data["configuration"]
        assert "quality_preset" in data["configuration"]

        assert "recommended_workflow" in data
        assert isinstance(data["recommended_workflow"], str)
        assert "tapps_quality_gate" in data["recommended_workflow"]

    @pytest.mark.asyncio
    async def test_server_info_reports_installed_checkers(self):
        """Verify the installed_checkers field has expected tool entries."""
        result = await tapps_server_info()
        checkers = result["data"]["installed_checkers"]

        tool_names = {c["name"] for c in checkers}
        assert "ruff" in tool_names
        assert "mypy" in tool_names
        assert "bandit" in tool_names
        assert "radon" in tool_names

        for checker in checkers:
            assert "name" in checker
            assert "available" in checker
            assert isinstance(checker["available"], bool)
            # If unavailable, should have install_hint
            if not checker["available"]:
                assert checker.get("install_hint") is not None

    def test_mcp_instance_has_tools_registered(self):
        """Verify the FastMCP instance has tools registered."""
        try:
            tool_manager = mcp._tool_manager
            tools = list(tool_manager._tools.keys())
            assert "tapps_server_info" in tools
        except AttributeError:
            # If internal API changes, at least verify the tool function exists
            assert callable(tapps_server_info)
