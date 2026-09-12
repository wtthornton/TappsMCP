"""tapps_static_detectors registers on a real FastMCP instance (CB lane L3 fix round 1).

FIX 1: the tool was declared (server_analysis_tools.tapps_static_detectors, a
thin delegator to project/static_detectors.run_static_detector_tool) but was
absent from BOTH server_analysis_tools.register()'s gated block AND
server.py's ALL_TOOL_NAMES frozenset -- unreachable on any preset, including
the default `full`. A missing TOOL_DESCRIPTIONS entry would additionally
crash registration with a KeyError (TAP-7217's failure mode) the moment it
was attempted. This test drives the real registration path, the same one
test_every_profile_registers.py uses, forcing the tool name into
allowed_tools directly (matching the round-1 verifier's method) rather than
grepping for the string.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tapps_mcp.server import ALL_TOOL_NAMES, register_profile


def test_tapps_static_detectors_registers_on_full_preset() -> None:
    mcp_instance = FastMCP("test-full")

    register_profile(mcp_instance, ALL_TOOL_NAMES, tool_preset="full")

    registered = mcp_instance._tool_manager._tools
    assert "tapps_static_detectors" in registered
    assert registered["tapps_static_detectors"].description


def test_tapps_static_detectors_registers_when_forced_into_allowed_tools() -> None:
    forced = frozenset({"tapps_static_detectors"})
    mcp_instance = FastMCP("test-forced")

    register_profile(mcp_instance, forced, tool_preset=None)

    registered = mcp_instance._tool_manager._tools
    assert "tapps_static_detectors" in registered
    assert len(registered) == 1
