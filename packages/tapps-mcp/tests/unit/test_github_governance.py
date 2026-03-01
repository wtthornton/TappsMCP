"""Tests for GitHub governance and security configuration generators.

Epic 22: GitHub Governance & Security Configuration.
"""

from __future__ import annotations


class TestSecurityPolicyGeneration:
    """Tests for generate_security_policy (Story 22.2)."""

    def test_creates_security_md(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        generate_security_policy(tmp_path)
        assert (tmp_path / "SECURITY.md").exists()

    def test_has_reporting_section(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        generate_security_policy(tmp_path)
        content = (tmp_path / "SECURITY.md").read_text()
        assert "Reporting" in content

    def test_has_response_timeline(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        generate_security_policy(tmp_path)
        content = (tmp_path / "SECURITY.md").read_text()
        assert "Response Timeline" in content

    def test_has_supported_versions(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        generate_security_policy(tmp_path)
        content = (tmp_path / "SECURITY.md").read_text()
        assert "Supported Versions" in content

    def test_skips_when_exists(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        (tmp_path / "SECURITY.md").write_text("existing", encoding="utf-8")
        result = generate_security_policy(tmp_path)
        assert result["action"] == "skipped"
        assert (tmp_path / "SECURITY.md").read_text() == "existing"

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        result = generate_security_policy(tmp_path)
        assert result["action"] == "created"
        assert result["file"] == "SECURITY.md"


class TestCodeownersGeneration:
    """Tests for generate_codeowners (Story 22.1)."""

    def test_creates_codeowners(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_codeowners

        generate_codeowners(tmp_path)
        assert (tmp_path / ".github" / "CODEOWNERS").exists()

    def test_has_catch_all_rule(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_codeowners

        generate_codeowners(tmp_path)
        content = (tmp_path / ".github" / "CODEOWNERS").read_text()
        assert "*" in content
        assert "@your-team" in content

    def test_has_security_paths(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_codeowners

        generate_codeowners(tmp_path)
        content = (tmp_path / ".github" / "CODEOWNERS").read_text()
        assert "security" in content.lower()

    def test_has_workflow_paths(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_codeowners

        generate_codeowners(tmp_path)
        content = (tmp_path / ".github" / "CODEOWNERS").read_text()
        assert ".github/workflows/" in content

    def test_skips_when_exists(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_codeowners

        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        (github_dir / "CODEOWNERS").write_text("existing", encoding="utf-8")
        result = generate_codeowners(tmp_path)
        assert result["action"] == "skipped"

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_codeowners

        result = generate_codeowners(tmp_path)
        assert result["action"] == "created"


class TestRulesetScriptGeneration:
    """Tests for generate_ruleset_scripts (Story 22.3)."""

    def test_creates_scripts_directory(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_ruleset_scripts

        generate_ruleset_scripts(tmp_path)
        assert (tmp_path / ".github" / "scripts").is_dir()

    def test_creates_bash_script(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_ruleset_scripts

        generate_ruleset_scripts(tmp_path)
        sh = tmp_path / ".github" / "scripts" / "setup-rulesets.sh"
        assert sh.exists()
        content = sh.read_text()
        assert "gh api" in content
        assert "rulesets" in content

    def test_creates_powershell_script(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_ruleset_scripts

        generate_ruleset_scripts(tmp_path)
        ps1 = tmp_path / ".github" / "scripts" / "setup-rulesets.ps1"
        assert ps1.exists()
        content = ps1.read_text()
        assert "gh api" in content

    def test_bash_script_is_executable(self, tmp_path):
        import os
        import sys

        if sys.platform == "win32":
            return  # Skip on Windows

        from tapps_mcp.pipeline.github_governance import generate_ruleset_scripts

        generate_ruleset_scripts(tmp_path)
        sh = tmp_path / ".github" / "scripts" / "setup-rulesets.sh"
        assert os.access(sh, os.X_OK)

    def test_scripts_have_gh_api_commands(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_ruleset_scripts

        generate_ruleset_scripts(tmp_path)
        sh_content = (tmp_path / ".github" / "scripts" / "setup-rulesets.sh").read_text()
        assert "pull_request" in sh_content
        assert "required_status_checks" in sh_content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_ruleset_scripts

        result = generate_ruleset_scripts(tmp_path)
        assert result["count"] == 2
        assert result["action"] == "created"


class TestSetupGuideGeneration:
    """Tests for generate_setup_guide (Story 22.4)."""

    def test_creates_setup_guide(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        generate_setup_guide(tmp_path)
        assert (tmp_path / "docs" / "GITHUB_SETUP_GUIDE.md").exists()

    def test_has_rulesets_section(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        generate_setup_guide(tmp_path)
        content = (tmp_path / "docs" / "GITHUB_SETUP_GUIDE.md").read_text()
        assert "Rulesets" in content

    def test_has_copilot_mcp_section(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        generate_setup_guide(tmp_path)
        content = (tmp_path / "docs" / "GITHUB_SETUP_GUIDE.md").read_text()
        assert "Copilot" in content
        assert "MCP" in content

    def test_has_secret_scanning_section(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        generate_setup_guide(tmp_path)
        content = (tmp_path / "docs" / "GITHUB_SETUP_GUIDE.md").read_text()
        assert "Secret Scanning" in content

    def test_has_dependabot_section(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        generate_setup_guide(tmp_path)
        content = (tmp_path / "docs" / "GITHUB_SETUP_GUIDE.md").read_text()
        assert "Dependabot" in content

    def test_result_dict(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        result = generate_setup_guide(tmp_path)
        assert result["action"] == "created"


class TestGenerateAllGovernance:
    """Tests for generate_all_governance (Story 22.5)."""

    def test_generates_all_governance(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_all_governance

        result = generate_all_governance(tmp_path)
        assert result["success"] is True
        assert result["total_files"] == 5  # SECURITY + CODEOWNERS + 2 scripts + guide

    def test_all_files_created(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_all_governance

        generate_all_governance(tmp_path)
        assert (tmp_path / "SECURITY.md").exists()
        assert (tmp_path / ".github" / "CODEOWNERS").exists()
        assert (tmp_path / ".github" / "scripts" / "setup-rulesets.sh").exists()
        assert (tmp_path / ".github" / "scripts" / "setup-rulesets.ps1").exists()
        assert (tmp_path / "docs" / "GITHUB_SETUP_GUIDE.md").exists()

    def test_result_has_sub_results(self, tmp_path):
        from tapps_mcp.pipeline.github_governance import generate_all_governance

        result = generate_all_governance(tmp_path)
        assert "security_policy" in result
        assert "codeowners" in result
        assert "ruleset_scripts" in result
        assert "setup_guide" in result
