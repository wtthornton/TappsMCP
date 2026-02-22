"""Tests for CI/Headless Documentation generation (Story 12.16).

Verifies that generate_ci_workflow creates a valid GitHub Actions
workflow YAML and that the CLAUDE.md CI section is correct.
"""

from __future__ import annotations

import yaml

from tapps_mcp.pipeline.platform_generators import (
    generate_ci_workflow,
    get_ci_claude_md_section,
)


class TestWorkflowCreation:
    """Tests for workflow file creation."""

    def test_creates_file(self, tmp_path):
        generate_ci_workflow(tmp_path)
        target = tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        assert target.exists()

    def test_creates_workflows_dir(self, tmp_path):
        generate_ci_workflow(tmp_path)
        assert (tmp_path / ".github" / "workflows").is_dir()

    def test_result_dict(self, tmp_path):
        result = generate_ci_workflow(tmp_path)
        assert result["action"] == "created"
        assert "tapps-quality.yml" in result["file"]


class TestWorkflowContent:
    """Tests for workflow YAML content."""

    def test_valid_yaml(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        # Strip the leading comment lines that start with #
        parsed = yaml.safe_load(content)
        assert parsed is not None

    def test_has_jobs_key(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        parsed = yaml.safe_load(content)
        assert "jobs" in parsed

    def test_has_name(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        parsed = yaml.safe_load(content)
        assert "name" in parsed

    def test_references_tapps_mcp(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        assert "tapps-mcp" in content

    def test_has_project_root_env(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        assert "TAPPS_MCP_PROJECT_ROOT" in content

    def test_triggers_on_pull_request(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        parsed = yaml.safe_load(content)
        assert "pull_request" in parsed.get("on", parsed.get(True, {}))


class TestIdempotency:
    """Tests for idempotent behavior."""

    def test_idempotent_overwrite(self, tmp_path):
        generate_ci_workflow(tmp_path)
        content1 = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        generate_ci_workflow(tmp_path)
        content2 = (
            tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        ).read_text()
        assert content1 == content2


class TestClaudeMdCISection:
    """Tests for the CLAUDE.md CI section template."""

    def test_mentions_headless(self):
        section = get_ci_claude_md_section()
        assert "--headless" in section

    def test_mentions_enable_all_servers(self):
        section = get_ci_claude_md_section()
        assert "enableAllProjectMcpServers" in section

    def test_mentions_init_only(self):
        section = get_ci_claude_md_section()
        assert "--init-only" in section

    def test_mentions_validate_changed(self):
        section = get_ci_claude_md_section()
        assert "tapps_validate_changed" in section or "validate-changed" in section


class TestClaudeMdTemplate:
    """Tests that the CLAUDE.md template includes the CI section."""

    def test_template_has_ci_section(self):
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        content = load_platform_rules("claude")
        assert "CI Integration" in content
        assert "enableAllProjectMcpServers" in content
