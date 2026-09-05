"""Smoke tests for tapps_mcp.distribution.doctor_context7 (TAP-5606 split)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from tapps_mcp.distribution.doctor_context7 import (
    _env_file_get_value,
    _env_file_sets_key,
    _mcp_configs_set_context7,
    check_consumer_context7_env,
    check_context7_configured_without_key,
    check_context7_live,
    check_mcp_operator_secrets,
)


def test_env_file_get_value_missing_file_returns_none(tmp_path: Path) -> None:
    assert _env_file_get_value(tmp_path / "missing.env", "KEY") is None


def test_env_file_get_value_reads_defined_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_KEY=abc123\n", encoding="utf-8")
    assert _env_file_get_value(env_file, "SOME_KEY") == "abc123"


def test_env_file_sets_key_false_when_missing(tmp_path: Path) -> None:
    assert _env_file_sets_key(tmp_path / "missing.env", "KEY") is False


def test_mcp_configs_set_context7_no_configs_returns_empty(tmp_path: Path) -> None:
    assert _mcp_configs_set_context7(tmp_path) == []


def test_check_context7_live_quick_mode_skips(tmp_path: Path) -> None:
    result = check_context7_live(tmp_path, quick=True)
    assert result.ok is True
    assert "Skipped" in result.message


def test_check_consumer_context7_env_no_configs_passes(tmp_path: Path) -> None:
    os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    result = check_consumer_context7_env(tmp_path)
    assert result.ok is True


def test_check_mcp_operator_secrets_no_configs_passes(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    result = check_mcp_operator_secrets(tmp_path)
    assert result.ok is True


class TestCheckContext7ConfiguredWithoutKey:
    """TAP-6443: doctor must flag Context7-active-but-no-key, which
    ``check_context7_live``'s ``no_key`` branch deliberately does not."""

    def setup_method(self) -> None:
        for key in (
            "TAPPS_MCP_CONTEXT7_API_KEY",
            "CONTEXT7_API_KEY",
            "TAPPS_MCP_DOCS_VIA_BRAIN",
        ):
            os.environ.pop(key, None)

    def teardown_method(self) -> None:
        self.setup_method()

    def test_configured_without_key_fails(self, tmp_path: Path) -> None:
        # Isolated from any real ~/.tapps-operator.env on the dev machine --
        # _operator_secret_available also checks that file and this repo's
        # own operator env has a live Context7 key, which would otherwise
        # make this test pass for the wrong reason.
        with patch(
            "tapps_mcp.distribution.doctor_context7._operator_secret_available",
            return_value=False,
        ):
            (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
            result = check_context7_configured_without_key(tmp_path)
        assert result.ok is False
        assert "no API key is resolvable" in result.message
        assert result.detail
        assert "TAPPS_MCP_CONTEXT7_API_KEY" in result.detail

    def test_configured_with_key_passes(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        os.environ["TAPPS_MCP_CONTEXT7_API_KEY"] = "test-key-123"
        result = check_context7_configured_without_key(tmp_path)
        assert result.ok is True

    def test_docs_via_brain_enabled_skips(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
        result = check_context7_configured_without_key(tmp_path)
        assert result.ok is True
        assert "Skipped" in result.message


def test_check_is_registered_in_the_doctor_run() -> None:
    """TAP-6443b: assert against `_check_specs`, not `_collect_checks` --
    `_collect_checks` only calls `_check_specs` and does not inline its
    display-name constants (see the two pre-existing broken examples in
    test_skill_asset_policy.py / test_agent_to_agent_rule.py; do not repeat
    that pattern here)."""
    from tapps_mcp.distribution.doctor_runner import _check_specs

    assert "Context7 configured without key" in _check_specs.__code__.co_consts
