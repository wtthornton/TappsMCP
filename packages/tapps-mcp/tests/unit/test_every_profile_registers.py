"""Every NLT profile registers cleanly on a fresh FastMCP instance (LANE_ISSUE).

TAP-7217: nlt-build 3.12.84 crashed at import time with
``KeyError: "Missing TOOL_DESCRIPTIONS entry for 'tapps_file_api'"``. Every
unit test passed and CI was green because nothing actually drove
``register_profile`` (née ``_register_tool_modules``) against a real
``FastMCP`` instance per profile -- the module-level call only ever ran
once, for whichever preset the test process happened to load with. This
file is the constraint that would have caught it: for every profile in
``_NLT_TAPPS_TOOL_PRESETS``, build a fresh ``FastMCP`` instance, run the
exact registration path the server uses, and assert it succeeds with the
right tool set and non-empty descriptions.
"""

from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from tapps_mcp.server import _NLT_TAPPS_TOOL_PRESETS, register_profile
from tapps_mcp.tools.session_start_helpers import SESSION_START_POINTER_PRESETS


@pytest.mark.parametrize("preset_name", sorted(_NLT_TAPPS_TOOL_PRESETS))
def test_profile_registers_without_error(preset_name: str) -> None:
    allowed_tools = _NLT_TAPPS_TOOL_PRESETS[preset_name]
    mcp_instance = FastMCP(f"test-{preset_name}")

    register_profile(mcp_instance, allowed_tools, tool_preset=preset_name)


@pytest.mark.parametrize("preset_name", sorted(_NLT_TAPPS_TOOL_PRESETS))
def test_profile_registers_exact_tool_set(preset_name: str) -> None:
    allowed_tools = _NLT_TAPPS_TOOL_PRESETS[preset_name]
    mcp_instance = FastMCP(f"test-{preset_name}")

    register_profile(mcp_instance, allowed_tools, tool_preset=preset_name)

    # TAP-7018: nlt-build/nlt-setup (by literal preset string, not the alias
    # names) additionally register a tapps_session_start pointer stub so a
    # retired preset's first call resolves instead of 404ing -- expected,
    # not a registration bug this constraint should flag.
    expected = set(allowed_tools)
    if preset_name in SESSION_START_POINTER_PRESETS and "tapps_session_start" not in expected:
        expected |= {"tapps_session_start"}

    registered = set(mcp_instance._tool_manager._tools.keys())
    assert registered == expected


@pytest.mark.parametrize("preset_name", sorted(_NLT_TAPPS_TOOL_PRESETS))
def test_profile_every_tool_has_a_description(preset_name: str) -> None:
    allowed_tools = _NLT_TAPPS_TOOL_PRESETS[preset_name]
    mcp_instance = FastMCP(f"test-{preset_name}")

    register_profile(mcp_instance, allowed_tools, tool_preset=preset_name)

    tools = mcp_instance._tool_manager._tools
    for tool_name in tools:
        assert tools[tool_name].description, f"{tool_name} registered with an empty description"
