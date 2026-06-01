"""Tests for docs_mcp.integrations.linear_gateway (TAP-2009).

Covers:
- check_validate_sentinel: absent, fresh, stale, malformed
- validate_missing_envelope: shape and fields
- gate_linear_save: pass, fire, bypass env
- docs_save_linear_issue handler: gate pass, gate fire, config error
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.integrations.linear_gateway import (
    _SENTINEL_MAX_AGE_S,
    _SENTINEL_REL,
    check_validate_sentinel,
    gate_linear_save,
    validate_missing_envelope,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A temporary project directory (no sentinel by default)."""
    return tmp_path


@pytest.fixture
def fresh_sentinel(project_dir: Path) -> Path:
    """Write a fresh sentinel and return the project dir."""
    sentinel = project_dir / _SENTINEL_REL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(str(time.time()), encoding="utf-8")
    return project_dir


@pytest.fixture
def stale_sentinel(project_dir: Path) -> Path:
    """Write a stale sentinel (age > TTL) and return the project dir."""
    sentinel = project_dir / _SENTINEL_REL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    stale_epoch = time.time() - _SENTINEL_MAX_AGE_S - 60
    sentinel.write_text(str(stale_epoch), encoding="utf-8")
    return project_dir


# ---------------------------------------------------------------------------
# check_validate_sentinel
# ---------------------------------------------------------------------------


class TestCheckValidateSentinel:
    def test_no_sentinel_file_returns_false(self, project_dir: Path) -> None:
        assert check_validate_sentinel(project_dir) is False

    def test_fresh_sentinel_returns_true(self, fresh_sentinel: Path) -> None:
        assert check_validate_sentinel(fresh_sentinel) is True

    def test_stale_sentinel_returns_false(self, stale_sentinel: Path) -> None:
        assert check_validate_sentinel(stale_sentinel) is False

    def test_malformed_sentinel_content_returns_false(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("not-a-number", encoding="utf-8")
        assert check_validate_sentinel(project_dir) is False

    def test_empty_sentinel_content_returns_false(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("", encoding="utf-8")
        assert check_validate_sentinel(project_dir) is False

    def test_sentinel_exactly_at_ttl_boundary_returns_false(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        # Exactly at the TTL boundary — should be outside the window
        sentinel.write_text(str(time.time() - _SENTINEL_MAX_AGE_S - 1), encoding="utf-8")
        assert check_validate_sentinel(project_dir) is False

    def test_sentinel_just_inside_ttl_returns_true(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(str(time.time() - _SENTINEL_MAX_AGE_S + 10), encoding="utf-8")
        assert check_validate_sentinel(project_dir) is True


# ---------------------------------------------------------------------------
# validate_missing_envelope
# ---------------------------------------------------------------------------


class TestValidateMissingEnvelope:
    def test_returns_ok_false(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["ok"] is False

    def test_code_is_validate_missing(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["code"] == "validate_missing"

    def test_gate_field(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["gate"] == "linear_write_validation"

    def test_use_field_names_correct_tool(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["use"] == "docs_validate_linear_issue"

    def test_args_contains_title_and_description(self) -> None:
        env = validate_missing_envelope("My issue", "desc")
        assert env["args"]["title"] == "My issue"
        assert env["args"]["description"] == "desc"

    def test_bypass_env_present(self) -> None:
        env = validate_missing_envelope("t", "d")
        assert env["bypass_env"] == "TAPPS_LINEAR_SKIP_VALIDATE"

    def test_logged_to_present(self) -> None:
        env = validate_missing_envelope("t", "d")
        assert ".bypass-log.jsonl" in env["logged_to"]

    def test_hint_is_string(self) -> None:
        env = validate_missing_envelope("t", "d")
        assert isinstance(env["hint"], str)
        assert len(env["hint"]) > 0


# ---------------------------------------------------------------------------
# gate_linear_save
# ---------------------------------------------------------------------------


class TestGateLinearSave:
    def test_returns_none_when_fresh_sentinel(self, fresh_sentinel: Path) -> None:
        result = gate_linear_save(fresh_sentinel, "title", "description")
        assert result is None

    def test_returns_envelope_when_no_sentinel(self, project_dir: Path) -> None:
        result = gate_linear_save(project_dir, "My issue", "desc")
        assert result is not None
        assert result["ok"] is False
        assert result["code"] == "validate_missing"

    def test_returns_envelope_when_stale_sentinel(self, stale_sentinel: Path) -> None:
        result = gate_linear_save(stale_sentinel, "title", "desc")
        assert result is not None
        assert result["code"] == "validate_missing"

    def test_bypass_env_skips_check(self, project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.setenv("TAPPS_LINEAR_SKIP_VALIDATE", "1")
        # Even with no sentinel, bypass returns None (gate passes)
        result = gate_linear_save(project_dir, "title", "desc")
        assert result is None

    def test_bypass_env_not_set_enforces_gate(self, project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.delenv("TAPPS_LINEAR_SKIP_VALIDATE", raising=False)
        result = gate_linear_save(project_dir, "title", "desc")
        assert result is not None
        assert result["ok"] is False

    def test_envelope_args_carry_input_title(self, project_dir: Path) -> None:
        result = gate_linear_save(project_dir, "Specific title", "body")
        assert result is not None
        assert result["args"]["title"] == "Specific title"


# ---------------------------------------------------------------------------
# docs_save_linear_issue handler (integration-style, no real MCP stack)
# ---------------------------------------------------------------------------


class TestDocsSaveLinearIssueHandler:
    @pytest.mark.asyncio
    async def test_gate_passes_when_fresh_sentinel(self, fresh_sentinel: Path) -> None:
        """Gate passes → returns ok: true."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = fresh_sentinel

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("My issue", "desc", str(fresh_sentinel))

        assert result["success"] is True
        assert result["data"]["ok"] is True

    @pytest.mark.asyncio
    async def test_gate_fires_when_no_sentinel(self, project_dir: Path) -> None:
        """Gate fires → returns validate_missing envelope in data."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("My issue", "desc", str(project_dir))

        assert result["success"] is True  # tool ran OK at transport level
        assert result["data"]["ok"] is False
        assert result["data"]["code"] == "validate_missing"

    @pytest.mark.asyncio
    async def test_next_steps_on_gate_fire(self, project_dir: Path) -> None:
        """Gate fire response includes next_steps with the validator call."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("My issue", "desc", str(project_dir))

        next_steps = result["data"].get("next_steps", [])
        assert any("docs_validate_linear_issue" in step for step in next_steps)

    @pytest.mark.asyncio
    async def test_next_steps_on_gate_pass(self, fresh_sentinel: Path) -> None:
        """Gate pass response includes next_steps pointing to save_issue."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = fresh_sentinel

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("My issue", "desc", str(fresh_sentinel))

        next_steps = result["data"].get("next_steps", [])
        assert any("save_issue" in step for step in next_steps)

    @pytest.mark.asyncio
    async def test_config_error_returns_error_response(self) -> None:
        """Settings failure returns an error response (not a crash)."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            side_effect=RuntimeError("config broken"),
        ):
            result = await docs_save_linear_issue("title", "desc")

        assert result["success"] is False
        assert result["error"]["code"] == "CONFIG_ERROR"

    @pytest.mark.asyncio
    async def test_bypass_env_allows_save_without_sentinel(
        self, project_dir: Path, monkeypatch: Any
    ) -> None:
        """TAPPS_LINEAR_SKIP_VALIDATE bypasses the gate check."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        monkeypatch.setenv("TAPPS_LINEAR_SKIP_VALIDATE", "1")

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("title", "desc", str(project_dir))

        assert result["data"]["ok"] is True
