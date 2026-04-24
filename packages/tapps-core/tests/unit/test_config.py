"""Tests for config.settings."""

from __future__ import annotations

import pytest

from tapps_core.config.settings import (
    PRESETS,
    TappsMCPSettings,
    load_settings,
)


class TestTappsMCPSettings:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Isolate from runner env so default is None when key not set
        monkeypatch.delenv("TAPPS_MCP_CONTEXT7_API_KEY", raising=False)
        settings = TappsMCPSettings()
        assert settings.quality_preset == "standard"
        assert settings.log_level == "INFO"
        assert settings.log_json is False
        assert settings.tool_timeout == 30
        assert settings.context7_api_key is None
        assert settings.expert_auto_fallback is True
        assert settings.expert_fallback_max_chars == 1200

    def test_linear_cache_ttl_defaults(self) -> None:
        settings = TappsMCPSettings()
        assert settings.linear_cache_ttl_open_seconds == 300
        assert settings.linear_cache_ttl_closed_seconds == 3600

    def test_linear_cache_ttl_rejects_negative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_LINEAR_CACHE_TTL_OPEN_SECONDS", "-1")
        with pytest.raises(ValueError):
            TappsMCPSettings()

    def test_scoring_weights_default(self) -> None:
        settings = TappsMCPSettings()
        w = settings.scoring_weights
        total = (
            w.complexity
            + w.security
            + w.maintainability
            + w.test_coverage
            + w.performance
            + w.structure
            + w.devex
        )
        assert abs(total - 1.0) < 0.01


class TestPresets:
    def test_standard_preset(self) -> None:
        assert PRESETS["standard"]["overall_min"] == 70.0

    def test_strict_preset(self) -> None:
        assert PRESETS["strict"]["overall_min"] == 80.0

    def test_framework_preset(self) -> None:
        assert PRESETS["framework"]["overall_min"] == 75.0


class TestLoadSettings:
    def test_load_with_no_yaml(self, tmp_path: pytest.TempPathFactory) -> None:
        settings = load_settings(project_root=tmp_path)  # type: ignore[arg-type]
        assert settings.project_root == tmp_path

    def test_load_with_yaml(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / ".tapps-mcp.yaml"  # type: ignore[operator]
        yaml_file.write_text("quality_preset: strict\nlog_level: DEBUG\n")
        settings = load_settings(project_root=tmp_path)  # type: ignore[arg-type]
        assert settings.quality_preset == "strict"
        assert settings.log_level == "DEBUG"

    def test_load_with_invalid_yaml(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / ".tapps-mcp.yaml"  # type: ignore[operator]
        yaml_file.write_text("not: valid: yaml: [")
        # Should fallback to defaults on parse error
        settings = load_settings(project_root=tmp_path)  # type: ignore[arg-type]
        assert settings.quality_preset == "standard"
