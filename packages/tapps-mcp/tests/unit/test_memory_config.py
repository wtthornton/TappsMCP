"""Tests for memory configuration and observability (Epic 24.5)."""

from __future__ import annotations

import pytest

from tapps_mcp.config.settings import MemoryDecaySettings, MemorySettings, TappsMCPSettings
from tapps_mcp.memory.decay import DecayConfig


class TestMemorySettings:
    def test_defaults(self) -> None:
        """Memory settings have sensible defaults."""
        settings = MemorySettings()
        assert settings.enabled is True
        assert settings.gc_enabled is True
        assert settings.contradiction_check_on_start is True
        assert settings.max_memories == 1500
        assert settings.inject_into_experts is True
        assert settings.enrich_impact_analysis is True
        assert settings.auto_save_quality is True
        assert settings.track_recurring_quick_check is True
        assert settings.auto_supersede_architectural is True

    def test_memory_hooks_defaults_on_root_settings(self) -> None:
        """memory_hooks default to on for POC (auto-recall / auto-capture)."""
        root = TappsMCPSettings()
        assert root.memory_hooks.auto_recall.enabled is True
        assert root.memory_hooks.auto_capture.enabled is True

    def test_decay_defaults(self) -> None:
        """Decay settings have the correct half-lives."""
        decay = MemoryDecaySettings()
        assert decay.architectural_half_life_days == 180
        assert decay.pattern_half_life_days == 60
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
            context_half_life_days=7,
            confidence_floor=0.05,
        )
        config = DecayConfig(
            architectural_half_life_days=decay_settings.architectural_half_life_days,
            pattern_half_life_days=decay_settings.pattern_half_life_days,
            context_half_life_days=decay_settings.context_half_life_days,
            confidence_floor=decay_settings.confidence_floor,
        )
        assert config.architectural_half_life_days == 90
        assert config.pattern_half_life_days == 30
        assert config.context_half_life_days == 7
        assert config.confidence_floor == 0.05

    def test_yaml_config_loading(self, tmp_path: pytest.TempPathFactory) -> None:
        """Memory settings can be loaded from YAML config."""
        from tapps_mcp.config.settings import load_settings

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
