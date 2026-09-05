"""Tests for server_lookup_tools — tapps_lookup_docs and its response builders."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.server_lookup_tools import (
    _VALID_LOOKUP_MODES,
    _build_lookup_data,
    _lookup_error_code,
    _sanitize_lookup_param,
    tapps_lookup_docs,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")


def _lookup_result(**overrides: object) -> SimpleNamespace:
    """Build a LookupResult-shaped stub with sane defaults."""
    base: dict[str, object] = {
        "success": True,
        "library": "httpx",
        "topic": "overview",
        "source": "context7",
        "cache_hit": False,
        "response_time_ms": 12,
        "content": "docs body",
        "context7_id": None,
        "matched_library_id": None,
        "resolution_confidence": None,
        "likely_local_module": False,
        "fuzzy_score": None,
        "error": None,
        "warning": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestSanitizeLookupParam:
    def test_strips_control_characters(self) -> None:
        assert _sanitize_lookup_param("ht\x00tp\x1fx") == "httpx"

    def test_truncates_to_max_len(self) -> None:
        assert _sanitize_lookup_param("a" * 200) == "a" * 100

    def test_respects_explicit_max_len(self) -> None:
        assert _sanitize_lookup_param("a" * 20, max_len=5) == "a" * 5

    def test_trims_surrounding_whitespace(self) -> None:
        assert _sanitize_lookup_param("  httpx  ") == "httpx"


class TestLookupErrorCode:
    def test_none_when_no_error(self) -> None:
        assert _lookup_error_code(None) is None
        assert _lookup_error_code("") is None

    def test_api_key_missing_detected(self) -> None:
        assert _lookup_error_code("No Context7 API key configured.") == "api_key_missing"

    def test_generic_failure(self) -> None:
        assert _lookup_error_code("upstream exploded") == "lookup_failed"


class TestBuildLookupData:
    def test_includes_core_fields_and_token_estimate(self) -> None:
        data = _build_lookup_data(_lookup_result(content="abcdefgh"))
        assert data["library"] == "httpx"
        assert data["source"] == "context7"
        assert data["token_estimate"] == len("abcdefgh") // 4

    def test_omits_optional_fields_when_unset(self) -> None:
        data = _build_lookup_data(_lookup_result())
        assert "context7_id" not in data
        assert "fuzzy_score" not in data
        assert "likely_local_module" not in data

    def test_includes_optional_fields_when_set(self) -> None:
        data = _build_lookup_data(
            _lookup_result(
                context7_id="/encode/httpx",
                matched_library_id="/encode/httpx",
                resolution_confidence="high",
                likely_local_module=True,
                fuzzy_score=0.91,
            )
        )
        assert data["context7_id"] == "/encode/httpx"
        assert data["resolution_confidence"] == "high"
        assert data["likely_local_module"] is True
        assert data["fuzzy_score"] == 0.91

    def test_context7_hint_added_on_fallback_without_key(self, monkeypatch) -> None:
        monkeypatch.delenv("TAPPS_MCP_CONTEXT7_API_KEY", raising=False)
        monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
        data = _build_lookup_data(_lookup_result(source="llmstxt"))
        assert "context7_hint" in data

    def test_no_context7_hint_when_key_present(self, monkeypatch) -> None:
        monkeypatch.setenv("TAPPS_MCP_CONTEXT7_API_KEY", "sk-test")
        data = _build_lookup_data(_lookup_result(source="llmstxt"))
        assert "context7_hint" not in data


class TestTappsLookupDocs:
    @pytest.mark.asyncio
    async def test_invalid_mode_rejected(self) -> None:
        result = await tapps_lookup_docs("httpx", mode="not-a-mode")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_mode"

    @pytest.mark.asyncio
    async def test_empty_library_rejected(self) -> None:
        result = await tapps_lookup_docs("   ")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_library"

    @pytest.mark.asyncio
    async def test_success_path_returns_data(self) -> None:
        engine = AsyncMock()
        engine.lookup.return_value = _lookup_result()
        with patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine):
            result = await tapps_lookup_docs("httpx", topic="async client")
        assert result["success"] is True
        assert result["data"]["library"] == "httpx"
        engine.lookup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_engine_exception_returns_lookup_failed(self) -> None:
        engine = AsyncMock()
        engine.lookup.side_effect = RuntimeError("network down")
        with patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine):
            result = await tapps_lookup_docs("httpx")
        assert result["success"] is False
        assert result["error"]["code"] == "lookup_failed"

    @pytest.mark.asyncio
    async def test_engine_failure_result_surfaces_error_code(self) -> None:
        engine = AsyncMock()
        engine.lookup.return_value = _lookup_result(
            success=False, error="No Context7 API key configured.", content=None
        )
        with (
            patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine),
            patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None),
        ):
            result = await tapps_lookup_docs("httpx")
        assert result["success"] is False
        assert result["error"]["code"] == "api_key_missing"

    @pytest.mark.asyncio
    async def test_api_key_missing_fallback_uses_brain_when_reachable(self) -> None:
        """TAP-6443: an api_key_missing failure falls back to brain docs."""
        engine = AsyncMock()
        engine.lookup.return_value = _lookup_result(
            success=False, error="No Context7 API key configured.", content=None
        )
        brain_result = _lookup_result(source="brain", content="brain docs body")
        with (
            patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine),
            patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=object()),
            patch(
                "tapps_core.knowledge.brain_docs.lookup_via_brain",
                new_callable=AsyncMock,
                return_value=brain_result,
            ),
        ):
            result = await tapps_lookup_docs("httpx")
        assert result["success"] is True
        assert result["data"]["content"] == "brain docs body"
        assert result["data"]["source"] == "brain"

    @pytest.mark.asyncio
    async def test_api_key_missing_fallback_names_setting_and_repo_when_no_route(
        self,
    ) -> None:
        """TAP-6443: with no brain route, the error names the setting and repo."""
        engine = AsyncMock()
        engine.lookup.return_value = _lookup_result(
            success=False, error="No Context7 API key configured.", content=None
        )
        with (
            patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine),
            patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None),
        ):
            result = await tapps_lookup_docs("httpx")
        assert result["success"] is False
        assert result["error"]["code"] == "api_key_missing"
        assert "TAPPS_MCP_CONTEXT7_API_KEY" in result["error"]["message"]
        assert "project_root=" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_warning_is_propagated(self) -> None:
        engine = AsyncMock()
        engine.lookup.return_value = _lookup_result(warning="stale cache")
        with patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine):
            result = await tapps_lookup_docs("httpx")
        assert result["warning"] == "stale cache"


def test_valid_lookup_modes_contract() -> None:
    assert frozenset({"code", "info"}) == _VALID_LOOKUP_MODES
