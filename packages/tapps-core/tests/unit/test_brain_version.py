"""Tests for the remote tapps-brain version probe (TAP-519).

Covers:

- ``check_brain_version`` skips cleanly when the URL is empty.
- Returns ``ok=True`` when the reported version satisfies the pinned floor.
- Returns ``ok=False`` with a descriptive error when the version is below the floor.
- Returns ``ok=False`` + ``degraded=True`` on HTTP/network failure (non-fatal).
- ``create_brain_bridge`` wires the probe and stashes the result on the bridge.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_brain() -> MagicMock:
    brain = MagicMock()
    store = MagicMock()
    store.count.return_value = 0
    store.project_root = "."
    brain.store = store
    brain.hive = None
    return brain


def _mock_http_response(
    *,
    status_code: int = 200,
    json_payload: dict[str, Any] | None = None,
    raise_exc: Exception | None = None,
) -> Any:
    """Build a patchable replacement for ``httpx.get``."""

    def _fake_get(url: str, timeout: float) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        request = httpx.Request("GET", url)
        return httpx.Response(
            status_code=status_code,
            json=json_payload if json_payload is not None else {},
            request=request,
        )

    return _fake_get


# ---------------------------------------------------------------------------
# check_brain_version
# ---------------------------------------------------------------------------


class TestCheckBrainVersion:
    def test_skipped_when_url_empty(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        result = check_brain_version("")
        assert result["ok"] is True
        assert result["skipped"] is True
        assert result["degraded"] is False
        assert result["errors"] == []
        assert result["version"] is None

    def test_version_check_passes_when_floor_met(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(
            json_payload={"status": "ok", "service": "tapps-brain", "version": "3.18.0"},
        )
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example/")

        assert result["ok"] is True
        assert result["skipped"] is False
        assert result["version"] == "3.18.0"
        assert result["errors"] == []

    def test_version_check_passes_at_exact_floor(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(
            json_payload={"version": "3.17.0"},
        )
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is True
        assert result["version"] == "3.17.0"

    def test_version_check_fails_when_below_floor(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(json_payload={"version": "3.16.0"})
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is False
        assert result["version"] == "3.16.0"
        assert len(result["errors"]) == 1
        assert "3.16.0" in result["errors"][0]
        assert ">=3.17.0" in result["errors"][0]

    def test_version_check_fails_at_or_above_ceiling(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(json_payload={"version": "4.0.0"})
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is False
        assert result["version"] == "4.0.0"
        assert "4.0.0" in result["errors"][0]

    def test_version_check_network_error_marks_degraded(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(raise_exc=httpx.ConnectError("connection refused"))
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is False
        assert result["degraded"] is True
        assert result["version"] is None
        assert len(result["warnings"]) == 1
        assert "connection refused" in result["warnings"][0]
        # Network failure is reported as a warning, not an error — it's
        # non-fatal in the health contract.
        assert result["errors"] == []

    def test_version_check_http_error_marks_degraded(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(status_code=500, json_payload={"detail": "boom"})
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is False
        assert result["degraded"] is True
        assert result["warnings"] != []

    def test_version_check_missing_version_field_errors(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(json_payload={"status": "ok"})  # no "version"
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is False
        assert result["degraded"] is False  # protocol-level error, not transport
        assert "missing 'version'" in result["errors"][0]

    def test_version_check_unparseable_version_errors(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(json_payload={"version": "not-a-version"})
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example")

        assert result["ok"] is False
        assert "not-a-version" in result["errors"][0]

    def test_trailing_slash_stripped(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        called_url: list[str] = []

        def _capture(url: str, timeout: float) -> httpx.Response:
            called_url.append(url)
            return httpx.Response(
                status_code=200,
                json={"version": "3.8.0"},
                request=httpx.Request("GET", url),
            )

        with patch("tapps_core.brain_bridge.httpx.get", side_effect=_capture):
            check_brain_version("http://brain.example/")

        assert called_url == ["http://brain.example/health"]

    def test_custom_floor_and_ceiling(self) -> None:
        from tapps_core.brain_bridge import check_brain_version

        fake_get = _mock_http_response(json_payload={"version": "5.1.0"})
        with patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get):
            result = check_brain_version("http://brain.example", floor="5.0.0", ceiling="6.0.0")

        assert result["ok"] is True
        assert result["floor"] == "5.0.0"
        assert result["ceiling"] == "6.0.0"


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


class TestFactoryWiring:
    def test_bridge_stashes_skipped_result_when_url_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_core.brain_bridge import create_brain_bridge

        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")

        settings = MagicMock()
        settings.memory.database_url = "postgresql://x/db"
        settings.memory.profile = "repo-brain"
        settings.memory.hive_dsn = ""
        settings.memory.project_id = ""
        settings.memory.pg_pool_max_waiting = 0
        settings.memory.pg_pool_max_lifetime_seconds = 0
        settings.memory.brain_http_url = ""

        with patch("tapps_brain.AgentBrain", return_value=_make_brain()):
            bridge = create_brain_bridge(settings=settings)

        assert bridge is not None
        assert bridge.version_check["skipped"] is True
        assert bridge.version_check["ok"] is True

    def test_bridge_stashes_ok_result_when_version_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_core.brain_bridge import create_brain_bridge

        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")

        settings = MagicMock()
        settings.memory.database_url = "postgresql://x/db"
        settings.memory.profile = "repo-brain"
        settings.memory.hive_dsn = ""
        settings.memory.project_id = ""
        settings.memory.pg_pool_max_waiting = 0
        settings.memory.pg_pool_max_lifetime_seconds = 0
        settings.memory.brain_http_url = "http://brain.example"

        fake_get = _mock_http_response(json_payload={"version": "3.18.0"})
        with (
            patch("tapps_brain.AgentBrain", return_value=_make_brain()),
            patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get),
        ):
            bridge = create_brain_bridge(settings=settings)

        assert bridge is not None
        assert bridge.version_check["ok"] is True
        assert bridge.version_check["version"] == "3.18.0"
        assert bridge.version_check["skipped"] is False

    def test_bridge_still_returned_when_version_below_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Version mismatch is logged loudly but does not block the bridge.

        Callers (e.g. ``tapps_session_start``) surface ``bridge.version_check``
        to operators. Blocking bridge creation would hide other memory
        operations that might still work against an older brain.
        """
        from tapps_core.brain_bridge import create_brain_bridge

        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")

        settings = MagicMock()
        settings.memory.database_url = "postgresql://x/db"
        settings.memory.profile = "repo-brain"
        settings.memory.hive_dsn = ""
        settings.memory.project_id = ""
        settings.memory.pg_pool_max_waiting = 0
        settings.memory.pg_pool_max_lifetime_seconds = 0
        settings.memory.brain_http_url = "http://brain.example"

        fake_get = _mock_http_response(json_payload={"version": "3.6.0"})
        with (
            patch("tapps_brain.AgentBrain", return_value=_make_brain()),
            patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get),
        ):
            bridge = create_brain_bridge(settings=settings)

        assert bridge is not None
        assert bridge.version_check["ok"] is False
        assert "3.6.0" in bridge.version_check["errors"][0]

    def test_bridge_still_returned_on_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tapps_core.brain_bridge import create_brain_bridge

        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")

        settings = MagicMock()
        settings.memory.database_url = "postgresql://x/db"
        settings.memory.profile = "repo-brain"
        settings.memory.hive_dsn = ""
        settings.memory.project_id = ""
        settings.memory.pg_pool_max_waiting = 0
        settings.memory.pg_pool_max_lifetime_seconds = 0
        settings.memory.brain_http_url = "http://brain.example"

        fake_get = _mock_http_response(raise_exc=httpx.ConnectError("no route"))
        with (
            patch("tapps_brain.AgentBrain", return_value=_make_brain()),
            patch("tapps_core.brain_bridge.httpx.get", side_effect=fake_get),
        ):
            bridge = create_brain_bridge(settings=settings)

        assert bridge is not None
        assert bridge.version_check["ok"] is False
        assert bridge.version_check["degraded"] is True


# ---------------------------------------------------------------------------
# version_check property snapshot
# ---------------------------------------------------------------------------


class TestVersionCheckProperty:
    def test_default_version_check_is_skipped_sentinel(self) -> None:
        from tapps_core.brain_bridge import BrainBridge

        bridge = BrainBridge(_make_brain())
        snapshot = bridge.version_check
        assert snapshot["skipped"] is True
        assert snapshot["ok"] is True

    def test_version_check_returns_copy(self) -> None:
        """The property must return a defensive copy so callers can't mutate the cached result."""
        from tapps_core.brain_bridge import BrainBridge

        bridge = BrainBridge(_make_brain())
        snapshot = bridge.version_check
        snapshot["ok"] = False  # mutate the copy
        assert bridge.version_check["ok"] is True  # original untouched
