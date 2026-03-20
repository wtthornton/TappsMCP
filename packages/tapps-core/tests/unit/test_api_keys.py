"""Tests for tapps_core.security.api_keys — secure API key loading."""

from __future__ import annotations

from pydantic import SecretStr

from tapps_core.security.api_keys import load_api_key_from_env


class TestLoadApiKeyFromEnv:
    """Verify load_api_key_from_env wraps values in SecretStr."""

    def test_returns_secret_str_when_set(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_API_KEY", "sk-abc123")
        result = load_api_key_from_env("TEST_API_KEY")
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "sk-abc123"

    def test_returns_none_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("TEST_API_KEY", raising=False)
        result = load_api_key_from_env("TEST_API_KEY")
        assert result is None

    def test_returns_none_for_empty_string(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_API_KEY", "")
        result = load_api_key_from_env("TEST_API_KEY")
        assert result is None

    def test_secret_str_repr_hides_value(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_API_KEY", "super-secret")
        result = load_api_key_from_env("TEST_API_KEY")
        assert result is not None
        assert "super-secret" not in repr(result)
        assert "super-secret" not in str(result)
