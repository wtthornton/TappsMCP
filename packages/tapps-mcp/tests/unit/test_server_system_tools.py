"""Tests for server_system_tools — server info + config validation helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_system_tools import (
    _attach_config_structured_output,
    _build_config_response_data,
    _read_config_content,
    _resolve_config_type,
    tapps_server_info,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")


def _finding(severity: str = "warning") -> SimpleNamespace:
    return SimpleNamespace(
        severity=severity,
        message="msg",
        line=3,
        category="security",
        model_dump=lambda: {"severity": severity, "message": "msg", "line": 3},
    )


class TestResolveConfigType:
    def test_auto_returns_none(self) -> None:
        assert _resolve_config_type("auto") is None

    def test_known_type_passes_through(self) -> None:
        assert _resolve_config_type("dockerfile") == "dockerfile"

    def test_unknown_type_returns_error_response(self) -> None:
        result = _resolve_config_type("bogus")
        assert isinstance(result, dict)
        assert result["error"]["code"] == "invalid_config_type"


class TestReadConfigContent:
    def test_reads_utf8_content(self, tmp_path) -> None:
        f = tmp_path / "Dockerfile"
        f.write_text("FROM python:3.12\n", encoding="utf-8")
        assert _read_config_content(f) == "FROM python:3.12\n"

    def test_missing_file_returns_file_error(self, tmp_path) -> None:
        result = _read_config_content(tmp_path / "nope")
        assert isinstance(result, dict)
        assert result["error"]["code"] == "file_error"

    def test_oversized_file_rejected(self, tmp_path) -> None:
        f = tmp_path / "big.yaml"
        f.write_text("x" * 10, encoding="utf-8")
        with patch("tapps_mcp.server_system_tools._MAX_CONFIG_FILE_SIZE", 5):
            result = _read_config_content(f)
        assert isinstance(result, dict)
        assert result["error"]["code"] == "file_too_large"

    def test_non_utf8_returns_decode_error(self, tmp_path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_bytes(b"\xff\xfe\x00binary")
        result = _read_config_content(f)
        assert isinstance(result, dict)
        assert result["error"]["code"] == "decode_error"


class TestBuildConfigResponseData:
    def test_counts_by_severity(self) -> None:
        result = SimpleNamespace(
            file_path="/p/Dockerfile",
            config_type="dockerfile",
            valid=False,
            findings=[_finding("critical"), _finding("warning"), _finding("warning")],
            suggestions=["pin base image"],
        )
        data = _build_config_response_data(result)
        assert data["finding_count"] == 3
        assert data["critical_count"] == 1
        assert data["warning_count"] == 2

    def test_empty_findings(self) -> None:
        result = SimpleNamespace(
            file_path="/p/Dockerfile",
            config_type="dockerfile",
            valid=True,
            findings=[],
            suggestions=[],
        )
        data = _build_config_response_data(result)
        assert data["finding_count"] == 0
        assert data["valid"] is True


class TestAttachConfigStructuredOutput:
    def test_attaches_structured_content(self) -> None:
        result = SimpleNamespace(
            file_path="/p/Dockerfile",
            config_type="dockerfile",
            valid=False,
            findings=[_finding("critical")],
            suggestions=[],
        )
        resp: dict[str, Any] = {"data": _build_config_response_data(result)}
        _attach_config_structured_output(resp, result)
        assert "structuredContent" in resp

    def test_malformed_result_does_not_raise(self) -> None:
        resp: dict[str, Any] = {"data": {}}
        _attach_config_structured_output(resp, SimpleNamespace())
        assert "structuredContent" not in resp


class TestTappsServerInfoDelegates:
    @pytest.mark.asyncio
    async def test_delegates_to_server_info_async(self) -> None:
        sentinel = {"tool": "tapps_server_info", "success": True, "data": {}}
        with patch(
            "tapps_mcp.server._server_info_async",
            return_value=sentinel,
        ) as mock_impl:
            result = await tapps_server_info()
        assert result is sentinel
        mock_impl.assert_called_once()


class TestServerInfoNoOverlap:
    """TAP-6435: tapps_server_info must not duplicate tapps_session_start(quick=True).

    ``server`` (name/version/protocol_version) is a named, asserted
    exception (see server._SERVER_INFO_FIELDS_DUPLICATED_BY_QUICK_SESSION_START):
    it is the minimal identity tapps_server_info's own "verify a remote
    deployment is reachable" use case needs without session_start having
    run first. Any other shared top-level field is the TAP-6433 duplication
    bug reappearing.
    """

    @pytest.mark.asyncio
    async def test_server_info_no_overlap_with_quick_session_start(self) -> None:
        from tapps_mcp.server import _server_info_async
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        quick_result = await tapps_session_start()
        info_result = await _server_info_async(trim_duplicated_fields=True)

        quick_keys = set(quick_result["data"].keys())
        info_keys = set(info_result["data"].keys())

        assert quick_keys & info_keys == {"server"}
