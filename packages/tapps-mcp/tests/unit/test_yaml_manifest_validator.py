"""Tests for generic YAML manifest validation."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.validators.yaml_manifest import validate_yaml_manifest


class TestYamlManifestValidator:
    def test_invalid_yaml_fails(self, tmp_path: Path) -> None:
        result = validate_yaml_manifest(
            "brands/acme/brand.yaml",
            "key: [unclosed",
            project_root=tmp_path,
        )
        assert result.valid is False
        assert result.config_type == "yaml_manifest"

    def test_missing_required_key_fails(self, tmp_path: Path) -> None:
        result = validate_yaml_manifest(
            "brands/acme/brand.yaml",
            "name: acme\n",
            required_keys=["version"],
            project_root=tmp_path,
        )
        assert result.valid is False
        assert any("version" in f.message for f in result.findings)

    def test_valid_manifest_passes(self, tmp_path: Path) -> None:
        result = validate_yaml_manifest(
            "templates/report/template.yaml",
            "id: annual-report\nname: Annual Report\n",
            required_keys=["id"],
            project_root=tmp_path,
        )
        assert result.valid is True

    def test_outside_glob_syntax_only_pass(self, tmp_path: Path) -> None:
        result = validate_yaml_manifest(
            "README.yaml",
            "not: a manifest\n",
            path_globs=["brands/**/*.yaml"],
            project_root=tmp_path,
        )
        assert result.valid is True
        assert result.suggestions
