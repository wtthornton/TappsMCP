"""Tests for the GitHub domain expert (Epic 21, Story 21.7)."""

from __future__ import annotations

from pathlib import Path


class TestGitHubDomainRegistration:
    """Tests that the GitHub domain is properly registered."""

    def test_github_in_technical_domains(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        assert "github" in ExpertRegistry.TECHNICAL_DOMAINS

    def test_github_expert_config_exists(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("github")
        assert expert is not None
        assert expert.expert_id == "expert-github"
        assert expert.primary_domain == "github"

    def test_github_expert_name(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("github")
        assert expert is not None
        assert "GitHub" in expert.expert_name

    def test_github_expert_in_all_experts(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        all_experts = ExpertRegistry.get_all_experts()
        github_experts = [e for e in all_experts if e.primary_domain == "github"]
        assert len(github_experts) == 1

    def test_total_experts_is_17(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        assert len(ExpertRegistry.BUILTIN_EXPERTS) == 17
        assert len(ExpertRegistry.TECHNICAL_DOMAINS) == 17


class TestGitHubDomainDetection:
    """Tests that domain detection recognizes GitHub topics."""

    def test_detects_github_actions(self):
        from tapps_mcp.experts.domain_detector import DOMAIN_KEYWORDS

        assert "github" in DOMAIN_KEYWORDS
        keywords = DOMAIN_KEYWORDS["github"]
        assert "github actions" in keywords

    def test_detects_copilot_agent(self):
        from tapps_mcp.experts.domain_detector import DOMAIN_KEYWORDS

        keywords = DOMAIN_KEYWORDS["github"]
        assert "copilot coding agent" in keywords or "copilot agent" in keywords

    def test_detects_rulesets(self):
        from tapps_mcp.experts.domain_detector import DOMAIN_KEYWORDS

        keywords = DOMAIN_KEYWORDS["github"]
        assert "ruleset" in keywords

    def test_detects_dependabot(self):
        from tapps_mcp.experts.domain_detector import DOMAIN_KEYWORDS

        keywords = DOMAIN_KEYWORDS["github"]
        assert "dependabot" in keywords


class TestGitHubKnowledgeFiles:
    """Tests that knowledge files exist and are valid."""

    def test_knowledge_directory_exists(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        github_dir = kb_path / "github"
        assert github_dir.is_dir(), f"Missing: {github_dir}"

    def test_has_9_knowledge_files(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        github_dir = kb_path / "github"
        md_files = list(github_dir.glob("*.md"))
        assert len(md_files) == 9, f"Expected 9, found {len(md_files)}: {[f.name for f in md_files]}"

    def test_knowledge_files_not_empty(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        github_dir = kb_path / "github"
        for md_file in github_dir.glob("*.md"):
            content = md_file.read_text()
            assert len(content) > 100, f"{md_file.name} is too short ({len(content)} chars)"

    def test_actions_comprehensive_exists(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        assert (kb_path / "github" / "github-actions-comprehensive.md").exists()

    def test_copilot_agent_setup_exists(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        assert (kb_path / "github" / "github-copilot-agent-setup.md").exists()

    def test_security_features_exists(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        assert (kb_path / "github" / "github-security-features.md").exists()

    def test_mcp_integration_exists(self):
        from tapps_mcp.experts.registry import ExpertRegistry

        kb_path = ExpertRegistry.get_knowledge_base_path()
        assert (kb_path / "github" / "github-mcp-integration.md").exists()
