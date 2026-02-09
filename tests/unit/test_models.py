"""Tests for common.models."""

from tapps_mcp.common.models import ErrorDetail, InstalledTool, ToolResponse


class TestToolResponse:
    def test_success_response(self):
        resp = ToolResponse(
            tool="tapps_server_info",
            success=True,
            elapsed_ms=42,
            data={"version": "0.1.0"},
        )
        assert resp.success is True
        assert resp.error is None
        assert resp.degraded is False
        assert resp.elapsed_ms == 42

    def test_error_response(self):
        resp = ToolResponse(
            tool="tapps_score_file",
            success=False,
            elapsed_ms=10,
            error=ErrorDetail(code="file_not_found", message="File not found"),
        )
        assert resp.success is False
        assert resp.error is not None
        assert resp.error.code == "file_not_found"

    def test_degraded_response(self):
        resp = ToolResponse(
            tool="tapps_score_file",
            success=True,
            elapsed_ms=100,
            degraded=True,
        )
        assert resp.degraded is True


class TestInstalledTool:
    def test_available_tool(self):
        tool = InstalledTool(name="ruff", version="0.8.0", available=True)
        assert tool.available is True
        assert tool.install_hint is None

    def test_missing_tool(self):
        tool = InstalledTool(
            name="bandit",
            available=False,
            install_hint="pip install bandit",
        )
        assert tool.available is False
        assert tool.install_hint == "pip install bandit"
