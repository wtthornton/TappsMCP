"""Tests for tapps_core.brain_bridge_http_health — health/auth/close probes
for HttpBrainBridge.

Split out of test_brain_bridge_health_check.py alongside the TAP-6736
megafile split (and its own further split into session/health/memory/
kg_hive mixins).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from tapps_core.brain_bridge import HttpBrainBridge


def _make_bridge() -> HttpBrainBridge:
    return HttpBrainBridge("http://brain:8080", {"Authorization": "Bearer t"})


def _mock_response(status_code: int, payload: dict[str, Any] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    resp.raise_for_status = MagicMock()
    return resp


class TestHealthCheck:
    def test_ok_on_200_healthz(self) -> None:
        bridge = _make_bridge()
        with patch(
            "tapps_core.brain_bridge_http_health.httpx.get",
            return_value=_mock_response(200, {"ok": True, "db_ok": True, "mcp_ok": True}),
        ):
            result = bridge.health_check()
        assert result["ok"] is True
        assert result["details"]["db_ok"] is True

    def test_degraded_on_503(self) -> None:
        bridge = _make_bridge()
        with patch(
            "tapps_core.brain_bridge_http_health.httpx.get",
            return_value=_mock_response(503, {"db_ok": False, "mcp_ok": True}),
        ):
            result = bridge.health_check()
        assert result["ok"] is False
        assert "db_ok=false" in result["errors"][0]

    def test_falls_back_to_legacy_health_on_404(self) -> None:
        bridge = _make_bridge()

        def _get(url: str, **kwargs: Any) -> MagicMock:
            if url.endswith("/healthz"):
                return _mock_response(404)
            return _mock_response(200, {"version": "3.30.0", "status": "ok"})

        with patch("tapps_core.brain_bridge_http_health.httpx.get", side_effect=_get):
            result = bridge.health_check()
        assert result["ok"] is True
        assert result["details"]["brain_version"] == "3.30.0"

    def test_failure_when_circuit_open(self) -> None:
        bridge = _make_bridge()
        bridge._record_failure()
        bridge._record_failure()
        bridge._record_failure()
        assert bridge.circuit_open is True
        result = bridge.health_check()
        assert result["ok"] is False
        assert "circuit open" in result["errors"][0]

    def test_failure_on_network_error(self) -> None:
        bridge = _make_bridge()
        with patch(
            "tapps_core.brain_bridge_http_health.httpx.get",
            side_effect=ConnectionError("refused"),
        ):
            result = bridge.health_check()
        assert result["ok"] is False
        assert result["dsn_reachable"] is False


class TestDrainBlocking:
    def test_reports_empty_queue(self) -> None:
        bridge = _make_bridge()
        result = bridge.drain_blocking(timeout=0.1)
        assert result == {"drained": 0, "dropped": 0, "remaining": 0}
