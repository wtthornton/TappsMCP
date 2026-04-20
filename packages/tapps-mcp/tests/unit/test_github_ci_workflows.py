"""Tests for GitHub Actions CI workflow generators.

Only CodeQL is emitted — quality work (lint, tests, build, quality gate)
runs locally via the TappsMCP pipeline.
"""

from __future__ import annotations


class TestCodeQLWorkflow:
    def test_creates_codeql_workflow(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_codeql_workflow

        generate_codeql_workflow(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "codeql-analysis.yml").exists()

    def test_has_security_events_permission(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_codeql_workflow

        generate_codeql_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "codeql-analysis.yml").read_text()
        assert "security-events: write" in content

    def test_has_python_language(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_codeql_workflow

        generate_codeql_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "codeql-analysis.yml").read_text()
        assert "python" in content

    def test_has_scheduled_run(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_codeql_workflow

        generate_codeql_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "codeql-analysis.yml").read_text()
        assert "schedule:" in content
        assert "cron:" in content


class TestGenerateAllWorkflows:
    def test_generates_only_codeql(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        result = generate_all_ci_workflows(tmp_path)
        assert result["success"] is True
        assert result["total_workflows"] == 1
        assert "codeql_workflow" in result

    def test_only_codeql_file_created(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        generate_all_ci_workflows(tmp_path)
        wf_dir = tmp_path / ".github" / "workflows"
        assert (wf_dir / "codeql-analysis.yml").exists()
        # Removed workflows must not come back.
        assert not (wf_dir / "tapps-quality.yml").exists()
        assert not (wf_dir / "tapps-quality-reusable.yml").exists()
        assert not (wf_dir / "copilot-setup-steps.yml").exists()
        assert not (wf_dir / "dependabot-auto-merge.yml").exists()
