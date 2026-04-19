"""Hive / Agent Teams session wiring (TAP-572).

tapps-mcp is a client of tapps-brain. Hive status is reported by asking the
BrainBridge, not by reading ``TAPPS_BRAIN_DATABASE_URL`` locally. These tests
prove ``collect_session_hive_status`` never touches the Postgres DSN directly
and instead routes through ``BrainBridge.hive_status``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.config.settings import load_settings


@pytest.mark.asyncio
async def test_collect_session_hive_status_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent Teams flag unset -> baseline (no probe, no bridge touch)."""
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    from tapps_mcp.server_helpers import collect_session_hive_status

    settings = load_settings()
    out = await collect_session_hive_status(settings)
    assert out == {"enabled": False}


@pytest.mark.asyncio
async def test_collect_session_hive_status_unknown_when_bridge_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent Teams on + brain unreachable -> ``enabled: "unknown"``.

    TAP-572: client must not fabricate a DSN-required error. When the
    BrainBridge is ``None`` we report ``enabled: "unknown"`` with a message
    pointing at brain connectivity (``TAPPS_BRAIN_BASE_URL`` /
    ``TAPPS_BRAIN_AUTH_TOKEN`` / ``TAPPS_BRAIN_DATABASE_URL`` on the brain
    server) — never at a missing local DSN.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
    from tapps_mcp.server_helpers import collect_session_hive_status

    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
        settings = load_settings()
        result = await collect_session_hive_status(settings)

    assert result["enabled"] == "unknown"
    assert result.get("degraded") is True
    message = result.get("message") or ""
    # Must NOT claim a local DSN is required.
    assert "Postgres DSN required" not in message
    assert "ADR-007" not in message
    # Must point at brain connectivity.
    assert "tapps-brain" in message


def test_server_helpers_removed_client_side_dsn_probe() -> None:
    """Regression for TAP-572: the prior DSN-probing ``_ensure_hive_singletons``
    helper (and its file-backed Hive backend construction) must be removed
    from the client module. Clients route via :class:`BrainBridge`, not via
    their own Postgres-backed Hive backend.
    """
    from tapps_mcp import server_helpers

    assert not hasattr(server_helpers, "_ensure_hive_singletons"), (
        "_ensure_hive_singletons was a client-side DSN probe — removed by TAP-572."
    )
    assert not hasattr(server_helpers, "_get_hive_store"), (
        "_get_hive_store backed a client-side Hive backend — removed by TAP-572."
    )
    assert not hasattr(server_helpers, "_get_hive_registry"), (
        "_get_hive_registry backed a client-side Hive backend — removed by TAP-572."
    )


@pytest.mark.asyncio
async def test_collect_session_hive_status_delegates_to_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: bridge present -> delegates to ``bridge.hive_status``.

    The client reads whatever the brain returns; it does not second-guess
    the result with a local DSN check.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.setenv("CLAUDE_AGENT_ID", "agent-test-1")
    monkeypatch.setenv("CLAUDE_AGENT_NAME", "test-agent")
    from tapps_mcp.server_helpers import collect_session_hive_status

    brain_response: dict[str, Any] = {
        "enabled": True,
        "degraded": False,
        "namespaces": ["universal", "repo-brain"],
        "namespace_count": 2,
        "agents": [{"id": "agent-test-1", "name": "test-agent"}],
        "agent_count": 1,
    }
    fake_bridge = MagicMock()
    fake_bridge.hive_status = AsyncMock(return_value=brain_response)

    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake_bridge):
        settings = load_settings()
        result = await collect_session_hive_status(settings)

    fake_bridge.hive_status.assert_awaited_once()
    call_kwargs = fake_bridge.hive_status.await_args.kwargs
    assert call_kwargs["agent_id"] == "agent-test-1"
    assert call_kwargs["agent_name"] == "test-agent"
    assert call_kwargs["register"] is True

    assert result["enabled"] is True
    assert result["degraded"] is False
    assert result["namespaces"] == ["universal", "repo-brain"]
    assert result["agent_id"] == "agent-test-1"
    assert result["registered_agents_count"] == 1


@pytest.mark.asyncio
async def test_collect_session_hive_status_forwards_bridge_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If brain says hive is degraded, tapps-mcp forwards that verbatim —
    no client-side "DSN required" rewriting.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    from tapps_mcp.server_helpers import collect_session_hive_status

    brain_response: dict[str, Any] = {
        "enabled": True,
        "degraded": True,
        "message": "Hive backend not available (no DSN or init failed).",
    }
    fake_bridge = MagicMock()
    fake_bridge.hive_status = AsyncMock(return_value=brain_response)

    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake_bridge):
        settings = load_settings()
        result = await collect_session_hive_status(settings)

    assert result["enabled"] is True
    assert result["degraded"] is True
    assert result["message"] == "Hive backend not available (no DSN or init failed)."


@pytest.mark.asyncio
async def test_collect_session_hive_status_handles_bridge_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exceptions from the bridge surface as ``degraded: true`` with the
    exception message, matching other optional tapps-brain integrations.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    from tapps_mcp.server_helpers import collect_session_hive_status

    fake_bridge = MagicMock()
    fake_bridge.hive_status = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake_bridge):
        settings = load_settings()
        result = await collect_session_hive_status(settings)

    assert result["enabled"] is True
    assert result["degraded"] is True
    assert "boom" in (result.get("message") or "")


@pytest.mark.asyncio
async def test_session_start_quick_does_not_require_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TAP-572: ``_session_start_quick`` must complete successfully without
    ``TAPPS_BRAIN_DATABASE_URL`` set, whether or not Agent Teams is on.
    """
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)

    from tapps_mcp.server_pipeline_tools import _session_start_quick

    start_ns = 0

    def _noop_record(_tool: str, _ns: int) -> None:
        return None

    def _noop_nudges(_tool: str, resp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return resp

    result = await _session_start_quick(start_ns, _noop_record, _noop_nudges)
    assert result["success"] is True
    hs = result["data"].get("hive_status")
    assert hs is not None
    # Agent Teams off -> baseline
    assert hs.get("enabled") is False


@pytest.mark.asyncio
async def test_session_start_quick_hive_unknown_when_agent_teams_without_brain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TAP-572: Agent Teams on + no brain -> ``hive_status.enabled == "unknown"``.

    The prior behavior produced
    ``"Hive unavailable: TAPPS_BRAIN_DATABASE_URL not configured ..."`` —
    this test is the regression proof that no such message is emitted.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)

    from tapps_mcp.server_pipeline_tools import _session_start_quick

    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
        start_ns = 0

        def _noop_record(_tool: str, _ns: int) -> None:
            return None

        def _noop_nudges(
            _tool: str,
            resp: dict[str, Any],
            _ctx: dict[str, Any],
        ) -> dict[str, Any]:
            return resp

        result = await _session_start_quick(start_ns, _noop_record, _noop_nudges)

    assert result["success"] is True
    hs = result["data"].get("hive_status")
    assert hs is not None
    assert hs.get("enabled") == "unknown"
    assert hs.get("degraded") is True
    message = hs.get("message") or ""
    assert "Postgres DSN required" not in message
    assert "ADR-007" not in message
