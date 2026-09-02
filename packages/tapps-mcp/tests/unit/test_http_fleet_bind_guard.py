"""Non-loopback fleet binds refuse to start without auth (TAP-6062, Story 2)."""

from __future__ import annotations

import ipaddress
from typing import Any

import pytest

from tapps_core.http.auth import FLEET_AUTH_ENV, FLEET_RUNTIME_ENV, FleetAuthConfig
from tapps_core.http.bind_policy import (
    NonLoopbackBindRefusedError,
    is_loopback_host,
    require_safe_bind,
    resolve_fleet_auth,
)
from tapps_mcp.distribution.nlt_http_fleet import (
    DEFAULT_FLEET_HOST,
    DEFAULT_FLEET_HOST_ENV,
    ensure_fleet_bind_allowed,
    fleet_bind_is_loopback,
    resolve_fleet_host,
)

# See test_http_fleet_auth.py: computed so S104 stays on for real bind sites.
WILDCARD_BIND = str(ipaddress.IPv4Address(0))


@pytest.fixture(autouse=True)
def _clean_fleet_env(monkeypatch: Any) -> None:
    for var in (DEFAULT_FLEET_HOST_ENV, FLEET_AUTH_ENV, FLEET_RUNTIME_ENV):
        monkeypatch.delenv(var, raising=False)


class TestConfigurableFleetHost:
    def test_default_is_loopback(self) -> None:
        assert DEFAULT_FLEET_HOST == "127.0.0.1"
        assert resolve_fleet_host() == "127.0.0.1"
        assert fleet_bind_is_loopback() is True

    def test_env_override_is_honored(self, monkeypatch: Any) -> None:
        monkeypatch.setenv(DEFAULT_FLEET_HOST_ENV, WILDCARD_BIND)
        assert resolve_fleet_host() == WILDCARD_BIND
        assert fleet_bind_is_loopback() is False

    def test_blank_override_falls_back_to_loopback(self, monkeypatch: Any) -> None:
        monkeypatch.setenv(DEFAULT_FLEET_HOST_ENV, "   ")
        assert resolve_fleet_host() == "127.0.0.1"


class TestEnsureFleetBindAllowed:
    def test_loopback_without_auth_is_fine(self) -> None:
        ensure_fleet_bind_allowed()

    def test_non_loopback_without_auth_refuses(self, monkeypatch: Any) -> None:
        monkeypatch.setenv(DEFAULT_FLEET_HOST_ENV, WILDCARD_BIND)
        with pytest.raises(NonLoopbackBindRefusedError):
            ensure_fleet_bind_allowed()

    def test_non_loopback_with_auth_is_allowed(self, monkeypatch: Any) -> None:
        monkeypatch.setenv(DEFAULT_FLEET_HOST_ENV, WILDCARD_BIND)
        monkeypatch.setenv(FLEET_AUTH_ENV, "op-secret")
        ensure_fleet_bind_allowed()


class TestRunServerStartupRefusal:
    """The ordering is structural: story 2 cannot ship without story 1."""

    def _run_server(self, monkeypatch: Any, host: str) -> list[Any]:
        from tapps_mcp import server as server_mod

        uvicorn_calls: list[Any] = []

        class _FakeUvicorn:
            @staticmethod
            def run(app: Any, **kwargs: Any) -> None:
                uvicorn_calls.append(kwargs)

        monkeypatch.setitem(__import__("sys").modules, "uvicorn", _FakeUvicorn)
        server_mod.run_server(transport="http", host=host, port=8760)
        return uvicorn_calls

    def test_non_loopback_bind_without_auth_never_reaches_uvicorn(self, monkeypatch: Any) -> None:
        with pytest.raises(NonLoopbackBindRefusedError, match="not loopback"):
            self._run_server(monkeypatch, WILDCARD_BIND)

    def test_non_loopback_bind_with_auth_starts(self, monkeypatch: Any) -> None:
        monkeypatch.setenv(FLEET_AUTH_ENV, "op-secret")
        calls = self._run_server(monkeypatch, WILDCARD_BIND)
        assert calls and calls[0]["host"] == WILDCARD_BIND

    def test_loopback_bind_without_auth_still_starts(self, monkeypatch: Any) -> None:
        calls = self._run_server(monkeypatch, "127.0.0.1")
        assert calls and calls[0]["host"] == "127.0.0.1"


class TestStartFleetPreflight:
    def test_start_fleet_refuses_non_loopback_without_auth(
        self, monkeypatch: Any, tmp_path: Any
    ) -> None:
        from tapps_mcp.distribution import fleet_control

        monkeypatch.setattr(
            fleet_control,
            "_build_fleet_process_env",
            lambda: {DEFAULT_FLEET_HOST_ENV: WILDCARD_BIND},
        )
        monkeypatch.setattr(fleet_control, "FLEET_PID_DIR", tmp_path / "pids")
        monkeypatch.setattr(fleet_control, "FLEET_LOG_DIR", tmp_path / "logs")

        spawned: list[Any] = []
        monkeypatch.setattr(
            fleet_control.subprocess,
            "Popen",
            lambda *a, **k: spawned.append(a),  # pragma: no cover - must not run
        )

        with pytest.raises(NonLoopbackBindRefusedError):
            fleet_control.start_fleet()
        assert spawned == []


class TestLoopbackClassification:
    @pytest.mark.parametrize("host", ["127.0.0.1", "::1", "[::1]", "localhost", "127.0.0.5"])
    def test_loopback_hosts(self, host: str) -> None:
        assert is_loopback_host(host) is True

    @pytest.mark.parametrize("host", [WILDCARD_BIND, "::", "192.168.1.10", "fleet.internal", ""])
    def test_non_loopback_hosts(self, host: str) -> None:
        assert is_loopback_host(host) is False

    def test_loopback_bind_allowed_without_auth(self) -> None:
        require_safe_bind("127.0.0.1", auth=FleetAuthConfig())

    def test_non_loopback_bind_refused_without_auth(self) -> None:
        with pytest.raises(NonLoopbackBindRefusedError, match="not loopback"):
            require_safe_bind(WILDCARD_BIND, auth=FleetAuthConfig())

    def test_non_loopback_bind_allowed_with_auth(self) -> None:
        require_safe_bind(WILDCARD_BIND, auth=FleetAuthConfig(operator_token="op"))

    def test_refusal_names_the_env_var_to_set(self) -> None:
        with pytest.raises(NonLoopbackBindRefusedError) as exc:
            require_safe_bind("192.168.1.10", auth=FleetAuthConfig())
        assert FLEET_AUTH_ENV in str(exc.value)


class TestResolveFleetAuth:
    """One call resolves the tokens and enforces the guard, so neither is skipped."""

    def test_returns_config_and_permits_loopback(self) -> None:
        auth = resolve_fleet_auth("127.0.0.1", env={})
        assert auth.enabled is False

    def test_refuses_non_loopback_without_auth(self) -> None:
        with pytest.raises(NonLoopbackBindRefusedError):
            resolve_fleet_auth(WILDCARD_BIND, env={})

    def test_permits_non_loopback_with_auth(self) -> None:
        auth = resolve_fleet_auth(WILDCARD_BIND, env={FLEET_AUTH_ENV: "op-secret"})
        assert auth.enabled is True

    def test_runtime_scope_flag_is_carried_through(self) -> None:
        auth = resolve_fleet_auth(
            "127.0.0.1",
            allow_runtime_scope=True,
            env={FLEET_RUNTIME_ENV: "rt-secret"},
        )
        assert auth.allow_runtime_scope is True
        assert auth.runtime_token == "rt-secret"
