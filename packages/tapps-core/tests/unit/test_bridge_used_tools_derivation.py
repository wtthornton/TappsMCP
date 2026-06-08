"""TAP-1961: bridge-used-tools registry API (tapps-core side)."""

from __future__ import annotations

import pytest

from tapps_core.brain_bridge import (
    _BRIDGE_USED_TOOLS_SNAPSHOT,
    get_bridge_used_tools,
    register_bridge_used_tools,
)


def test_get_bridge_used_tools_falls_back_to_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without tapps-mcp registration, the snapshot is the source of truth."""
    import tapps_core.brain_bridge as bb

    monkeypatch.setattr(bb, "_registered_bridge_used_tools", None)
    assert get_bridge_used_tools() == _BRIDGE_USED_TOOLS_SNAPSHOT


def test_register_bridge_used_tools_overrides_snapshot() -> None:
    custom = frozenset({"memory_save", "memory_get"})
    register_bridge_used_tools(custom)
    assert get_bridge_used_tools() == custom
    register_bridge_used_tools(_BRIDGE_USED_TOOLS_SNAPSHOT)
