"""Tests for Epic M1: Memory security surface — non-deprecated diagnostics.

TAP-1993/TAP-1994: safety_check and verify_integrity actions are now refused
(delegated to mcp__tapps-brain__brain_status). Those test classes have been
removed. TestDualMemoryServerCheck covers a doctor diagnostic that is
still active.
"""

from __future__ import annotations

from pathlib import Path


class TestDualMemoryServerCheck:
    """Tests for check_dual_memory_server doctor diagnostic."""

    def test_no_config_files(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_dual_memory_server

        result = check_dual_memory_server(tmp_path)
        assert result.ok is True
        assert "No dual memory server" in result.message

    def test_detects_tapps_brain_mcp_in_config(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_dual_memory_server

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config = claude_dir / "settings.json"
        config.write_text(
            '{"mcpServers": {"tapps-brain-mcp": {"command": "tapps-brain-mcp"}}}',
            encoding="utf-8",
        )

        result = check_dual_memory_server(tmp_path)
        assert "tapps-brain-mcp" in result.message
        assert "split-brain" in (result.detail or "")

    def test_ignores_unrelated_config(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_dual_memory_server

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config = claude_dir / "settings.json"
        config.write_text(
            '{"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}',
            encoding="utf-8",
        )

        result = check_dual_memory_server(tmp_path)
        assert result.ok is True
        assert "No dual memory server" in result.message
