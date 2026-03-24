"""M4.1: auto-save expert consultations when memory.auto_save_quality is enabled."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from tapps_core.config.settings import MemorySettings, TappsMCPSettings
from tapps_mcp.server import tapps_consult_expert
from tapps_mcp.server_helpers import _auto_save_expert_consultation_memory


def test_auto_save_helper_skips_when_flag_off() -> None:
    settings = TappsMCPSettings(
        project_root=Path("/tmp"),
        memory=MemorySettings(auto_save_quality=False),
    )
    out = _auto_save_expert_consultation_memory(
        settings,
        question="q",
        domain="security",
        expert_answer="answer text long enough",
        expert_id="e1",
        expert_name="Sec",
        confidence=0.9,
    )
    assert out["quality_memory_saved"] is False
    assert out.get("quality_memory_skip") == "feature_disabled"


@patch("tapps_mcp.server_helpers._get_memory_store")
def test_auto_save_helper_calls_save_when_flag_on(mock_get_store: MagicMock) -> None:
    mock_store = MagicMock()
    mock_store.save.return_value = object()
    mock_get_store.return_value = mock_store

    settings = TappsMCPSettings(
        project_root=Path("/tmp"),
        memory=MemorySettings(auto_save_quality=True),
    )
    out = _auto_save_expert_consultation_memory(
        settings,
        question="How to structure pytest fixtures?",
        domain="testing-strategies",
        expert_answer="Use session-scoped fixtures for expensive setup." * 2,
        expert_id="tid",
        expert_name="Testing",
        confidence=0.88,
    )
    assert out["quality_memory_saved"] is True
    assert "quality_memory_key" in out
    mock_store.save.assert_called_once()
    kwargs: dict[str, Any] = mock_store.save.call_args.kwargs
    assert kwargs["tier"] == "pattern"
    assert kwargs["source"] == "agent"
    assert kwargs["source_agent"] == "tapps-mcp"
    assert "auto-captured" in kwargs["tags"]


@patch("tapps_mcp.server.load_settings")
@patch("tapps_mcp.server_helpers._get_memory_store")
def test_consult_expert_does_not_save_when_auto_save_off(
    mock_get_store: MagicMock,
    mock_load_settings: MagicMock,
    tmp_path: Path,
) -> None:
    store = MagicMock()
    mock_get_store.return_value = store
    mock_load_settings.return_value = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(auto_save_quality=False),
    )
    result = tapps_consult_expert(
        question="What is parameterized testing?",
        domain="testing-strategies",
    )
    assert result.get("success") is True
    store.save.assert_not_called()


@patch("tapps_mcp.server.load_settings")
@patch("tapps_mcp.server_helpers._get_memory_store")
def test_consult_expert_saves_once_when_auto_save_on(
    mock_get_store: MagicMock,
    mock_load_settings: MagicMock,
    tmp_path: Path,
) -> None:
    store = MagicMock()
    store.save.return_value = object()
    mock_get_store.return_value = store
    mock_load_settings.return_value = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(auto_save_quality=True),
    )
    result = tapps_consult_expert(
        question="How do I mock external APIs in tests?",
        domain="testing-strategies",
    )
    assert result.get("success") is True
    store.save.assert_called_once()
    data = result.get("data") or {}
    assert data.get("quality_memory_saved") is True
    assert data.get("quality_memory_key")
