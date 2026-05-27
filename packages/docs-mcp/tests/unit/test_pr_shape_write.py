"""TAP-2007: Tests for docs-mcp PR-shape procedural pattern write.

Tests for ``docs_mcp.server_linear_tools._fire_pr_shape_pattern`` and
``_write_pr_shape_to_brain``.  These live in the docs-mcp test suite to
avoid the circular-import that occurs when ``docs_mcp.server_linear_tools``
is imported from a tapps-mcp test (it imports ``docs_mcp.server`` at module
level, which in turn registers all server_* modules).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from docs_mcp.server_linear_tools import (
    _fire_pr_shape_pattern,
    _reset_pr_shape_written,
    _write_pr_shape_to_brain,
)

# ---------------------------------------------------------------------------
# Autouse: reset per-session flag before each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_flag() -> None:
    _reset_pr_shape_written()


# ---------------------------------------------------------------------------
# _fire_pr_shape_pattern — session dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_shape_written_once_per_session() -> None:
    with patch(
        "docs_mcp.server_linear_tools._write_pr_shape_to_brain",
        new=AsyncMock(),
    ) as mock_write:
        result_dict = {
            "agent_ready": True,
            "score": 90,
            "findings": [],
            "suggested_label": "",
            "suggested_status": "Backlog",
            "tokens": {},
        }
        _fire_pr_shape_pattern(result_dict)
        _fire_pr_shape_pattern(result_dict)  # second call must be dedup'd
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert mock_write.call_count <= 1


@pytest.mark.asyncio
async def test_pr_shape_not_written_when_not_agent_ready() -> None:
    with patch(
        "docs_mcp.server_linear_tools._write_pr_shape_to_brain",
        new=AsyncMock(),
    ) as mock_write:
        result_dict = {
            "agent_ready": False,
            "score": 50,
            "findings": [{"rule": "missing-acceptance", "severity": "high"}],
            "suggested_label": "",
            "suggested_status": "Triage",
            "tokens": {},
        }
        _fire_pr_shape_pattern(result_dict)
        await asyncio.sleep(0)

    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# _write_pr_shape_to_brain — tier / key / tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_shape_writes_procedural_tier() -> None:
    saved: list[dict[str, Any]] = []

    class _LocalBridge:
        async def save(self, **kwargs: Any) -> dict[str, Any]:
            saved.append(kwargs)
            return {}

        async def supersede(self, key: str, new_value: str, **kwargs: Any) -> dict[str, Any]:
            return {"error": "not_found"}

    with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=_LocalBridge()):
        await _write_pr_shape_to_brain(score=95, common_rules=["missing-estimate"])

    assert len(saved) == 1
    kw = saved[0]
    assert kw["tier"] == "procedural"
    assert "pr-shape" in kw["tags"]
    assert "docs-mcp" in kw["tags"]
    assert "auto-captured" in kw["tags"]
    assert kw["key"] == "procedural.pr-shape.session"
    assert kw["scope"] == "project"


@pytest.mark.asyncio
async def test_pr_shape_supersedes_on_existing_key() -> None:
    superseded: list[dict[str, Any]] = []
    saved: list[dict[str, Any]] = []

    class _BridgeWithSupersede:
        async def save(self, **kwargs: Any) -> dict[str, Any]:
            saved.append(kwargs)
            return {}

        async def supersede(self, key: str, new_value: str, **kwargs: Any) -> dict[str, Any]:
            superseded.append({"key": key, "new_value": new_value})
            return {"success": True}  # key exists

    with patch(
        "tapps_core.brain_bridge.create_brain_bridge", return_value=_BridgeWithSupersede()
    ):
        await _write_pr_shape_to_brain(score=80, common_rules=[])

    assert len(superseded) == 1
    assert superseded[0]["key"] == "procedural.pr-shape.session"
    assert len(saved) == 0  # supersede succeeded, no save needed


@pytest.mark.asyncio
async def test_pr_shape_no_write_when_bridge_unavailable() -> None:
    with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=None):
        # Should not raise
        await _write_pr_shape_to_brain(score=95, common_rules=[])
    assert True
