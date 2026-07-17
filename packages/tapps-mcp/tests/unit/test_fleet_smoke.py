"""Tests for HTTP fleet MCP smoke probes (ADR-0024)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.distribution import fleet_smoke


def _sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


class TestParseSseJson:
    def test_extracts_first_data_line(self) -> None:
        body = _sse({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
        parsed = fleet_smoke.parse_sse_json(body)
        assert parsed is not None
        assert parsed["id"] == 1

    def test_returns_none_for_garbage(self) -> None:
        assert fleet_smoke.parse_sse_json("not sse") is None


class TestProbeFleetMcpInitialize:
    def test_happy_path(self) -> None:
        init_body = _sse(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"serverInfo": {"name": "TappsMCP"}},
            }
        )
        with patch.object(
            fleet_smoke,
            "_post_mcp",
            return_value=(200, "sess-1", init_body),
        ):
            result = fleet_smoke.probe_fleet_mcp_initialize("nlt-build")
        assert result["ok"] is True
        assert result["stage"] == "initialize"

    def test_timeout_style_failure(self) -> None:
        with patch.object(
            fleet_smoke,
            "_post_mcp",
            return_value=(0, None, "connection failed: timed out"),
        ):
            result = fleet_smoke.probe_fleet_mcp_initialize("nlt-build")
        assert result["ok"] is False
        assert result["stage"] == "initialize"


class TestProbeFleetMcpSession:
    def test_happy_path(self) -> None:
        init_body = _sse(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "serverInfo": {"name": "TappsMCP", "version": "3.12.46"},
                },
            }
        )
        tools_body = _sse(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": [{"name": "tapps_session_start"}]},
            }
        )
        responses = [
            (200, "sess-1", init_body),
            (202, "sess-1", ""),
            (200, "sess-1", tools_body),
        ]

        def fake_post(*_args: Any, **_kwargs: Any) -> tuple[int, str | None, str]:
            return responses.pop(0)

        with patch.object(fleet_smoke, "_post_mcp", side_effect=fake_post):
            result = fleet_smoke.probe_fleet_mcp_session("nlt-build")

        assert result["ok"] is True
        assert result["tool_count"] == 1
        assert result["server_name"] == "TappsMCP"

    def test_initialize_failure(self) -> None:
        with patch.object(
            fleet_smoke,
            "_post_mcp",
            return_value=(406, None, "Not Acceptable"),
        ):
            result = fleet_smoke.probe_fleet_mcp_session("nlt-build")

        assert result["ok"] is False
        assert result["stage"] == "initialize"

    def test_connection_refused_is_a_failed_stage_not_a_crash(self) -> None:
        """Regression: deploy-local crashed with an unhandled URLError when a
        just-restarted fleet server had not bound its port yet. _post_mcp must
        translate connection errors into a failed probe result instead.
        """
        import io
        import urllib.error
        import urllib.request

        refused = urllib.error.URLError(OSError(111, "Connection refused"))
        with patch.object(urllib.request, "urlopen", side_effect=refused):
            result = fleet_smoke.probe_fleet_mcp_session("nlt-build")

        assert result["ok"] is False
        assert result["stage"] == "initialize"
        assert "connection failed" in result["error"]

        # HTTPError (has a real status) must keep flowing through unchanged.
        http_err = urllib.error.HTTPError(
            "http://127.0.0.1:8760/mcp",
            500,
            "boom",
            {},
            io.BytesIO(b"body"),  # type: ignore[arg-type]
        )
        with patch.object(urllib.request, "urlopen", side_effect=http_err):
            result = fleet_smoke.probe_fleet_mcp_session("nlt-build")
        assert result["ok"] is False
        assert result["http_status"] == 500


class TestSmokeTestFleet:
    def test_aggregates_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_probe(server_id: str, **_kw: Any) -> dict[str, Any]:
            if server_id == "nlt-build":
                return {"ok": True, "server_id": server_id, "tool_count": 3}
            return {"ok": False, "server_id": server_id, "stage": "initialize", "error": "down"}

        monkeypatch.setattr(fleet_smoke, "probe_fleet_mcp_session", fake_probe)
        result = fleet_smoke.smoke_test_fleet()
        assert result["ok"] is False
        assert result["passed"] == 1
        assert result["total"] == 6
        assert any("nlt-memory" in item for item in result["failures"])

    def test_all_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            fleet_smoke,
            "probe_fleet_mcp_session",
            lambda server_id, **_kw: {"ok": True, "server_id": server_id, "tool_count": 1},
        )
        result = fleet_smoke.smoke_test_fleet()
        assert result["ok"] is True
        assert result["passed"] == 6


class TestRestartFleetWithSmoke:
    def test_restart_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tapps_mcp.distribution import fleet_control

        calls: list[str] = []
        monkeypatch.setattr(fleet_control, "stop_fleet", lambda: calls.append("stop") or {})
        monkeypatch.setattr(
            fleet_control,
            "start_fleet",
            lambda *, force: (
                calls.append(f"start:{force}") or {"started": ["nlt-build"], "errors": []}
            ),
        )
        monkeypatch.setattr(
            fleet_control,
            "_wait_fleet_ports_listening",
            lambda **_: calls.append("wait") or [],
        )
        monkeypatch.setattr(
            fleet_smoke,
            "smoke_test_fleet",
            lambda **_: {"ok": True, "passed": 6, "total": 6, "servers": {}, "failures": []},
        )
        report = fleet_control.restart_fleet_with_smoke()
        assert calls == ["stop", "start:True", "wait"]
        assert report["ok"] is True
        assert report["not_ready"] == []

    def test_restart_fails_when_ports_never_bind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tapps_mcp.distribution import fleet_control

        monkeypatch.setattr(fleet_control, "stop_fleet", lambda: {})
        monkeypatch.setattr(
            fleet_control,
            "start_fleet",
            lambda *, force: {"started": [], "errors": []},
        )
        monkeypatch.setattr(
            fleet_control,
            "_wait_fleet_ports_listening",
            lambda **_: ["nlt-build"],
        )
        monkeypatch.setattr(
            fleet_smoke,
            "smoke_test_fleet",
            lambda **_: {"ok": True, "passed": 6, "total": 6, "servers": {}, "failures": []},
        )
        report = fleet_control.restart_fleet_with_smoke()
        assert report["ok"] is False
        assert report["not_ready"] == ["nlt-build"]
