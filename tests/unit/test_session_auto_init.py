"""Tests for session auto-initialization (server_helpers session state)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_helpers import (
    _reset_session_state,
    ensure_session_initialized,
    ensure_session_initialized_sync,
    get_session_context,
    is_session_initialized,
    mark_session_initialized,
)


class TestSessionState:
    """Tests for basic session state management."""

    def test_initial_state_not_initialized(self):
        assert is_session_initialized() is False

    def test_mark_session_initialized_sets_flag(self):
        mark_session_initialized()
        assert is_session_initialized() is True

    def test_mark_session_initialized_stores_context(self):
        ctx = {"project_root": "/tmp/proj", "quality_preset": "standard"}
        mark_session_initialized(ctx)
        result = get_session_context()
        assert result["project_root"] == "/tmp/proj"
        assert result["quality_preset"] == "standard"

    def test_mark_session_initialized_merges_context(self):
        mark_session_initialized({"a": 1})
        mark_session_initialized({"b": 2})
        ctx = get_session_context()
        assert ctx["a"] == 1
        assert ctx["b"] == 2

    def test_get_session_context_returns_copy(self):
        mark_session_initialized({"key": "value"})
        ctx = get_session_context()
        ctx["key"] = "modified"
        assert get_session_context()["key"] == "value"

    def test_reset_session_state_clears_flag(self):
        mark_session_initialized({"key": "value"})
        assert is_session_initialized() is True
        _reset_session_state()
        assert is_session_initialized() is False
        assert get_session_context() == {}


class TestEnsureSessionInitialized:
    """Tests for async ensure_session_initialized."""

    @pytest.mark.asyncio
    async def test_sets_flag(self):
        with patch("tapps_mcp.config.settings.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=MagicMock(),
                quality_preset="standard",
            )
            with patch("tapps_mcp.project.profiler.detect_project_profile") as mock_profile:
                mock_profile.return_value = MagicMock(
                    project_type="library",
                    has_tests=True,
                    has_docker=False,
                    has_ci=True,
                )
                await ensure_session_initialized()
        assert is_session_initialized() is True

    @pytest.mark.asyncio
    async def test_idempotent(self):
        mark_session_initialized({"first": True})
        # Should be a no-op since already initialized
        await ensure_session_initialized()
        ctx = get_session_context()
        assert ctx.get("first") is True
        assert ctx.get("auto_initialized") is None

    @pytest.mark.asyncio
    async def test_context_has_auto_flag(self):
        with patch("tapps_mcp.config.settings.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=MagicMock(__str__=lambda s: "/tmp/proj"),
                quality_preset="standard",
            )
            with patch("tapps_mcp.project.profiler.detect_project_profile") as mock_profile:
                mock_profile.return_value = MagicMock(
                    project_type="app",
                    has_tests=False,
                    has_docker=True,
                    has_ci=False,
                )
                await ensure_session_initialized()
        ctx = get_session_context()
        assert ctx["auto_initialized"] is True

    @pytest.mark.asyncio
    async def test_profile_failure_still_initializes(self):
        """If project profiling fails, session still initializes."""
        with patch("tapps_mcp.config.settings.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=MagicMock(__str__=lambda s: "/tmp/proj"),
                quality_preset="strict",
            )
            with patch(
                "tapps_mcp.project.profiler.detect_project_profile",
                side_effect=RuntimeError("profile failed"),
            ):
                await ensure_session_initialized()
        assert is_session_initialized() is True
        ctx = get_session_context()
        assert ctx["auto_initialized"] is True
        assert ctx["project_profile"] == {}


class TestEnsureSessionInitializedSync:
    """Tests for sync ensure_session_initialized_sync."""

    def test_sets_flag(self):
        with patch("tapps_mcp.config.settings.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=MagicMock(__str__=lambda s: "/tmp/proj"),
                quality_preset="standard",
            )
            ensure_session_initialized_sync()
        assert is_session_initialized() is True

    def test_idempotent(self):
        mark_session_initialized({"first": True})
        ensure_session_initialized_sync()
        ctx = get_session_context()
        assert ctx.get("first") is True

    def test_context_has_sync_only_flag(self):
        with patch("tapps_mcp.config.settings.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=MagicMock(__str__=lambda s: "/tmp/proj"),
                quality_preset="standard",
            )
            ensure_session_initialized_sync()
        ctx = get_session_context()
        assert ctx["auto_initialized"] is True
        assert ctx["sync_only"] is True
