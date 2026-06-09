"""Tests for ensure_session_initialized profile cache integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.project.profile_cache import save_cached_profile_summary, profile_marker_fingerprint
from tapps_mcp.server_helpers import _reset_session_state, ensure_session_initialized


@pytest.mark.asyncio
async def test_ensure_session_initialized_uses_profile_cache(tmp_path: Path) -> None:
    _reset_session_state()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    fp = profile_marker_fingerprint(tmp_path)
    save_cached_profile_summary(
        tmp_path,
        fp,
        {"project_type": "library", "has_tests": True, "has_docker": False, "has_ci": True},
    )

    with patch("tapps_core.config.settings.load_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            quality_preset="standard",
        )
        with patch("tapps_mcp.project.profiler.detect_project_profile") as mock_detect:
            await ensure_session_initialized()
            mock_detect.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_session_initialized_populates_cache_on_miss(tmp_path: Path) -> None:
    _reset_session_state()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")

    with patch("tapps_core.config.settings.load_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            quality_preset="standard",
        )
        with patch("tapps_mcp.project.profiler.detect_project_profile") as mock_detect:
            mock_detect.return_value = MagicMock(
                project_type="library",
                has_tests=True,
                has_docker=True,
                has_ci=False,
            )
            await ensure_session_initialized()
            mock_detect.assert_called_once()
