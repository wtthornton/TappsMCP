"""Tests for LLM engagement level configuration.

Epic 18: LLM Engagement Level Configuration.
"""

from __future__ import annotations

import pytest


class TestEngagementLevelSettings:
    """Tests for engagement level in TappsMCPSettings (Story 18.1)."""

    def test_default_is_medium(self, tmp_path):
        from tapps_mcp.config.settings import load_settings

        settings = load_settings(project_root=tmp_path)
        assert settings.llm_engagement_level == "medium"

    def test_loads_from_yaml(self, tmp_path):
        from tapps_mcp.config.settings import load_settings

        config = tmp_path / ".tapps-mcp.yaml"
        config.write_text("llm_engagement_level: high\n", encoding="utf-8")
        settings = load_settings(project_root=tmp_path)
        assert settings.llm_engagement_level == "high"

    def test_loads_low_from_yaml(self, tmp_path):
        from tapps_mcp.config.settings import load_settings

        config = tmp_path / ".tapps-mcp.yaml"
        config.write_text("llm_engagement_level: low\n", encoding="utf-8")
        settings = load_settings(project_root=tmp_path)
        assert settings.llm_engagement_level == "low"

    def test_invalid_value_raises_error(self, tmp_path):
        from pydantic import ValidationError

        from tapps_mcp.config.settings import TappsMCPSettings

        with pytest.raises(ValidationError):
            TappsMCPSettings(
                project_root=tmp_path,
                llm_engagement_level="extreme",  # type: ignore[arg-type]
            )

    def test_existing_yaml_without_key_still_loads(self, tmp_path):
        from tapps_mcp.config.settings import load_settings

        config = tmp_path / ".tapps-mcp.yaml"
        config.write_text("quality_preset: strict\n", encoding="utf-8")
        settings = load_settings(project_root=tmp_path)
        assert settings.llm_engagement_level == "medium"
        assert settings.quality_preset == "strict"

    def test_accepts_all_valid_levels(self, tmp_path):
        from tapps_mcp.config.settings import TappsMCPSettings

        for level in ("high", "medium", "low"):
            settings = TappsMCPSettings(
                project_root=tmp_path,
                llm_engagement_level=level,  # type: ignore[arg-type]
            )
            assert settings.llm_engagement_level == level

    def test_loads_from_env_var(self, tmp_path, monkeypatch):
        from tapps_mcp.config.settings import load_settings

        monkeypatch.setenv("TAPPS_MCP_LLM_ENGAGEMENT_LEVEL", "high")
        settings = load_settings(project_root=tmp_path)
        assert settings.llm_engagement_level == "high"
