"""Tests for ``tapps_core.brain_auth`` (TAP-521).

Scaffolding-only coverage: ``BrainBridge`` is in-process today, so there is no
HTTP path to assert against. These tests verify that ``build_brain_headers``
produces the correct header dict, honors strict mode, and that ``SecretStr``
protects the token from accidental leaks in logs / repr.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from tapps_core.brain_auth import BrainAuthConfigError, build_brain_headers
from tapps_core.config.settings import TappsMCPSettings

if TYPE_CHECKING:
    from collections.abc import Iterator

_TOKEN_VALUE = "s3cr3t-bearer-token"
_PROJECT_ID = "tapps-mcp"


def _make_settings(
    tmp_path: Path,
    *,
    token: str | None = _TOKEN_VALUE,
    project_id: str = _PROJECT_ID,
) -> TappsMCPSettings:
    """Build a settings object with the brain-auth fields populated."""
    settings = TappsMCPSettings(project_root=tmp_path)
    settings.memory.brain_auth_token = SecretStr(token) if token is not None else None
    settings.memory.brain_project_id = project_id
    # Ensure agent_id generation has a stable project slug to chain off.
    settings.memory.project_id = project_id
    return settings


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate each test from ambient ``TAPPS_BRAIN_STRICT`` / agent-id env."""
    monkeypatch.delenv("TAPPS_BRAIN_STRICT", raising=False)
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    yield


def test_headers_include_bearer_and_project_and_agent_id(tmp_path: Path) -> None:
    """All three headers appear when all three values are configured."""
    settings = _make_settings(tmp_path)

    headers = build_brain_headers(settings)

    assert headers["Authorization"] == f"Bearer {_TOKEN_VALUE}"
    assert headers["X-Project-Id"] == _PROJECT_ID
    assert headers["X-Agent-Id"].startswith(f"{_PROJECT_ID}-")


def test_secret_str_not_leaked_in_repr(tmp_path: Path) -> None:
    """``SecretStr`` masks the token value in ``repr(settings.memory)``."""
    settings = _make_settings(tmp_path)

    rendered = repr(settings.memory)

    assert _TOKEN_VALUE not in rendered
    # SecretStr renders as ``SecretStr('**********')`` — confirm the mask is
    # actually present so we don't pass trivially when the field is missing.
    assert "SecretStr" in rendered


def test_strict_mode_raises_when_token_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Strict mode raises ``BrainAuthConfigError`` on missing token."""
    monkeypatch.setenv("TAPPS_BRAIN_STRICT", "1")
    settings = _make_settings(tmp_path, token=None)

    with pytest.raises(BrainAuthConfigError) as excinfo:
        build_brain_headers(settings)

    assert "brain_auth_token" in str(excinfo.value)
    # Token must never appear in the error — even the sentinel value from the
    # default fixture should not be reachable here, but assert just in case.
    assert _TOKEN_VALUE not in str(excinfo.value)


def test_non_strict_warn_and_proceed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-strict mode returns best-effort headers with ``Authorization`` omitted.

    structlog writes to stdout rather than the stdlib logging framework, so we
    stub ``brain_auth.logger.warning`` directly to capture the call.
    """
    settings = _make_settings(tmp_path, token=None)

    warnings: list[tuple[str, dict[str, Any]]] = []

    def _record_warning(event: str, **kwargs: Any) -> None:
        warnings.append((event, kwargs))

    monkeypatch.setattr("tapps_core.brain_auth.logger.warning", _record_warning)

    headers = build_brain_headers(settings)

    assert "Authorization" not in headers
    assert headers["X-Project-Id"] == _PROJECT_ID
    assert headers["X-Agent-Id"].startswith(f"{_PROJECT_ID}-")
    assert warnings, "expected a warning when required config is missing"
    event, payload = warnings[0]
    assert event == "brain_auth.incomplete_config"
    assert "brain_auth_token" in payload["missing"]


def test_admin_kwarg_uses_same_bearer(tmp_path: Path) -> None:
    """``admin=True`` reuses the data-plane Bearer token (tapps-brain v3.8.0)."""
    settings = _make_settings(tmp_path)

    data_headers = build_brain_headers(settings)
    admin_headers = build_brain_headers(settings, admin=True)

    assert data_headers["Authorization"] == admin_headers["Authorization"]
    assert admin_headers["Authorization"] == f"Bearer {_TOKEN_VALUE}"


def test_x_agent_id_uses_stable_agent_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``X-Agent-Id`` is sourced from ``get_stable_agent_id``."""
    settings = _make_settings(tmp_path)
    expected_agent_id = "patched-agent-42"

    monkeypatch.setattr(
        "tapps_core.brain_auth.get_stable_agent_id",
        lambda _settings: expected_agent_id,
    )

    headers = build_brain_headers(settings)

    assert headers["X-Agent-Id"] == expected_agent_id
