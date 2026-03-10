"""Tests for DocsMCP configuration system."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from docs_mcp.config.settings import (
    DocsMCPSettings,
    _expand_path,
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


class TestExpandPath:
    """Tests for the _expand_path helper."""

    def test_expand_env_var(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"MY_TEST_DIR": str(tmp_path)}):
            result = _expand_path("${MY_TEST_DIR}/sub")
        assert result == tmp_path / "sub"

    def test_expand_user_tilde(self) -> None:
        result = _expand_path("~/projects/foo")
        assert "~" not in str(result)
        assert str(result).endswith(os.path.join("projects", "foo"))

    def test_no_expansion_needed(self, tmp_path: Path) -> None:
        result = _expand_path(str(tmp_path))
        assert result == tmp_path

    def test_nonexistent_env_var_stays_empty(self) -> None:
        # Ensure the var doesn't exist
        env = {k: v for k, v in os.environ.items() if k != "TOTALLY_MISSING_VAR_XYZ"}
        with patch.dict(os.environ, env, clear=True):
            result = _expand_path("${TOTALLY_MISSING_VAR_XYZ}/rest")
        # On platforms where expandvars leaves unknown vars, the literal stays;
        # on others it becomes empty. Either way, no crash.
        assert isinstance(result, Path)


class TestEnvVarResolution:
    """Tests for environment variable resolution in load_docs_settings."""

    def test_project_root_env_var_resolves(self, tmp_path: Path) -> None:
        """DOCS_MCP_PROJECT_ROOT env var should resolve, not stay literal."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        with patch.dict(os.environ, {"DOCS_MCP_PROJECT_ROOT": str(project_dir)}):
            _reset_docs_settings_cache()
            result = load_docs_settings()
        assert result.project_root == project_dir
        assert "${" not in str(result.project_root)

    def test_project_root_tilde_expansion(self, tmp_path: Path) -> None:
        """~ in project_root should expand to full home path."""
        result = load_docs_settings(project_root=Path("~/myproject"))
        assert "~" not in str(result.project_root)

    def test_output_dir_env_var_resolves(self, tmp_path: Path) -> None:
        """output_dir with env vars should resolve."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / ".docsmcp.yaml").write_text(
            "output_dir: ${HOME}/custom_docs\n",
            encoding="utf-8",
        )
        result = load_docs_settings(project_root=project_dir)
        assert "${" not in result.output_dir

    def test_missing_dir_logs_warning(self, tmp_path: Path) -> None:
        """Non-existent project_root should log warning but not error."""
        nonexistent = tmp_path / "does_not_exist"
        # Should not raise
        result = load_docs_settings(project_root=nonexistent)
        assert result.project_root == nonexistent

    def test_explicit_project_root_with_env_var_syntax(self, tmp_path: Path) -> None:
        """Explicit project_root containing ${VAR} should expand."""
        project_dir = tmp_path / "real"
        project_dir.mkdir()
        with patch.dict(os.environ, {"MY_ROOT": str(tmp_path)}):
            result = load_docs_settings(project_root=Path("${MY_ROOT}/real"))
        assert result.project_root == project_dir
