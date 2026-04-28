"""Upgrade must not silently re-add managed config files the user has deleted.

The GitHub workflow + Copilot config generators are called unconditionally
by ``upgrade_pipeline``. Without a deletion-aware guard, a user who removes
``codeql-analysis.yml`` (or a Copilot agent profile / instruction file) sees
it reappear on the next ``tapps_upgrade`` -- making a GitHub-side
``gh workflow disable`` the only durable opt-out.

In ``upgrade_mode=True``, a missing target means "user deleted it" and the
generator skips with a warning instead of rewriting.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.github_ci import (
    generate_all_ci_workflows,
    generate_codeql_workflow,
)
from tapps_mcp.pipeline.github_copilot import (
    generate_agent_profiles,
    generate_all_copilot_config,
    generate_enhanced_copilot_instructions,
    generate_path_scoped_instructions,
)


class TestCiWorkflowHonorsDeletion:
    def test_init_mode_creates_codeql(self, tmp_path: Path) -> None:
        result = generate_codeql_workflow(tmp_path)
        assert result["action"] == "created"
        assert (tmp_path / ".github" / "workflows" / "codeql-analysis.yml").exists()

    def test_upgrade_mode_skips_when_user_deleted_file(self, tmp_path: Path) -> None:
        generate_codeql_workflow(tmp_path)
        target = tmp_path / ".github" / "workflows" / "codeql-analysis.yml"
        target.unlink()

        result = generate_codeql_workflow(tmp_path, upgrade_mode=True)
        assert result["action"] == "skipped (deleted by user)"
        assert not target.exists()

    def test_upgrade_mode_updates_existing_file(self, tmp_path: Path) -> None:
        generate_codeql_workflow(tmp_path)
        target = tmp_path / ".github" / "workflows" / "codeql-analysis.yml"
        target.write_text("user-edited content", encoding="utf-8")

        result = generate_codeql_workflow(tmp_path, upgrade_mode=True)
        assert result["action"] == "updated"
        assert target.read_text(encoding="utf-8") != "user-edited content"

    def test_generate_all_forwards_upgrade_mode(self, tmp_path: Path) -> None:
        generate_all_ci_workflows(tmp_path)
        (tmp_path / ".github" / "workflows" / "codeql-analysis.yml").unlink()

        result = generate_all_ci_workflows(tmp_path, upgrade_mode=True)
        assert result["codeql_workflow"]["action"] == "skipped (deleted by user)"


class TestAgentProfilesHonorDeletion:
    def test_upgrade_mode_skips_deleted_profile(self, tmp_path: Path) -> None:
        generate_agent_profiles(tmp_path)
        deleted = tmp_path / ".github" / "agents" / "tapps-quality.md"
        kept = tmp_path / ".github" / "agents" / "tapps-researcher.md"
        deleted.unlink()

        result = generate_agent_profiles(tmp_path, upgrade_mode=True)
        assert not deleted.exists()
        assert kept.exists()
        assert "skipped_deleted" in result
        assert any("tapps-quality.md" in path for path in result["skipped_deleted"])

    def test_init_mode_recreates_missing_profile(self, tmp_path: Path) -> None:
        generate_agent_profiles(tmp_path)
        deleted = tmp_path / ".github" / "agents" / "tapps-quality.md"
        deleted.unlink()

        generate_agent_profiles(tmp_path)
        assert deleted.exists()


class TestPathInstructionsHonorDeletion:
    def test_upgrade_mode_skips_deleted_instruction(self, tmp_path: Path) -> None:
        generate_path_scoped_instructions(tmp_path)
        deleted = tmp_path / ".github" / "instructions" / "security.instructions.md"
        deleted.unlink()

        result = generate_path_scoped_instructions(tmp_path, upgrade_mode=True)
        assert not deleted.exists()
        assert "skipped_deleted" in result


class TestEnhancedCopilotInstructionsHonorDeletion:
    def test_upgrade_mode_skips_when_deleted(self, tmp_path: Path) -> None:
        generate_enhanced_copilot_instructions(tmp_path)
        target = tmp_path / ".github" / "copilot-instructions.md"
        target.unlink()

        result = generate_enhanced_copilot_instructions(tmp_path, upgrade_mode=True)
        assert result["action"] == "skipped (deleted by user)"
        assert not target.exists()


class TestGenerateAllCopilotConfigForwardsUpgradeMode:
    def test_all_three_subcomponents_honor_deletion(self, tmp_path: Path) -> None:
        generate_all_copilot_config(tmp_path)

        (tmp_path / ".github" / "agents" / "tapps-quality.md").unlink()
        (tmp_path / ".github" / "instructions" / "security.instructions.md").unlink()
        (tmp_path / ".github" / "copilot-instructions.md").unlink()

        result = generate_all_copilot_config(tmp_path, upgrade_mode=True)

        assert "skipped_deleted" in result["agent_profiles"]
        assert "skipped_deleted" in result["path_instructions"]
        assert result["copilot_instructions"]["action"] == "skipped (deleted by user)"
        assert not (tmp_path / ".github" / "agents" / "tapps-quality.md").exists()
        assert not (tmp_path / ".github" / "copilot-instructions.md").exists()
