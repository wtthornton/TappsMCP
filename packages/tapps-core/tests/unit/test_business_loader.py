"""Tests for business expert auto-loading integration."""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_core.experts.business_loader import (
    BusinessExpertLoadResult,
    load_and_register_business_experts,
)
from tapps_core.experts.registry import ExpertRegistry


def _write_experts_yaml(tmp_path: Path, experts: list[dict[str, object]]) -> None:
    """Helper to write experts.yaml in the expected location."""
    config_dir = tmp_path / ".tapps-mcp"
    config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = config_dir / "experts.yaml"
    yaml_path.write_text(yaml.dump({"experts": experts}), encoding="utf-8")


def _make_expert_dict(
    expert_id: str = "expert-test",
    expert_name: str = "Test Expert",
    primary_domain: str = "test-domain",
) -> dict[str, object]:
    return {
        "expert_id": expert_id,
        "expert_name": expert_name,
        "primary_domain": primary_domain,
    }


class TestLoadAndRegisterBusinessExperts:
    """Tests for load_and_register_business_experts."""

    def test_valid_yaml_registers_experts(self, tmp_path: Path) -> None:
        """Valid YAML loads and registers experts."""
        _write_experts_yaml(tmp_path, [_make_expert_dict()])
        result = load_and_register_business_experts(tmp_path)

        assert result.loaded == 1
        assert result.expert_ids == ["expert-test"]
        assert not result.errors
        assert ExpertRegistry.get_business_experts()

    def test_missing_yaml_returns_empty(self, tmp_path: Path) -> None:
        """Missing experts.yaml returns empty result gracefully."""
        result = load_and_register_business_experts(tmp_path)

        assert result.loaded == 0
        assert not result.errors
        assert not result.expert_ids

    def test_disabled_via_settings_returns_empty(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        """When business_experts_enabled=False, returns empty result."""
        from tapps_core.config import settings as settings_mod

        _write_experts_yaml(tmp_path, [_make_expert_dict()])

        # Patch load_settings to return disabled
        from unittest.mock import patch

        from tapps_core.config.settings import TappsMCPSettings

        mock_settings = TappsMCPSettings(
            project_root=tmp_path, business_experts_enabled=False
        )

        with patch.object(settings_mod, "_cached_settings", mock_settings):
            result = load_and_register_business_experts(tmp_path)

        assert result.loaded == 0
        assert not result.errors

    def test_knowledge_validation_included(self, tmp_path: Path) -> None:
        """Knowledge validation results are included in the load result."""
        _write_experts_yaml(tmp_path, [_make_expert_dict()])
        result = load_and_register_business_experts(tmp_path)

        # No knowledge dir was created, so it should be missing
        assert result.knowledge_status.get("test-domain") == "missing"
        assert any("missing" in w.lower() for w in result.warnings)

    def test_knowledge_valid_when_dir_has_md(self, tmp_path: Path) -> None:
        """Knowledge directory with .md files is reported as valid."""
        _write_experts_yaml(tmp_path, [_make_expert_dict()])

        # Create knowledge directory with an .md file
        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "test-domain"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "overview.md").write_text("# Overview\n")

        result = load_and_register_business_experts(tmp_path)
        assert result.knowledge_status.get("test-domain") == "valid"

    def test_id_collision_error_reported(self, tmp_path: Path) -> None:
        """ID collision with built-in expert is reported as error."""
        # Use a built-in expert ID
        _write_experts_yaml(
            tmp_path,
            [_make_expert_dict(expert_id="expert-security", primary_domain="custom-sec")],
        )
        result = load_and_register_business_experts(tmp_path)

        assert result.loaded == 0
        assert any("collides" in e.lower() for e in result.errors)

    def test_malformed_yaml_error_reported(self, tmp_path: Path) -> None:
        """Malformed YAML is reported as error."""
        config_dir = tmp_path / ".tapps-mcp"
        config_dir.mkdir(parents=True)
        (config_dir / "experts.yaml").write_text(":::bad yaml:::", encoding="utf-8")

        result = load_and_register_business_experts(tmp_path)
        assert result.loaded == 0
        assert result.errors

    def test_multiple_experts(self, tmp_path: Path) -> None:
        """Multiple experts are loaded and registered."""
        experts = [
            _make_expert_dict("expert-one", "One", "domain-one"),
            _make_expert_dict("expert-two", "Two", "domain-two"),
        ]
        _write_experts_yaml(tmp_path, experts)

        result = load_and_register_business_experts(tmp_path)
        assert result.loaded == 2
        assert set(result.expert_ids) == {"expert-one", "expert-two"}
        assert ExpertRegistry.is_business_domain("domain-one")
        assert ExpertRegistry.is_business_domain("domain-two")
