"""TAP-523: BrainBridge.health_check and startup fail-fast coverage.

Probes:

* DSN reachability check via ``store.count()``.
* Pool config validation of
  ``TAPPS_BRAIN_PG_POOL_MAX_WAITING`` and
  ``TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS`` env vars.
* Optional ``store.health()`` native probe.
* ``create_brain_bridge`` fails fast (returns None + logs) when health is bad.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_brain(*, count_raises: Exception | None = None, health: Any = None) -> MagicMock:
    brain = MagicMock()
    store = MagicMock()
    if count_raises is not None:
        store.count.side_effect = count_raises
    else:
        store.count.return_value = 7
    if health is None:
        store.health.return_value = MagicMock(
            model_dump=lambda: {"store_available": True, "current_count": 7}
        )
    else:
        store.health.return_value = health
    brain.store = store
    brain.hive = None
    return brain


@pytest.fixture
def bridge() -> Any:
    from tapps_core.brain_bridge import BrainBridge

    return BrainBridge(_make_brain())


class TestHealthCheckDSN:
    def test_ok_when_store_count_succeeds(self, bridge: Any) -> None:
        report = bridge.health_check()
        assert report["ok"] is True
        assert report["dsn_reachable"] is True
        assert report["details"]["entry_count"] == 7
        assert report["errors"] == []

    def test_fails_when_store_count_raises(self) -> None:
        from tapps_core.brain_bridge import BrainBridge

        b = BrainBridge(_make_brain(count_raises=RuntimeError("connection refused")))
        report = b.health_check()
        assert report["ok"] is False
        assert report["dsn_reachable"] is False
        assert any("dsn_unreachable" in e for e in report["errors"])


class TestHealthCheckPoolConfig:
    def test_accepts_valid_pool_vars(self, bridge: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_WAITING", "15")
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS", "600")
        report = bridge.health_check()
        assert report["pool_config_valid"] is True
        assert report["ok"] is True
        assert report["details"]["tapps_brain_pg_pool_max_waiting"] == 15
        assert report["details"]["tapps_brain_pg_pool_max_lifetime_seconds"] == 600

    def test_rejects_non_integer(self, bridge: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_WAITING", "abc")
        report = bridge.health_check()
        assert report["pool_config_valid"] is False
        assert report["ok"] is False
        assert any("is not an integer" in e for e in report["errors"])

    def test_rejects_negative(self, bridge: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS", "-5")
        report = bridge.health_check()
        assert report["pool_config_valid"] is False
        assert report["ok"] is False
        assert any("must be >= 0" in e for e in report["errors"])

    def test_warns_on_short_lifetime(self, bridge: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS", "10")
        report = bridge.health_check()
        assert report["ok"] is True  # still valid, just suspicious
        assert any("unusually short" in w for w in report["warnings"])

    def test_ignores_unset_env_vars(self, bridge: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPPS_BRAIN_PG_POOL_MAX_WAITING", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS", raising=False)
        report = bridge.health_check()
        assert report["pool_config_valid"] is True


class TestHealthCheckNativeProbe:
    def test_native_health_ok_when_health_method_exists(self, bridge: Any) -> None:
        report = bridge.health_check()
        assert report["native_health_ok"] is True
        assert "native_health" in report["details"]
        assert report["details"]["native_health"]["store_available"] is True

    def test_native_health_probe_failure_is_non_fatal(self) -> None:
        from tapps_core.brain_bridge import BrainBridge

        brain = _make_brain()
        brain.store.health.side_effect = RuntimeError("rpc timeout")
        b = BrainBridge(brain)

        report = b.health_check()
        assert report["ok"] is True  # native probe is advisory
        assert report["native_health_ok"] is False
        assert any("native_health_probe_failed" in w for w in report["warnings"])

    def test_native_health_absent_is_non_fatal(self) -> None:
        from tapps_core.brain_bridge import BrainBridge

        brain = _make_brain()
        del brain.store.health
        b = BrainBridge(brain)

        report = b.health_check()
        assert report["ok"] is True
        assert report["native_health_ok"] is False


class TestCreateBrainBridgeStartupFailFast:
    def test_returns_bridge_when_health_check_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.delenv("TAPPS_BRAIN_PG_POOL_MAX_WAITING", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS", raising=False)
        from tapps_core.brain_bridge import BrainBridge, create_brain_bridge

        with patch("tapps_brain.AgentBrain", return_value=_make_brain()):
            result = create_brain_bridge(settings=None)
        assert isinstance(result, BrainBridge)

    def test_returns_none_when_health_check_dsn_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://bad/dsn")
        from tapps_core.brain_bridge import create_brain_bridge

        bad_brain = _make_brain(count_raises=RuntimeError("cannot connect"))
        with patch("tapps_brain.AgentBrain", return_value=bad_brain):
            result = create_brain_bridge(settings=None)
        assert result is None
        # Ensure brain.close was called to release the just-constructed pool
        bad_brain.close.assert_called_once()

    def test_returns_none_when_pool_config_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_WAITING", "not-an-int")
        from tapps_core.brain_bridge import create_brain_bridge

        with patch("tapps_brain.AgentBrain", return_value=_make_brain()):
            result = create_brain_bridge(settings=None)
        assert result is None

    def test_proceeds_with_warnings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.setenv("TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS", "5")
        from tapps_core.brain_bridge import BrainBridge, create_brain_bridge

        with patch("tapps_brain.AgentBrain", return_value=_make_brain()):
            result = create_brain_bridge(settings=None)
        assert isinstance(result, BrainBridge)
