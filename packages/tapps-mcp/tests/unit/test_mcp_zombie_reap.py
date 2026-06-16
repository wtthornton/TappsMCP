"""Tests for deploy-local MCP orphan reap."""

from __future__ import annotations

import os
import signal
from unittest.mock import patch

from tapps_mcp.distribution.mcp_zombie_reap import (
    find_live_mcp_serve_pids,
    find_orphan_mcp_serve_pids,
    reap_orphan_mcp_serves,
)


class TestFindOrphanMcpServePids:
    def test_empty_when_ps_unavailable(self) -> None:
        with patch(
            "tapps_mcp.distribution.mcp_zombie_reap.subprocess.run",
            side_effect=OSError("no ps"),
        ):
            assert find_orphan_mcp_serve_pids() == []

    def test_finds_orphan_nlt_serve(self) -> None:
        ps_out = "12345 1 uv run tapps-mcp serve --profile nlt-build\n"
        with patch(
            "tapps_mcp.distribution.mcp_zombie_reap.subprocess.run",
            return_value=type("R", (), {"returncode": 0, "stdout": ps_out})(),
        ):
            assert find_orphan_mcp_serve_pids() == [12345]

    def test_skips_live_parent(self) -> None:
        ps_out = "99999 88888 uv run tapps-mcp serve --profile nlt-build\n"
        with (
            patch(
                "tapps_mcp.distribution.mcp_zombie_reap.subprocess.run",
                return_value=type("R", (), {"returncode": 0, "stdout": ps_out})(),
            ),
            patch("tapps_mcp.distribution.mcp_zombie_reap._parent_alive", return_value=True),
        ):
            assert find_orphan_mcp_serve_pids() == []


class TestFindLiveMcpServePids:
    def test_finds_live_parent(self) -> None:
        ps_out = "99999 88888 uv run tapps-mcp serve --profile nlt-build\n"
        with (
            patch(
                "tapps_mcp.distribution.mcp_zombie_reap.subprocess.run",
                return_value=type("R", (), {"returncode": 0, "stdout": ps_out})(),
            ),
            patch("tapps_mcp.distribution.mcp_zombie_reap._parent_alive", return_value=True),
        ):
            assert find_live_mcp_serve_pids() == [99999]

    def test_skips_orphans(self) -> None:
        ps_out = "12345 1 uv run tapps-mcp serve --profile nlt-build\n"
        with patch(
            "tapps_mcp.distribution.mcp_zombie_reap.subprocess.run",
            return_value=type("R", (), {"returncode": 0, "stdout": ps_out})(),
        ):
            assert find_live_mcp_serve_pids() == []


class TestReapOrphanMcpServes:
    def test_dry_run_does_not_kill(self) -> None:
        with patch(
            "tapps_mcp.distribution.mcp_zombie_reap.find_orphan_mcp_serve_pids",
            return_value=[42],
        ):
            with patch("tapps_mcp.distribution.mcp_zombie_reap.os.kill") as kill_mock:
                result = reap_orphan_mcp_serves(dry_run=True)
        kill_mock.assert_not_called()
        assert result["reaped"] == [42]

    def test_reap_sends_sigterm(self) -> None:
        with patch(
            "tapps_mcp.distribution.mcp_zombie_reap.find_orphan_mcp_serve_pids",
            return_value=[42],
        ):
            with patch("tapps_mcp.distribution.mcp_zombie_reap.os.kill") as kill_mock:
                result = reap_orphan_mcp_serves()
        kill_mock.assert_called_once_with(42, signal.SIGTERM)
        assert result["ok"] is True
