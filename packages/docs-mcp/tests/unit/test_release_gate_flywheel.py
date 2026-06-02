"""Tests for docs_release_gate flywheel-gap signal (TAP-1952).

The three sub-checks are stubbed clean (verdict would be 'pass') so the test
isolates the flywheel-driven verdict transition. asyncio auto-mode → no marker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from docs_mcp.server_val_tools import docs_release_gate

_CLEAN_DRIFT = {"data": {"drift_score": 0, "items": []}}
_CLEAN_FRESH = {"data": {"stale_count": 0, "ancient_count": 0}}
_CLEAN_LINKS = {"data": {"broken_count": 0, "total_links": 5}}


class FakeBridge:
    def __init__(self, gaps_total: int, gaps: list[dict[str, Any]] | None = None) -> None:
        self._gaps_total = gaps_total
        self._gaps = gaps or []

    async def flywheel_report(self, period_days: int = 7) -> dict[str, Any]:
        return {"gaps_total": self._gaps_total, "gaps": self._gaps}


def _patch_checks() -> Any:
    return patch.multiple(
        "docs_mcp.server_val_tools",
        docs_check_drift=AsyncMock(return_value=_CLEAN_DRIFT),
        docs_check_freshness=AsyncMock(return_value=_CLEAN_FRESH),
        docs_check_links=AsyncMock(return_value=_CLEAN_LINKS),
    )


def _patch_bridge(bridge: Any) -> Any:
    return patch("docs_mcp.server_val_tools._get_brain_bridge", return_value=bridge)


async def test_pass_when_gaps_below_threshold() -> None:
    with _patch_checks(), _patch_bridge(FakeBridge(3)):
        resp = await docs_release_gate(prev_version="v1")
    data = resp["data"]
    assert data["verdict"] == "pass"
    assert data["reason"] == ""
    assert data["flywheel"] == {"available": True, "gaps_total": 3, "top_gaps": []}


async def test_warn_when_gaps_exceed_threshold() -> None:
    gaps = [{"name": "auth", "count": 4}, {"name": "cli", "count": 2}]
    with _patch_checks(), _patch_bridge(FakeBridge(9, gaps)):
        resp = await docs_release_gate(prev_version="v1")
    data = resp["data"]
    assert data["verdict"] == "warn"
    assert data["reason"] == "flywheel gaps exceed threshold"
    assert data["flywheel"]["gaps_total"] == 9
    assert data["flywheel"]["top_gaps"][0] == {"name": "auth", "count": 4}
    assert any("flywheel gaps" in r for r in data["recommendations"])


async def test_top_gaps_capped_at_three() -> None:
    gaps = [{"name": f"g{i}", "count": 10 - i} for i in range(6)]
    with _patch_checks(), _patch_bridge(FakeBridge(20, gaps)):
        resp = await docs_release_gate(prev_version="v1")
    assert len(resp["data"]["flywheel"]["top_gaps"]) == 3


async def test_bridge_unavailable_leaves_verdict_unchanged() -> None:
    with _patch_checks(), _patch_bridge(None):
        resp = await docs_release_gate(prev_version="v1")
    data = resp["data"]
    assert data["flywheel"] == {"available": False}
    assert data["verdict"] == "pass"


async def test_flywheel_does_not_upgrade_a_failing_gate() -> None:
    """A gate already failing local checks stays 'warn' regardless of low gaps."""
    failing_drift = {"data": {"drift_score": 80, "items": [{}]}}
    with (
        patch.multiple(
            "docs_mcp.server_val_tools",
            docs_check_drift=AsyncMock(return_value=failing_drift),
            docs_check_freshness=AsyncMock(return_value=_CLEAN_FRESH),
            docs_check_links=AsyncMock(return_value=_CLEAN_LINKS),
        ),
        _patch_bridge(FakeBridge(0)),
    ):
        resp = await docs_release_gate(prev_version="v1")
    data = resp["data"]
    assert data["agent_ready"] is False
    assert data["verdict"] == "warn"
