"""M4.3: architectural save uses store.supersede when auto_supersede_architectural is on."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_core.config.settings import MemorySafetySettings, MemorySettings, TappsMCPSettings
from tapps_mcp.server_memory_tools import tapps_memory


def _long_value() -> str:
    return "Architectural decision body " * 2


@pytest.mark.asyncio
async def test_save_supersedes_when_flag_on_and_active_arch_head(tmp_path: Path) -> None:
    mock_store = MagicMock()
    head = MagicMock()
    head.invalid_at = None
    head.tier = "architectural"
    head.key = "adr-auth"
    head.valid_at = "2024-01-01T00:00:00Z"
    mock_store.history.return_value = [head]

    new_entry = MagicMock()
    new_entry.key = "adr-auth.v2"
    new_entry.model_dump.return_value = {"key": "adr-auth.v2", "tier": "architectural"}
    mock_store.supersede.return_value = new_entry
    mock_store.snapshot.return_value = MagicMock(total_count=2, tier_counts={"architectural": 2})

    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(
            enabled=True,
            auto_supersede_architectural=True,
            safety=MemorySafetySettings(enforcement="warn", allow_bypass=True),
        ),
    )

    with (
        patch("tapps_mcp.server_memory_tools._record_call"),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ),
        patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=mock_store),
        patch("tapps_core.config.settings.load_settings", return_value=settings),
    ):
        out = await tapps_memory(
            action="save",
            key="adr-auth",
            value=_long_value(),
            tier="architectural",
            source="system",
            safety_bypass=True,
        )

    assert out.get("success") is True
    data = out.get("data") or {}
    assert data.get("status") == "superseded"
    assert data.get("superseded_old_key") == "adr-auth"
    assert data.get("new_key") == "adr-auth.v2"
    assert data.get("version_count") == 1
    mock_store.supersede.assert_called_once()
    mock_store.save.assert_not_called()
    kw = mock_store.supersede.call_args.kwargs
    assert kw["old_key"] == "adr-auth"
    assert kw["new_value"] == _long_value()
    assert kw["tier"] == "architectural"


@pytest.mark.asyncio
async def test_save_uses_plain_save_when_flag_off(tmp_path: Path) -> None:
    mock_store = MagicMock()
    head = MagicMock()
    head.invalid_at = None
    head.tier = "architectural"
    head.key = "adr-auth"
    head.valid_at = "2024-01-01T00:00:00Z"
    mock_store.history.return_value = [head]

    saved = MagicMock()
    saved.model_dump.return_value = {"key": "adr-auth"}
    mock_store.save.return_value = saved
    mock_store.snapshot.return_value = MagicMock(total_count=1, tier_counts={"architectural": 1})

    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(
            enabled=True,
            auto_supersede_architectural=False,
            safety=MemorySafetySettings(enforcement="warn", allow_bypass=True),
        ),
    )

    with (
        patch("tapps_mcp.server_memory_tools._record_call"),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ),
        patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=mock_store),
        patch("tapps_core.config.settings.load_settings", return_value=settings),
    ):
        out = await tapps_memory(
            action="save",
            key="adr-auth",
            value=_long_value(),
            tier="architectural",
            source="system",
            safety_bypass=True,
        )

    assert out.get("success") is True
    data = out.get("data") or {}
    assert "status" not in data
    mock_store.history.assert_not_called()
    mock_store.supersede.assert_not_called()
    mock_store.save.assert_called_once()


@pytest.mark.asyncio
async def test_save_falls_back_when_supersede_raises(tmp_path: Path) -> None:
    mock_store = MagicMock()
    head = MagicMock()
    head.invalid_at = None
    head.tier = "architectural"
    head.key = "adr-auth"
    head.valid_at = "2024-01-01T00:00:00Z"
    mock_store.history.return_value = [head]
    mock_store.supersede.side_effect = ValueError("already superseded")

    saved = MagicMock()
    saved.model_dump.return_value = {"key": "adr-auth"}
    mock_store.save.return_value = saved
    mock_store.snapshot.return_value = MagicMock(total_count=1, tier_counts={"architectural": 1})

    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(
            enabled=True,
            auto_supersede_architectural=True,
            safety=MemorySafetySettings(enforcement="warn", allow_bypass=True),
        ),
    )

    with (
        patch("tapps_mcp.server_memory_tools._record_call"),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ),
        patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=mock_store),
        patch("tapps_core.config.settings.load_settings", return_value=settings),
    ):
        out = await tapps_memory(
            action="save",
            key="adr-auth",
            value=_long_value(),
            tier="architectural",
            source="system",
            safety_bypass=True,
        )

    assert out.get("success") is True
    mock_store.save.assert_called_once()
    data = out.get("data") or {}
    assert "status" not in data
