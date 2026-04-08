"""Tests for DocsMCP server helper functions."""

from __future__ import annotations

from docs_mcp.server_helpers import error_response, success_response


class TestSuccessResponse:
    def test_success_response_shape(self) -> None:
        result = success_response("test_tool", 42, {"key": "value"})
        assert "tool" in result
        assert "success" in result
        assert "elapsed_ms" in result
        assert "data" in result

    def test_success_response_values(self) -> None:
        result = success_response("my_tool", 100, {"foo": "bar"})
        assert result["tool"] == "my_tool"
        assert result["success"] is True
        assert result["elapsed_ms"] == 100
        assert result["data"] == {"foo": "bar"}

    def test_success_response_no_degraded_by_default(self) -> None:
        result = success_response("t", 0, {})
        assert "degraded" not in result

    def test_success_response_with_degraded(self) -> None:
        result = success_response("t", 0, {}, degraded=True)
        assert result["degraded"] is True

    def test_success_response_with_degraded_false(self) -> None:
        result = success_response("t", 0, {}, degraded=False)
        assert result["degraded"] is False

    def test_success_response_with_next_steps(self) -> None:
        steps = ["step1", "step2"]
        result = success_response("t", 0, {"k": "v"}, next_steps=steps)
        assert result["data"]["next_steps"] == steps

    def test_success_response_no_next_steps_when_empty(self) -> None:
        result = success_response("t", 0, {"k": "v"}, next_steps=[])
        assert "next_steps" not in result["data"]


class TestErrorResponse:
    def test_error_response_shape(self) -> None:
        result = error_response("test_tool", "ERR_CODE", "Something failed")
        assert "tool" in result
        assert "success" in result
        assert "elapsed_ms" in result
        assert "error" in result

    def test_error_response_values(self) -> None:
        result = error_response("my_tool", "BAD_INPUT", "Invalid path")
        assert result["tool"] == "my_tool"
        assert result["success"] is False
        assert result["elapsed_ms"] == 0
        assert result["error"]["code"] == "BAD_INPUT"
        assert result["error"]["message"] == "Invalid path"

    def test_error_response_no_data_key(self) -> None:
        result = error_response("t", "E", "msg")
        assert "data" not in result


class TestSettingsSingleton:
    def test_get_settings_returns_settings(self) -> None:
        from docs_mcp.server_helpers import _get_settings

        settings = _get_settings()
        from docs_mcp.config.settings import DocsMCPSettings

        assert isinstance(settings, DocsMCPSettings)

    def test_reset_settings_cache(self) -> None:
        from docs_mcp.server_helpers import _get_settings, _reset_settings_cache

        s1 = _get_settings()
        _reset_settings_cache()
        s2 = _get_settings()
        # After reset, a new instance is created (may or may not be same object)
        assert isinstance(s1, type(s2))


class TestErrorResponseExtra:
    """Issue #84: error_response supports extra metadata."""

    def test_extra_merged_into_error(self) -> None:
        from docs_mcp.server_helpers import error_response

        result = error_response(
            "test_tool", "NO_FILES_FOUND", "No files matched",
            extra={"requested_files": ["a.md"], "project_root": "/tmp"},
        )
        assert result["error"]["requested_files"] == ["a.md"]
        assert result["error"]["project_root"] == "/tmp"

    def test_extra_none_preserves_original(self) -> None:
        from docs_mcp.server_helpers import error_response

        result = error_response("test_tool", "CODE", "msg")
        assert set(result["error"].keys()) == {"code", "message"}
