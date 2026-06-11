"""Tests for session_start CLI fallback (TAP-3587)."""

from __future__ import annotations

from tapps_mcp.tools.session_start_helpers import CLI_FALLBACK, attach_cli_fallback


class TestCliFallback:
    def test_attach_cli_fallback_keys(self) -> None:
        data: dict[str, object] = {}
        attach_cli_fallback(data)
        assert "cli_fallback" in data
        assert "mcp_recovery_hint" in data
        fallback = data["cli_fallback"]
        assert isinstance(fallback, dict)
        assert "tapps_validate_changed" in fallback
        assert "tapps_quick_check" in fallback
        assert "--file-paths" in fallback["tapps_validate_changed"]
        assert "quick-check" in fallback["tapps_quick_check"]

    def test_cli_fallback_map_complete(self) -> None:
        assert "tapps_doctor" in CLI_FALLBACK
        assert "tapps_lookup_docs" in CLI_FALLBACK
