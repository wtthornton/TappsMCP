"""Tests for GitHub Copilot agent integration generators.

Epic 21: GitHub Copilot Agent Integration.
"""

from __future__ import annotations


class TestAgentProfileGeneration:
    """Tests for generate_agent_profiles (Story 21.1)."""

    def test_creates_agents_directory(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        assert (tmp_path / ".github" / "agents").is_dir()

    def test_creates_quality_agent(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        quality = tmp_path / ".github" / "agents" / "tapps-quality.md"
        assert quality.exists()
        content = quality.read_text()
        assert "tapps_quick_check" in content
        assert "tapps_score_file" in content

    def test_creates_researcher_agent(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        researcher = tmp_path / ".github" / "agents" / "tapps-researcher.md"
        assert researcher.exists()
        content = researcher.read_text()
        assert "tapps_research" in content
        assert "tapps_lookup_docs" in content

    def test_quality_agent_has_yaml_frontmatter(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        content = (tmp_path / ".github" / "agents" / "tapps-quality.md").read_text()
        assert "---" in content
        assert "name:" in content
        assert "description:" in content
        assert "tools:" in content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        result = generate_agent_profiles(tmp_path)
        assert result["count"] == 2
        assert result["action"] == "created"
        assert len(result["files"]) == 2

    def test_idempotent(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        generate_agent_profiles(tmp_path)
        agents = list((tmp_path / ".github" / "agents").iterdir())
        assert len(agents) == 2


class TestPathScopedInstructions:
    """Tests for generate_path_scoped_instructions (Story 21.2)."""

    def test_creates_instructions_directory(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        generate_path_scoped_instructions(tmp_path)
        assert (tmp_path / ".github" / "instructions").is_dir()

    def test_creates_quality_instructions(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        generate_path_scoped_instructions(tmp_path)
        quality = tmp_path / ".github" / "instructions" / "quality.instructions.md"
        assert quality.exists()
        content = quality.read_text()
        assert "applyTo:" in content
        assert "**/*.py" in content

    def test_creates_security_instructions(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        generate_path_scoped_instructions(tmp_path)
        security = tmp_path / ".github" / "instructions" / "security.instructions.md"
        assert security.exists()
        content = security.read_text()
        assert "security" in content.lower()

    def test_creates_testing_instructions(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        generate_path_scoped_instructions(tmp_path)
        testing = tmp_path / ".github" / "instructions" / "testing.instructions.md"
        assert testing.exists()
        content = testing.read_text()
        assert "tests/**" in content

    def test_instructions_have_yaml_frontmatter(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        generate_path_scoped_instructions(tmp_path)
        for f in (tmp_path / ".github" / "instructions").iterdir():
            content = f.read_text()
            assert "---" in content, f"{f.name} missing frontmatter"
            assert "applyTo:" in content, f"{f.name} missing applyTo"

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        result = generate_path_scoped_instructions(tmp_path)
        assert result["count"] == 3
        assert result["action"] == "created"


class TestEnhancedCopilotInstructions:
    """Tests for generate_enhanced_copilot_instructions (Story 21.3)."""

    def test_creates_copilot_instructions(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        generate_enhanced_copilot_instructions(tmp_path)
        assert (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_includes_pipeline_stages(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        generate_enhanced_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "Discover" in content
        assert "Research" in content
        assert "Develop" in content
        assert "Validate" in content
        assert "Verify" in content

    def test_includes_tool_calls(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        generate_enhanced_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "tapps_session_start" in content
        assert "tapps_quick_check" in content
        assert "tapps_validate_changed" in content

    def test_up_to_date_when_current_version(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        generate_enhanced_copilot_instructions(tmp_path)
        result = generate_enhanced_copilot_instructions(tmp_path)
        assert result["action"] == "up-to-date"


class TestAgenticWorkflow:
    """Tests for generate_agentic_workflow (Story 21.4)."""

    def test_creates_agentic_workflow(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agentic_workflow

        generate_agentic_workflow(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "agentic-pr-review.yml").exists()

    def test_agentic_workflow_has_pr_trigger(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agentic_workflow

        generate_agentic_workflow(tmp_path)
        content = (
            tmp_path / ".github" / "workflows" / "agentic-pr-review.yml"
        ).read_text()
        assert "pull_request" in content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_agentic_workflow

        result = generate_agentic_workflow(tmp_path)
        assert result["action"] == "created"


class TestGenerateAllCopilotConfig:
    """Tests for generate_all_copilot_config (Story 21.5)."""

    def test_generates_all_config(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

        result = generate_all_copilot_config(tmp_path)
        assert result["success"] is True
        assert result["total_files"] == 7  # 2 agents + 3 instructions + 1 copilot + 1 workflow

    def test_all_files_created(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

        generate_all_copilot_config(tmp_path)
        assert (tmp_path / ".github" / "agents" / "tapps-quality.md").exists()
        assert (tmp_path / ".github" / "agents" / "tapps-researcher.md").exists()
        assert (tmp_path / ".github" / "instructions" / "quality.instructions.md").exists()
        assert (tmp_path / ".github" / "instructions" / "security.instructions.md").exists()
        assert (tmp_path / ".github" / "instructions" / "testing.instructions.md").exists()
        assert (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_result_has_sub_results(self, tmp_path):
        from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

        result = generate_all_copilot_config(tmp_path)
        assert "agent_profiles" in result
        assert "path_instructions" in result
        assert "copilot_instructions" in result
        assert "agentic_workflow" in result
