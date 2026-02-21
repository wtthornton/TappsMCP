"""Tests for tapps_mcp.config.settings."""

from __future__ import annotations

import os
from unittest import mock

import pytest


class TestScoringWeights:
    """Validate ScoringWeights defaults and constraints."""

    def test_defaults_sum_to_one(self) -> None:
        from tapps_mcp.config.settings import ScoringWeights

        w = ScoringWeights()
        total = w.complexity + w.security + w.maintainability + w.test_coverage + w.performance + w.structure + w.devex
        assert abs(total - 1.0) < 0.01

    def test_weight_range(self) -> None:
        from tapps_mcp.config.settings import ScoringWeights

        w = ScoringWeights()
        for field_name in ScoringWeights.model_fields:
            val = getattr(w, field_name)
            assert 0.0 <= val <= 1.0, f"{field_name} out of range: {val}"

    def test_env_override(self) -> None:
        from tapps_mcp.config.settings import ScoringWeights

        with mock.patch.dict(os.environ, {"TAPPS_MCP_WEIGHT_SECURITY": "0.50"}):
            w = ScoringWeights()
            assert w.security == 0.50


class TestQualityPreset:
    """Validate QualityPreset defaults."""

    def test_standard_defaults(self) -> None:
        from tapps_mcp.config.settings import QualityPreset

        p = QualityPreset()
        assert p.overall_min == 70.0
        assert p.security_min == 0.0


class TestPresets:
    """Validate built-in preset definitions."""

    def test_known_presets(self) -> None:
        from tapps_mcp.config.settings import PRESETS

        assert "standard" in PRESETS
        assert "strict" in PRESETS
        assert "framework" in PRESETS

    def test_strict_is_higher(self) -> None:
        from tapps_mcp.config.settings import PRESETS

        assert PRESETS["strict"]["overall_min"] > PRESETS["standard"]["overall_min"]


class TestTappsMCPSettings:
    """Validate root settings model."""

    def test_load_settings_returns_instance(self) -> None:
        from tapps_mcp.config.settings import TappsMCPSettings, load_settings

        s = load_settings()
        assert isinstance(s, TappsMCPSettings)

    def test_scoring_weights_attached(self) -> None:
        from tapps_mcp.config.settings import ScoringWeights, load_settings

        s = load_settings()
        assert isinstance(s.scoring_weights, ScoringWeights)


class TestAdaptiveSettings:
    """Validate adaptive learning settings."""

    def test_defaults(self) -> None:
        from tapps_mcp.config.settings import AdaptiveSettings

        a = AdaptiveSettings()
        assert a.enabled is False
        assert 0.0 <= a.learning_rate <= 1.0
        assert a.min_outcomes >= 1
