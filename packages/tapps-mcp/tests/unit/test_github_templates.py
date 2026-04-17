"""Tests for GitHub Issue forms, PR templates, and Dependabot configuration.

Epic 19: GitHub Issue & PR Templates.
"""

from __future__ import annotations

import yaml


class TestIssueTemplateGeneration:
    """Tests for generate_issue_templates (Story 19.1)."""

    def test_creates_issue_template_directory(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        assert (tmp_path / ".github" / "ISSUE_TEMPLATE").is_dir()

    def test_creates_bug_report_form(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        bug_report = tmp_path / ".github" / "ISSUE_TEMPLATE" / "bug-report.yml"
        assert bug_report.exists()
        content = yaml.safe_load(bug_report.read_text())
        assert content["name"] == "Bug Report"

    def test_creates_feature_request_form(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        feature = tmp_path / ".github" / "ISSUE_TEMPLATE" / "feature-request.yml"
        assert feature.exists()
        content = yaml.safe_load(feature.read_text())
        assert content["name"] == "Feature Request"

    def test_creates_task_form(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        task = tmp_path / ".github" / "ISSUE_TEMPLATE" / "task.yml"
        assert task.exists()
        content = yaml.safe_load(task.read_text())
        assert content["name"] == "Task"

    def test_creates_config_yml(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        config = tmp_path / ".github" / "ISSUE_TEMPLATE" / "config.yml"
        assert config.exists()
        content = yaml.safe_load(config.read_text())
        assert content["blank_issues_enabled"] is False

    def test_bug_report_has_required_fields(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        bug_report = tmp_path / ".github" / "ISSUE_TEMPLATE" / "bug-report.yml"
        content = yaml.safe_load(bug_report.read_text())
        body_types = [item["type"] for item in content["body"]]
        assert "textarea" in body_types
        assert "dropdown" in body_types

    def test_feature_request_has_required_fields(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        feature = tmp_path / ".github" / "ISSUE_TEMPLATE" / "feature-request.yml"
        content = yaml.safe_load(feature.read_text())
        assert len(content["body"]) >= 3

    def test_result_dict_structure(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        result = generate_issue_templates(tmp_path)
        assert "files" in result
        assert "action" in result
        assert "count" in result
        assert result["count"] == 4
        assert result["action"] == "created"

    def test_all_forms_valid_yaml(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        template_dir = tmp_path / ".github" / "ISSUE_TEMPLATE"
        for yml_file in template_dir.glob("*.yml"):
            content = yaml.safe_load(yml_file.read_text())
            assert content is not None, f"{yml_file.name} is not valid YAML"

    def test_idempotent(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_issue_templates

        generate_issue_templates(tmp_path)
        generate_issue_templates(tmp_path)
        files = list((tmp_path / ".github" / "ISSUE_TEMPLATE").iterdir())
        assert len(files) == 4


class TestPRTemplateGeneration:
    """Tests for generate_pr_template (Story 19.2)."""

    def test_creates_pr_template(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        assert (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()

    def test_pr_template_has_summary_section(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        content = (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
        assert "## Summary" in content

    def test_pr_template_has_test_plan(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        content = (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
        assert "## Test Plan" in content

    def test_pr_template_has_breaking_changes(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        content = (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
        assert "## Breaking Changes" in content

    def test_pr_template_has_checklist(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        content = (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
        assert "## Checklist" in content
        assert "- [ ]" in content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        result = generate_pr_template(tmp_path)
        assert result["action"] == "created"
        assert "PULL_REQUEST_TEMPLATE.md" in result["file"]


class TestDependabotConfigGeneration:
    """Tests for generate_dependabot_config (Story 19.4)."""

    def test_creates_dependabot_yml(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_dependabot_config

        generate_dependabot_config(tmp_path)
        assert (tmp_path / ".github" / "dependabot.yml").exists()

    def test_dependabot_has_pip_ecosystem(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_dependabot_config

        generate_dependabot_config(tmp_path)
        content = yaml.safe_load((tmp_path / ".github" / "dependabot.yml").read_text())
        ecosystems = [u["package-ecosystem"] for u in content["updates"]]
        assert "pip" in ecosystems

    def test_dependabot_has_github_actions_ecosystem(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_dependabot_config

        generate_dependabot_config(tmp_path)
        content = yaml.safe_load((tmp_path / ".github" / "dependabot.yml").read_text())
        ecosystems = [u["package-ecosystem"] for u in content["updates"]]
        assert "github-actions" in ecosystems

    def test_dependabot_has_grouped_updates(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_dependabot_config

        generate_dependabot_config(tmp_path)
        content = yaml.safe_load((tmp_path / ".github" / "dependabot.yml").read_text())
        pip_update = next(u for u in content["updates"] if u["package-ecosystem"] == "pip")
        assert "groups" in pip_update

    def test_dependabot_version_2(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_dependabot_config

        generate_dependabot_config(tmp_path)
        content = yaml.safe_load((tmp_path / ".github" / "dependabot.yml").read_text())
        assert content["version"] == 2

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_dependabot_config

        result = generate_dependabot_config(tmp_path)
        assert result["action"] == "created"
        assert "dependabot.yml" in result["file"]


class TestGenerateAllGithubTemplates:
    """Tests for generate_all_github_templates (Story 19.5)."""

    def test_generates_all_templates(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_all_github_templates

        result = generate_all_github_templates(tmp_path)
        assert result["success"] is True
        assert result["total_files"] == 6  # 4 issue + 1 PR + 1 dependabot

    def test_all_files_created(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_all_github_templates

        generate_all_github_templates(tmp_path)
        assert (tmp_path / ".github" / "ISSUE_TEMPLATE" / "bug-report.yml").exists()
        assert (tmp_path / ".github" / "ISSUE_TEMPLATE" / "feature-request.yml").exists()
        assert (tmp_path / ".github" / "ISSUE_TEMPLATE" / "task.yml").exists()
        assert (tmp_path / ".github" / "ISSUE_TEMPLATE" / "config.yml").exists()
        assert (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()
        assert (tmp_path / ".github" / "dependabot.yml").exists()

    def test_result_has_sub_results(self, tmp_path):
        from tapps_mcp.pipeline.github_templates import generate_all_github_templates

        result = generate_all_github_templates(tmp_path)
        assert "issue_templates" in result
        assert "pr_template" in result
        assert "dependabot" in result
