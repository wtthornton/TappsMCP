"""Tests for tapps_core.config.settings."""

from __future__ import annotations

import os
from unittest import mock


class TestScoringWeights:
    """Validate ScoringWeights defaults and constraints."""

    def test_defaults_sum_to_one(self) -> None:
        from tapps_core.config.settings import ScoringWeights

        w = ScoringWeights()
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

    def test_weight_range(self) -> None:
        from tapps_core.config.settings import ScoringWeights

        w = ScoringWeights()
        for field_name in ScoringWeights.model_fields:
            val = getattr(w, field_name)
            assert 0.0 <= val <= 1.0, f"{field_name} out of range: {val}"

    def test_env_override(self) -> None:
        from tapps_core.config.settings import ScoringWeights

        with mock.patch.dict(os.environ, {"TAPPS_MCP_WEIGHT_SECURITY": "0.50"}):
            w = ScoringWeights()
            assert w.security == 0.50


class TestQualityPreset:
    """Validate QualityPreset defaults."""

    def test_standard_defaults(self) -> None:
        from tapps_core.config.settings import QualityPreset

        p = QualityPreset()
        assert p.overall_min == 70.0
        assert p.security_min == 0.0


class TestPresets:
    """Validate built-in preset definitions."""

    def test_known_presets(self) -> None:
        from tapps_core.config.settings import PRESETS

        assert "standard" in PRESETS
        assert "strict" in PRESETS
        assert "framework" in PRESETS

    def test_strict_is_higher(self) -> None:
        from tapps_core.config.settings import PRESETS

        assert PRESETS["strict"]["overall_min"] > PRESETS["standard"]["overall_min"]


class TestTappsMCPSettings:
    """Validate root settings model."""

    def test_load_settings_returns_instance(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings, load_settings

        s = load_settings()
        assert isinstance(s, TappsMCPSettings)

    def test_scoring_weights_attached(self) -> None:
        from tapps_core.config.settings import ScoringWeights, load_settings

        s = load_settings()
        assert isinstance(s.scoring_weights, ScoringWeights)


class TestAdaptiveSettings:
    """Validate adaptive learning settings."""

    def test_defaults(self) -> None:
        from tapps_core.config.settings import AdaptiveSettings

        a = AdaptiveSettings()
        assert a.enabled is False
        assert 0.0 <= a.learning_rate <= 1.0
        assert a.min_outcomes >= 1


class TestToolCurationSettings:
    """Epic 79.1: enabled_tools, disabled_tools, tool_preset."""

    def test_defaults_all_tools(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings()
        assert s.enabled_tools is None
        assert s.disabled_tools == []
        assert s.tool_preset is None

    def test_enabled_tools_from_list(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(enabled_tools=["tapps_session_start", "tapps_quick_check"])
        assert s.enabled_tools == ["tapps_session_start", "tapps_quick_check"]

    def test_enabled_tools_from_comma_separated_string(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(enabled_tools="tapps_session_start, tapps_quick_check")
        assert s.enabled_tools == ["tapps_session_start", "tapps_quick_check"]

    def test_enabled_tools_empty_string_becomes_none(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(enabled_tools="")
        assert s.enabled_tools is None

    def test_disabled_tools_from_list(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(disabled_tools=["tapps_doctor", "tapps_dashboard"])
        assert s.disabled_tools == ["tapps_doctor", "tapps_dashboard"]

    def test_disabled_tools_from_comma_separated_string(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(disabled_tools="tapps_doctor, tapps_dashboard")
        assert s.disabled_tools == ["tapps_doctor", "tapps_dashboard"]

    def test_tool_preset_values(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        for preset in ("full", "core", "pipeline", "reviewer", "planner", "frontend", "developer"):
            s = TappsMCPSettings(tool_preset=preset)
            assert s.tool_preset == preset

    def test_tool_preset_env(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        with mock.patch.dict(os.environ, {"TAPPS_MCP_TOOL_PRESET": "core"}):
            s = TappsMCPSettings()
            assert s.tool_preset == "core"

    def test_enabled_tools_env_comma_separated(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        with mock.patch.dict(
            os.environ, {"TAPPS_MCP_ENABLED_TOOLS": "tapps_session_start,tapps_quick_check"}
        ):
            s = TappsMCPSettings()
            assert s.enabled_tools == ["tapps_session_start", "tapps_quick_check"]


class TestMemoryProjectIdAutoDerive:
    """TAP-1257: brain_project_id and project_id auto-derive from each other."""

    def test_brain_project_id_copied_from_project_id_when_empty(self) -> None:
        from tapps_core.config.settings import MemorySettings

        m = MemorySettings(project_id="my-tenant", brain_project_id="")
        assert m.project_id == "my-tenant"
        assert m.brain_project_id == "my-tenant"

    def test_project_id_copied_from_brain_project_id_when_empty(self) -> None:
        from tapps_core.config.settings import MemorySettings

        m = MemorySettings(project_id="", brain_project_id="my-tenant")
        assert m.project_id == "my-tenant"
        assert m.brain_project_id == "my-tenant"

    def test_both_empty_stays_empty(self) -> None:
        from tapps_core.config.settings import MemorySettings

        m = MemorySettings()
        assert m.project_id == ""
        assert m.brain_project_id == ""

    def test_disagreement_prefers_brain_project_id(self) -> None:
        """When both are set and differ, brain_project_id wins (more-specific name)."""
        from tapps_core.config.settings import MemorySettings

        m = MemorySettings(project_id="legacy", brain_project_id="canonical")
        assert m.brain_project_id == "canonical"
        assert m.project_id == "legacy"

    def test_matching_values_no_op(self) -> None:
        from tapps_core.config.settings import MemorySettings

        m = MemorySettings(project_id="same", brain_project_id="same")
        assert m.brain_project_id == "same"
        assert m.project_id == "same"
