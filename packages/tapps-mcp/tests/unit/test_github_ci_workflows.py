"""Tests for enhanced GitHub Actions CI workflow generators.

Epic 20: GitHub Actions CI Enhancement.
"""

from __future__ import annotations


class TestEnhancedQualityWorkflow:
    """Tests for generate_enhanced_ci_workflow (Story 20.1)."""

    def test_creates_quality_workflow(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "tapps-quality.yml").exists()

    def test_has_permissions_block(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality.yml").read_text()
        assert "permissions:" in content
        assert "contents: read" in content

    def test_has_concurrency_group(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality.yml").read_text()
        assert "concurrency:" in content
        assert "cancel-in-progress: true" in content

    def test_has_workflow_dispatch(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality.yml").read_text()
        assert "workflow_dispatch:" in content

    def test_uses_artifacts_v4(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality.yml").read_text()
        assert "upload-artifact@v4" in content

    def test_has_timeout(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality.yml").read_text()
        assert "timeout-minutes:" in content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        result = generate_enhanced_ci_workflow(tmp_path)
        assert result["action"] == "created"

    def test_updated_when_exists(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_enhanced_ci_workflow

        generate_enhanced_ci_workflow(tmp_path)
        result = generate_enhanced_ci_workflow(tmp_path)
        assert result["action"] == "updated"


class TestCodeQLWorkflow:
    """Tests for generate_codeql_workflow (Story 20.2)."""

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


class TestCopilotSetupSteps:
    """Tests for generate_copilot_setup_steps (Story 20.3)."""

    def test_creates_copilot_setup(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_copilot_setup_steps

        generate_copilot_setup_steps(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "copilot-setup-steps.yml").exists()

    def test_installs_tapps_mcp(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_copilot_setup_steps

        generate_copilot_setup_steps(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "copilot-setup-steps.yml").read_text()
        assert "tapps-mcp" in content

    def test_installs_quality_checkers(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_copilot_setup_steps

        generate_copilot_setup_steps(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "copilot-setup-steps.yml").read_text()
        assert "ruff" in content
        assert "mypy" in content
        assert "bandit" in content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_copilot_setup_steps

        result = generate_copilot_setup_steps(tmp_path)
        assert result["action"] == "created"


class TestDependabotAutoMerge:
    """Tests for generate_dependabot_auto_merge (Story 20.4)."""

    def test_creates_auto_merge_workflow(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_dependabot_auto_merge

        generate_dependabot_auto_merge(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "dependabot-auto-merge.yml").exists()

    def test_only_auto_merges_non_major(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_dependabot_auto_merge

        generate_dependabot_auto_merge(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text()
        assert "semver-patch" in content or "semver-minor" in content

    def test_uses_github_token(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_dependabot_auto_merge

        generate_dependabot_auto_merge(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text()
        assert "GITHUB_TOKEN" in content


class TestReusableQualityWorkflow:
    """Tests for generate_reusable_quality_workflow (Story 20.5)."""

    def test_creates_reusable_workflow(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_reusable_quality_workflow

        generate_reusable_quality_workflow(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "tapps-quality-reusable.yml").exists()

    def test_has_workflow_call_trigger(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_reusable_quality_workflow

        generate_reusable_quality_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality-reusable.yml").read_text()
        assert "workflow_call:" in content

    def test_has_preset_input(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_reusable_quality_workflow

        generate_reusable_quality_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality-reusable.yml").read_text()
        assert "preset:" in content

    def test_has_python_version_input(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_reusable_quality_workflow

        generate_reusable_quality_workflow(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "tapps-quality-reusable.yml").read_text()
        assert "python-version:" in content


class TestGenerateAllWorkflows:
    """Tests for generate_all_ci_workflows (Story 20.6)."""

    def test_generates_all_workflows(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        result = generate_all_ci_workflows(tmp_path)
        assert result["success"] is True
        assert result["total_workflows"] == 5

    def test_all_workflow_files_created(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        generate_all_ci_workflows(tmp_path)
        wf_dir = tmp_path / ".github" / "workflows"
        assert (wf_dir / "tapps-quality.yml").exists()
        assert (wf_dir / "codeql-analysis.yml").exists()
        assert (wf_dir / "copilot-setup-steps.yml").exists()
        assert (wf_dir / "dependabot-auto-merge.yml").exists()
        assert (wf_dir / "tapps-quality-reusable.yml").exists()

    def test_result_has_sub_results(self, tmp_path):
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        result = generate_all_ci_workflows(tmp_path)
        assert "quality_workflow" in result
        assert "codeql_workflow" in result
        assert "copilot_setup_steps" in result
        assert "dependabot_auto_merge" in result
        assert "reusable_quality_workflow" in result
