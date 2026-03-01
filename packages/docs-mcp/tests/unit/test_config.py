"""Tests for DocsMCP configuration system."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.config.settings import (
    DocsMCPSettings,
    _reset_docs_settings_cache,
    load_docs_settings,
)


class TestDocsMCPSettings:
    def test_default_settings(self) -> None:
        settings = DocsMCPSettings()
        assert isinstance(settings, DocsMCPSettings)

    def test_output_dir_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.output_dir == "docs"

    def test_default_style_values(self) -> None:
        settings = DocsMCPSettings()
        assert settings.default_style == "standard"

    def test_default_format(self) -> None:
        settings = DocsMCPSettings()
        assert settings.default_format == "markdown"

    def test_include_toc_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.include_toc is True

    def test_include_badges_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.include_badges is True

    def test_changelog_format_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.changelog_format == "keep-a-changelog"

    def test_adr_format_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.adr_format == "madr"

    def test_diagram_format_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.diagram_format == "mermaid"

    def test_git_log_limit_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.git_log_limit == 500

    def test_log_level_default(self) -> None:
        settings = DocsMCPSettings()
        assert settings.log_level == "INFO"


class TestLoadDocsSettings:
    def test_load_docs_settings_returns_settings(self) -> None:
        result = load_docs_settings()
        assert isinstance(result, DocsMCPSettings)

    def test_settings_cache_reset(self) -> None:
        s1 = load_docs_settings()
        _reset_docs_settings_cache()
        s2 = load_docs_settings()
        # Both should be valid settings objects
        assert isinstance(s1, DocsMCPSettings)
        assert isinstance(s2, DocsMCPSettings)

    def test_load_with_explicit_project_root(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        result = load_docs_settings(project_root=tmp_path)
        assert result.project_root == tmp_path

    def test_yaml_config_loading(self, tmp_path: Path) -> None:
        (tmp_path / ".docsmcp.yaml").write_text(
            "output_dir: custom_docs\ndefault_style: minimal\n",
            encoding="utf-8",
        )
        result = load_docs_settings(project_root=tmp_path)
        assert result.output_dir == "custom_docs"
        assert result.default_style == "minimal"

    def test_settings_merge_with_yaml(self, tmp_path: Path) -> None:
        (tmp_path / ".docsmcp.yaml").write_text(
            "include_toc: false\ndiagram_format: plantuml\n",
            encoding="utf-8",
        )
        result = load_docs_settings(project_root=tmp_path)
        assert result.include_toc is False
        assert result.diagram_format == "plantuml"
        # Defaults should still be present for unset values
        assert result.default_format == "markdown"

    def test_missing_yaml_uses_defaults(self, tmp_path: Path) -> None:
        # No .docsmcp.yaml in tmp_path
        result = load_docs_settings(project_root=tmp_path)
        assert result.output_dir == "docs"
        assert result.default_style == "standard"

    def test_invalid_yaml_uses_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".docsmcp.yaml").write_text(
            "not valid: [yaml: {broken",
            encoding="utf-8",
        )
        result = load_docs_settings(project_root=tmp_path)
        assert result.output_dir == "docs"
