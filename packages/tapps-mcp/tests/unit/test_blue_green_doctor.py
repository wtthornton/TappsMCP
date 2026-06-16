"""Doctor and diagnostics integration for blue/green deploy."""

from __future__ import annotations

from tapps_mcp.distribution.doctor import check_blue_green_deploy


def test_check_blue_green_deploy_not_configured() -> None:
    result = check_blue_green_deploy()
    assert result.ok is True
    assert "Not configured" in result.message or "current=" in result.message
