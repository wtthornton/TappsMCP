"""TAP-1961: derived bridge tool set matches regression snapshot."""

from __future__ import annotations

import tapps_mcp.server_memory_tools as smt
from tapps_core.brain_bridge import (
    _BRIDGE_USED_TOOLS_SNAPSHOT,
    get_bridge_used_tools,
)


def test_derived_tools_match_snapshot() -> None:
    derived = smt.derive_memory_bridge_used_tools()
    assert derived == _BRIDGE_USED_TOOLS_SNAPSHOT


def test_registration_populates_get_bridge_used_tools() -> None:
    assert get_bridge_used_tools() == _BRIDGE_USED_TOOLS_SNAPSHOT
