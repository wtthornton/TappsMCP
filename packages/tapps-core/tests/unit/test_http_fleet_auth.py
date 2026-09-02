"""Fleet bearer-token policy: which credential maps to which scope (TAP-6062)."""

from __future__ import annotations

from tapps_core.http.auth import (
    FLEET_AUTH_ENV,
    FLEET_RUNTIME_ENV,
    SCOPE_OPERATOR,
    SCOPE_RUNTIME,
    FleetAuthConfig,
    extract_presented_token,
)


class TestFleetAuthConfig:
    def test_disabled_when_no_token_configured(self) -> None:
        config = FleetAuthConfig()
        assert config.enabled is False
        # Loopback-only unauthenticated default is unchanged.
        assert config.authenticate(None) == SCOPE_OPERATOR

    def test_from_env_reads_both_tokens(self) -> None:
        config = FleetAuthConfig.from_env(
            {FLEET_AUTH_ENV: " op-secret ", FLEET_RUNTIME_ENV: "rt-secret"},
            allow_runtime_scope=True,
        )
        assert config.operator_token == "op-secret"
        assert config.runtime_token == "rt-secret"
        assert config.enabled is True

    def test_blank_token_is_not_a_token(self) -> None:
        config = FleetAuthConfig.from_env({FLEET_AUTH_ENV: "   "})
        assert config.operator_token is None
        assert config.enabled is False

    def test_operator_token_authenticates(self) -> None:
        config = FleetAuthConfig(operator_token="op-secret")
        assert config.authenticate("op-secret") == SCOPE_OPERATOR

    def test_wrong_token_is_rejected(self) -> None:
        config = FleetAuthConfig(operator_token="op-secret")
        assert config.authenticate("op-secre") is None
        assert config.authenticate("nope") is None

    def test_missing_token_is_rejected_when_enabled(self) -> None:
        config = FleetAuthConfig(operator_token="op-secret")
        assert config.authenticate(None) is None
        assert config.authenticate("") is None

    def test_runtime_token_only_on_runtime_scope_servers(self) -> None:
        build = FleetAuthConfig(runtime_token="rt", allow_runtime_scope=True)
        assert build.authenticate("rt") == SCOPE_RUNTIME

        other = FleetAuthConfig(runtime_token="rt", allow_runtime_scope=False)
        assert other.authenticate("rt") is None


class TestExtractPresentedToken:
    def test_bearer_authorization(self) -> None:
        assert extract_presented_token({"Authorization": "Bearer abc123"}) == "abc123"

    def test_bearer_is_case_insensitive(self) -> None:
        assert extract_presented_token({"authorization": "bearer abc123"}) == "abc123"

    def test_whole_value_header(self) -> None:
        assert extract_presented_token({"X-Tapps-Fleet-Token": "abc123"}) == "abc123"

    def test_non_bearer_authorization_ignored(self) -> None:
        assert extract_presented_token({"Authorization": "Basic abc123"}) is None

    def test_absent(self) -> None:
        assert extract_presented_token({}) is None
