"""Tests for memory configuration and observability (Epic 24.5)."""

from __future__ import annotations

import pytest  # noqa: TC002 - needed for tmp_path fixture at runtime

from tapps_core.config.settings import (
    MemoryDecaySettings,
    MemorySettings,
    MemoryWriteRules,
    TappsMCPSettings,
)
from tapps_core.memory.decay import DecayConfig


class TestMemorySettings:
    def test_defaults(self) -> None:
        """Memory settings have sensible defaults."""
        settings = MemorySettings()
        assert settings.enabled is True
        assert settings.gc_enabled is True
        assert settings.contradiction_check_on_start is True
        assert settings.max_memories == 1500
        assert settings.inject_into_experts is True

    def test_capture_prompt_default(self) -> None:
        """Memory capture_prompt has Neuronex-style default (Epic 65.3)."""
        settings = MemorySettings()
        assert "Store durable memories" in settings.capture_prompt
        assert "architectural" in settings.capture_prompt
        assert "Skip: raw action logs" in settings.capture_prompt

    def test_write_rules_defaults(self) -> None:
        """Memory write_rules have sensible defaults (Epic 65.3)."""
        settings = MemorySettings()
        rules = settings.write_rules
        assert isinstance(rules, MemoryWriteRules)
        assert "password" in rules.block_sensitive_keywords
        assert "api_key" in rules.block_sensitive_keywords
        assert rules.min_value_length == 10
        assert rules.max_value_length == 4096

    def test_decay_defaults(self) -> None:
        """Decay settings have the correct half-lives."""
        decay = MemoryDecaySettings()
        assert decay.architectural_half_life_days == 180
        assert decay.pattern_half_life_days == 60
        assert decay.procedural_half_life_days == 30  # Epic 65.11
        assert decay.context_half_life_days == 14
        assert decay.confidence_floor == 0.1

    def test_settings_attached_to_root(self) -> None:
        """Memory settings are accessible from TappsMCPSettings."""
        settings = TappsMCPSettings()
        assert hasattr(settings, "memory")
        assert isinstance(settings.memory, MemorySettings)
        assert isinstance(settings.memory.decay, MemoryDecaySettings)

    def test_config_to_decay_config(self) -> None:
        """MemoryDecaySettings can be converted to DecayConfig."""
        decay_settings = MemoryDecaySettings(
            architectural_half_life_days=90,
            pattern_half_life_days=30,
            procedural_half_life_days=21,
            context_half_life_days=7,
            confidence_floor=0.05,
        )
        config = DecayConfig(
            architectural_half_life_days=decay_settings.architectural_half_life_days,
            pattern_half_life_days=decay_settings.pattern_half_life_days,
            procedural_half_life_days=decay_settings.procedural_half_life_days,
            context_half_life_days=decay_settings.context_half_life_days,
            confidence_floor=decay_settings.confidence_floor,
        )
        assert config.architectural_half_life_days == 90
        assert config.pattern_half_life_days == 30
        assert config.procedural_half_life_days == 21
        assert config.context_half_life_days == 7
        assert config.confidence_floor == 0.05

    def test_yaml_config_loading(self, tmp_path: pytest.TempPathFactory) -> None:
        """Memory settings can be loaded from YAML config."""
        from tapps_core.config.settings import load_settings

        yaml_path = tmp_path / ".tapps-mcp.yaml"  # type: ignore[operator]
        yaml_path.write_text(  # type: ignore[union-attr]
            "memory:\n"
            "  enabled: false\n"
            "  gc_enabled: false\n"
            "  max_memories: 100\n"
            "  decay:\n"
            "    architectural_half_life_days: 90\n"
        )

        settings = load_settings(project_root=tmp_path)  # type: ignore[arg-type]
        assert settings.memory.enabled is False
        assert settings.memory.gc_enabled is False
        assert settings.memory.max_memories == 100
        assert settings.memory.decay.architectural_half_life_days == 90

    def test_yaml_capture_prompt_and_write_rules_override(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Memory capture_prompt and write_rules override via .tapps-mcp.yaml (Epic 65.3)."""
        from tapps_core.config.settings import load_settings

        yaml_path = tmp_path / ".tapps-mcp.yaml"  # type: ignore[operator]
        yaml_path.write_text(  # type: ignore[union-attr]
            "memory:\n"
            "  capture_prompt: 'Custom prompt for my project.'\n"
            "  write_rules:\n"
            "    block_sensitive_keywords: ['key', 'credential']\n"
            "    min_value_length: 20\n"
            "    max_value_length: 2048\n"
        )

        settings = load_settings(project_root=tmp_path)  # type: ignore[arg-type]
        assert settings.memory.capture_prompt == "Custom prompt for my project."
        assert settings.memory.write_rules.block_sensitive_keywords == [
            "key",
            "credential",
        ]
        assert settings.memory.write_rules.min_value_length == 20
        assert settings.memory.write_rules.max_value_length == 2048
