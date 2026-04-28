"""TAP-1080: tapps_memory store init failure handling.

Covers two production reliability bugs found in the 30-day audit:

- Generic ``store_init_failed`` errors lump together import errors, missing
  DSN, auth failures, and connection failures. Agents cannot pick the right
  remediation. Now each ``store_init_failed`` carries a ``sub_code``.
- Async actions that need the local store (e.g. ``consolidate``) used to
  null-deref with "'NoneType' object has no attribute 'list_all'" when the
  bridge was in HTTP mode. The async dispatch now returns a structured
  ``http_mode_not_supported`` error, mirroring the sync path.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tapps_mcp.server_memory_tools import _classify_store_init_error, tapps_memory


async def _noop_init() -> None:
    """Async no-op replacement for ensure_session_initialized."""


@pytest.fixture(autouse=True)
def _mock_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tapps_mcp.server_memory_tools.ensure_session_initialized",
        _noop_init,
    )


class TestClassifyStoreInitError:
    """The sub-code classifier maps exceptions to actionable codes."""

    def test_import_error_class(self) -> None:
        exc = ImportError("cannot import name 'EmbeddingProvider' from 'tapps_brain.embeddings'")
        assert _classify_store_init_error(exc) == "import_error"

    def test_no_module_named_message(self) -> None:
        exc = RuntimeError("no module named 'tapps_brain.embeddings'")
        assert _classify_store_init_error(exc) == "import_error"

    def test_dsn_missing(self) -> None:
        exc = RuntimeError(
            "Memory store unavailable: neither TAPPS_BRAIN_DATABASE_URL nor "
            "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL is configured."
        )
        assert _classify_store_init_error(exc) == "dsn_missing"

    def test_auth_failed_403(self) -> None:
        exc = RuntimeError("403 Forbidden: invalid token")
        assert _classify_store_init_error(exc) == "auth_failed"

    def test_auth_failed_unauthorized(self) -> None:
        exc = RuntimeError("Unauthorized: bearer token rejected")
        assert _classify_store_init_error(exc) == "auth_failed"

    def test_connection_refused(self) -> None:
        exc = RuntimeError("connection refused: localhost:5432")
        assert _classify_store_init_error(exc) == "connection_failed"

    def test_connection_timeout(self) -> None:
        exc = RuntimeError("timeout connecting to brain")
        assert _classify_store_init_error(exc) == "connection_failed"

    def test_unknown_falls_through(self) -> None:
        exc = RuntimeError("something completely unrelated")
        assert _classify_store_init_error(exc) == "unknown"


@pytest.mark.asyncio()
class TestStoreInitFailedSubCode:
    """The store_init_failed error envelope carries a discriminating sub_code."""

    async def test_dsn_missing_sub_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise() -> None:
            raise RuntimeError(
                "Memory store unavailable: neither TAPPS_BRAIN_DATABASE_URL nor "
                "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL is configured."
            )

        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools._get_memory_store",
            _raise,
        )

        result = await tapps_memory(action="search", query="x")

        assert result["success"] is False
        assert result["error"]["code"] == "store_init_failed"
        assert result["error"]["sub_code"] == "dsn_missing"
        assert result["error"]["exception_type"] == "RuntimeError"

    async def test_import_error_sub_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise() -> None:
            raise ImportError(
                "cannot import name 'EmbeddingProvider' from 'tapps_brain.embeddings'"
            )

        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools._get_memory_store",
            _raise,
        )

        result = await tapps_memory(action="save", key="k", value="v")

        assert result["error"]["code"] == "store_init_failed"
        assert result["error"]["sub_code"] == "import_error"
        assert result["error"]["exception_type"] == "ImportError"

    async def test_auth_failed_sub_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise() -> None:
            raise RuntimeError('{"error":"forbidden","detail":"Invalid token."}')

        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools._get_memory_store",
            _raise,
        )

        result = await tapps_memory(action="health")

        assert result["error"]["code"] == "store_init_failed"
        assert result["error"]["sub_code"] == "auth_failed"


@pytest.mark.asyncio()
class TestAsyncDispatchNoneStoreGuard:
    """Async dispatch guards against null-deref when store is None.

    Before TAP-1080, store=None reached async handlers like _handle_consolidate
    that bare-access store.list_all() and crashed with "'NoneType' object has
    no attribute 'list_all'". The dispatch now returns a structured error.
    """

    async def test_consolidate_with_none_store_returns_structured_error(self) -> None:
        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=None,
        ):
            result = await tapps_memory(action="consolidate")

        assert result["success"] is False
        assert result["error"]["code"] == "http_mode_not_supported"
        assert "consolidate" in result["error"]["message"]

    async def test_validate_with_none_store_returns_structured_error(self) -> None:
        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=None,
        ):
            result = await tapps_memory(action="validate", key="x")

        assert result["success"] is False
        assert result["error"]["code"] == "http_mode_not_supported"

    async def test_hive_status_with_none_store_does_not_crash(self) -> None:
        """hive_status is on the HTTP-OK allowlist — None store must not block it."""
        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=None,
        ):
            result = await tapps_memory(action="hive_status")

        # hive_status returns success=True with degraded info; it must NOT
        # be the http_mode_not_supported gate.
        if result.get("success") is False:
            assert result.get("error", {}).get("code") != "http_mode_not_supported"

    async def test_health_with_none_store_does_not_crash(self) -> None:
        """health is on the HTTP-OK allowlist."""
        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=None,
        ):
            result = await tapps_memory(action="health")

        if result.get("success") is False:
            assert result.get("error", {}).get("code") != "http_mode_not_supported"
