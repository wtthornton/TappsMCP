"""Hive / Agent Teams session wiring (Epic M3 chunk B)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_core.config.settings import load_settings


def test_collect_session_hive_status_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()
    settings = load_settings()
    out = collect_session_hive_status(settings)
    assert out["enabled"] is False
    assert "propagation_config" not in out


def test_collect_session_hive_status_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Happy-path hive status — mocks the hive store (v3 removed file-backed HiveStore).

    tapps-brain v3 (ADR-007) removed the file-backed HiveStore; a Postgres DSN is
    required for a real hive backend.  The test mocks _ensure_hive_singletons to
    inject a minimal stub and a real AgentRegistry, exercising the non-degraded
    code path without requiring Postgres.
    """
    from unittest.mock import MagicMock

    from tapps_brain.backends import AgentRegistry

    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()
    settings = load_settings()

    # Stub hive store with list_namespaces (file-backed store removed in v3).
    mock_store = MagicMock()
    mock_store.list_namespaces.return_value = ["universal", "test"]
    real_registry = AgentRegistry(registry_path=tmp_path / "agents.yaml")

    with patch(
        "tapps_mcp.server_helpers._ensure_hive_singletons",
        return_value=(mock_store, real_registry, None),
    ):
        result = collect_session_hive_status(settings)

    assert result["enabled"] is True
    assert result.get("degraded") is False
    assert "agent_id" in result
    assert isinstance(result.get("namespaces"), list)
    assert result.get("registered_agents_count", 0) >= 1
    assert "propagation_config" not in result


def test_collect_session_hive_status_degraded_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()

    def _boom() -> tuple[None, None, str]:
        return None, None, "simulated import failure"

    with patch("tapps_mcp.server_helpers._ensure_hive_singletons", _boom):
        settings = load_settings()
        result = collect_session_hive_status(settings)
    assert result["enabled"] is True
    assert result.get("degraded") is True
    assert "simulated import failure" in (result.get("message") or "")
    assert "propagation_config" not in result


def test_collect_session_hive_status_reports_missing_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Agent Teams is on but TAPPS_BRAIN_DATABASE_URL is unset, the status
    message must name the missing DSN — not the misleading
    ``Hive singleton initialization failed`` that masked the real cause.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()
    settings = load_settings()
    result = collect_session_hive_status(settings)

    assert result["enabled"] is True
    assert result.get("degraded") is True
    message = result.get("message") or ""
    assert "TAPPS_BRAIN_DATABASE_URL" in message
    assert "not configured" in message


def test_collect_session_hive_status_reports_bad_dsn_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-postgres DSN schemes must be reported by name, not swallowed."""
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "sqlite:///tmp/brain.db")
    from tapps_mcp.server_helpers import _reset_hive_store_cache, collect_session_hive_status

    _reset_hive_store_cache()
    settings = load_settings()
    result = collect_session_hive_status(settings)

    assert result["enabled"] is True
    assert result.get("degraded") is True
    message = result.get("message") or ""
    assert "sqlite" in message
    assert "postgres" in message


def test_ensure_hive_singletons_caches_backend_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``create_hive_backend`` raising should surface the exception message and
    cache it so we don't retry a known-broken DSN on every call.
    """
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://nope:5432/x")
    from tapps_mcp import server_helpers
    from tapps_mcp.server_helpers import _ensure_hive_singletons, _reset_hive_store_cache

    _reset_hive_store_cache()

    call_count = {"n": 0}

    def _boom(_dsn: str) -> object:
        call_count["n"] += 1
        raise RuntimeError("connection refused")

    monkeypatch.setattr("tapps_brain.backends.create_hive_backend", _boom, raising=True)

    _, _, err1 = _ensure_hive_singletons()
    _, _, err2 = _ensure_hive_singletons()

    assert err1 is not None
    assert "connection refused" in err1
    assert err1 == err2
    assert call_count["n"] == 1, "backend failure should be cached, not retried"
    assert server_helpers._hive_init_error is not None


@pytest.mark.asyncio
async def test_session_start_quick_includes_hive_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    from tapps_mcp.server_helpers import _reset_hive_store_cache
    from tapps_mcp.server_pipeline_tools import _session_start_quick

    _reset_hive_store_cache()
    start_ns = 0

    def _noop_record(_tool: str, _ns: int) -> None:
        return None

    def _noop_nudges(_tool: str, resp: dict, _ctx: dict) -> dict:
        return resp

    result = await _session_start_quick(start_ns, _noop_record, _noop_nudges)
    assert result["success"] is True
    hs = result["data"].get("hive_status")
    assert hs is not None
    assert hs.get("enabled") is False
    assert "propagation_config" not in hs
