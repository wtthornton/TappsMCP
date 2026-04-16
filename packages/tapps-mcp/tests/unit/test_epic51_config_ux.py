"""Tests for Epic 51: Configuration UX & TECH_STACK Preservation."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline


class TestTechStackPreservation:
    """Story 51.1: TECH_STACK.md overwrite protection."""

    _common = {
        "create_handoff": False,
        "create_runlog": False,
        "create_agents_md": False,
        "verify_server": False,
        "warm_cache_from_tech_stack": False,
        "warm_expert_rag_from_tech_stack": False,
    }

    def test_tech_stack_preserved_by_default(self, tmp_path):
        """Existing TECH_STACK.md with custom content is preserved by default."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\ndependencies = []\n")
        custom_content = "# My Custom Tech Stack\n\nHand-curated content.\n"
        (tmp_path / "TECH_STACK.md").write_text(custom_content)

        result = bootstrap_pipeline(tmp_path, **self._common)

        assert result["tech_stack_md"]["action"] == "preserved"
        assert (tmp_path / "TECH_STACK.md").read_text() == custom_content
        assert "TECH_STACK.md" not in result["created"]

    def test_tech_stack_overwrite_when_explicit(self, tmp_path):
        """overwrite_tech_stack_md=True overwrites existing file."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\ndependencies = []\n")
        (tmp_path / "TECH_STACK.md").write_text("# Old content\n")

        result = bootstrap_pipeline(tmp_path, **self._common, overwrite_tech_stack_md=True)

        assert result["tech_stack_md"]["action"] in ("created", "updated")
        content = (tmp_path / "TECH_STACK.md").read_text()
        assert "# Tech Stack" in content
        assert "Old content" not in content

    def test_tech_stack_created_when_missing(self, tmp_path):
        """When no TECH_STACK.md exists, it is created normally."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\ndependencies = []\n")

        result = bootstrap_pipeline(tmp_path, **self._common)

        assert result["tech_stack_md"]["action"] in ("created", "updated")
        assert (tmp_path / "TECH_STACK.md").exists()
        content = (tmp_path / "TECH_STACK.md").read_text()
        assert "# Tech Stack" in content

    def test_tech_stack_skipped_when_disabled(self, tmp_path):
        """create_tech_stack_md=False skips entirely."""
        result = bootstrap_pipeline(tmp_path, **self._common, create_tech_stack_md=False)
        assert result["tech_stack_md"]["action"] == "skipped"

    def test_bootstrap_config_has_overwrite_field(self):
        """BootstrapConfig defaults overwrite_tech_stack_md to False."""
        cfg = BootstrapConfig()
        assert cfg.overwrite_tech_stack_md is False

        cfg_explicit = BootstrapConfig(overwrite_tech_stack_md=True)
        assert cfg_explicit.overwrite_tech_stack_md is True

    def test_bootstrap_config_passed_through(self, tmp_path):
        """Config object with overwrite_tech_stack_md=True works."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\ndependencies = []\n")
        (tmp_path / "TECH_STACK.md").write_text("# Custom\n")

        cfg = BootstrapConfig(
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
            overwrite_tech_stack_md=True,
        )
        result = bootstrap_pipeline(tmp_path, config=cfg)

        assert result["tech_stack_md"]["action"] in ("created", "updated")


class TestShowConfigCli:
    """Story 51.2: show-config CLI command."""

    def test_show_config_outputs_yaml(self, tmp_path):
        """show-config prints YAML to stdout."""
        runner = CliRunner()
        result = runner.invoke(main, ["show-config", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "project_root:" in result.output
        assert "quality_preset:" in result.output
        assert "scoring_weights:" in result.output

    def test_show_config_redacts_api_key(self, tmp_path):
        """API keys should be redacted in output."""
        runner = CliRunner()
        with patch.dict("os.environ", {"TAPPS_MCP_CONTEXT7_API_KEY": "secret-key-123"}):
            result = runner.invoke(main, ["show-config", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "secret-key-123" not in result.output

    def test_show_config_includes_nested_settings(self, tmp_path):
        """Nested models like memory and adaptive should appear."""
        runner = CliRunner()
        result = runner.invoke(main, ["show-config", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "memory:" in result.output
        assert "adaptive:" in result.output
        assert "scoring_weights:" in result.output


class TestInitCliOverwriteTechStack:
    """Story 51.1: CLI --overwrite-tech-stack flag."""

    def test_init_has_overwrite_tech_stack_flag(self):
        """The init command accepts --overwrite-tech-stack."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "--overwrite-tech-stack" in result.output


class TestInitWarnings:
    """Story 51.3: Cache warming skip warnings in init result."""

    _common = {
        "create_handoff": False,
        "create_runlog": False,
        "create_agents_md": False,
        "verify_server": False,
        "warm_expert_rag_from_tech_stack": False,
    }

    def test_init_warnings_on_missing_api_key(self, tmp_path):
        """When CONTEXT7_API_KEY is missing, warnings list is populated."""
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'foo'\ndependencies = ['requests']\n"
        )
        result = bootstrap_pipeline(tmp_path, **self._common, warm_cache_from_tech_stack=True)

        assert "warnings" in result
        assert isinstance(result["warnings"], list)
        # Cache warming should be skipped and produce a warning
        cw = result.get("cache_warming", {})
        if cw.get("skipped") == "no_api_key":
            assert len(result["warnings"]) >= 1
            assert any("CONTEXT7_API_KEY" in w for w in result["warnings"])
            assert "warning" in cw

    def test_init_warnings_empty_when_no_issues(self, tmp_path):
        """When cache warming is disabled, warnings list is empty."""
        result = bootstrap_pipeline(
            tmp_path,
            **self._common,
            create_tech_stack_md=False,
            warm_cache_from_tech_stack=False,
        )
        assert "warnings" in result
        assert isinstance(result["warnings"], list)
        assert len(result["warnings"]) == 0

    def test_init_result_always_has_warnings_key(self, tmp_path):
        """The result dict always includes a 'warnings' key."""
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    def test_cache_warming_warning_has_guidance(self, tmp_path):
        """The warning message includes actionable guidance."""
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'foo'\ndependencies = ['requests']\n"
        )
        result = bootstrap_pipeline(tmp_path, **self._common, warm_cache_from_tech_stack=True)
        cw = result.get("cache_warming", {})
        if cw.get("skipped") == "no_api_key":
            warning_text = cw.get("warning", "")
            assert "CONTEXT7_API_KEY" in warning_text
            assert "env config" in warning_text.lower() or "MCP" in warning_text
