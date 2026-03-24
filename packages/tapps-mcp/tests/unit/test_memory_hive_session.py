"""Hive / Agent Teams session wiring (Epic M3 chunk B)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_core.config.settings import load_settings


def test_collect_session_hive_status_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()
    settings = load_settings()
    out = collect_session_hive_status(settings)
    assert out["enabled"] is False
    pc = out.get("propagation_config")
    assert isinstance(pc, dict)
    assert pc.get("profile_sourced") is False
    assert "hive_propagate_tool" in pc


def test_collect_session_hive_status_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()
    settings = load_settings()
    result = collect_session_hive_status(settings)
    assert result["enabled"] is True
    assert result.get("degraded") is False
    assert "agent_id" in result
    assert isinstance(result.get("namespaces"), list)
    assert result.get("registered_agents_count", 0) >= 1
    pc = result.get("propagation_config")
    assert isinstance(pc, dict)
    assert pc.get("profile_sourced") is False
    assert pc.get("hive_propagate_tool", {}).get("auto_propagate_tiers") is None


def test_collect_session_hive_status_degraded_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()

    def _boom() -> tuple[None, None, str]:
        return None, None, "simulated import failure"

    with patch("tapps_mcp.server_helpers._ensure_hive_singletons", _boom):
        settings = load_settings()
        result = collect_session_hive_status(settings)
    assert result["enabled"] is True
    assert result.get("degraded") is True
    assert "simulated import failure" in (result.get("message") or "")
    assert isinstance(result.get("propagation_config"), dict)


@pytest.mark.asyncio
async def test_session_start_quick_includes_hive_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    from tapps_mcp.server_helpers import _reset_hive_store_cache
    from tapps_mcp.server_pipeline_tools import _session_start_quick

    _reset_hive_store_cache()
    start_ns = 0

    def _noop_record(_tool: str, _ns: int) -> None:
        return None

    def _noop_nudges(_tool: str, resp: dict, _ctx: dict) -> dict:
        return resp

    result = await _session_start_quick(start_ns, _noop_record, _noop_nudges)
    assert result["success"] is True
    hs = result["data"].get("hive_status")
    assert hs is not None
    assert hs.get("enabled") is False
    assert isinstance(hs.get("propagation_config"), dict)
