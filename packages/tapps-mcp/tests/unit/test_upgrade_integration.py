"""Integration tests for Epic 33.5: Upgrade path for corrected artifacts.

Verifies that ``tapps_upgrade`` regenerates ALL corrected artifacts from
Epic 33 stories: skills (33.1), subagents (33.2), path-scoped rules (33.3),
and permission rules (33.4).
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_old_style_skill(skills_dir: Path, name: str) -> None:
    """Create a skill file with old-style ``tools:`` frontmatter."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Old style.\n"
        f"tools: mcp__tapps-mcp__tapps_score_file\n---\n\nOld body.\n",
        encoding="utf-8",
    )


def _create_old_style_agent(agents_dir: Path, name: str) -> None:
    """Create an agent file without mcpServers or maxTurns."""
    (agents_dir / name).write_text(
        f"---\nname: {name.replace('.md', '')}\n"
        f"description: Old agent.\n"
        f"tools: Read, Glob\n---\n\nOld body.\n",
        encoding="utf-8",
    )


def _setup_claude_project(tmp_path: Path) -> None:
    """Create a minimal Claude Code project structure."""
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)


def _setup_cursor_project(tmp_path: Path) -> None:
    """Create a minimal Cursor project structure."""
    (tmp_path / ".cursor").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tests: Skills get corrected frontmatter after upgrade
# ---------------------------------------------------------------------------


class TestUpgradeSkills:
    """Verify skills are regenerated with corrected frontmatter."""

    def test_skills_have_allowed_tools_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style ``tools:`` skills get replaced with ``allowed-tools:``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-score")

        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True

        skill_content = (skills_dir / "tapps-score" / "SKILL.md").read_text(encoding="utf-8")
        assert "allowed-tools:" in skill_content
        assert "\ntools:" not in skill_content

    def test_skills_have_argument_hint_after_upgrade(self, tmp_path: Path) -> None:
        """Skills that need argument-hint get it after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-score")

        upgrade_pipeline(tmp_path, platform="claude")

        skill_content = (skills_dir / "tapps-score" / "SKILL.md").read_text(encoding="utf-8")
        assert "argument-hint:" in skill_content

    def test_skills_updated_list_populated(self, tmp_path: Path) -> None:
        """Upgrade result reports skills as updated, not skipped."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-score")
        _create_old_style_skill(skills_dir, "tapps-gate")

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        assert len(platforms) > 0
        claude_result = platforms[0]
        skills_info = claude_result["components"]["skills"]
        assert "tapps-score" in skills_info["updated"]
        assert "tapps-gate" in skills_info["updated"]

    def test_new_skills_created_during_upgrade(self, tmp_path: Path) -> None:
        """Skills that don't exist yet get created during upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        # Don't create any old skills - all should be created

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        claude_result = platforms[0]
        skills_info = claude_result["components"]["skills"]
        assert len(skills_info["created"]) >= 5  # At least 5 skills exist


# ---------------------------------------------------------------------------
# Tests: Subagents get corrected frontmatter after upgrade
# ---------------------------------------------------------------------------


class TestUpgradeSubagents:
    """Verify subagents are regenerated with corrected frontmatter."""

    def test_subagents_have_mcp_servers_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style agents get ``mcpServers`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-reviewer.md").read_text(encoding="utf-8")
        assert "mcpServers:" in content
        assert "tapps-mcp:" in content

    def test_subagents_have_max_turns_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style agents get ``maxTurns`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-reviewer.md").read_text(encoding="utf-8")
        assert "maxTurns:" in content

    def test_subagents_have_permission_mode_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style agents get correct ``permissionMode`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-reviewer.md").read_text(encoding="utf-8")
        assert "permissionMode:" in content

    def test_subagents_updated_list_populated(self, tmp_path: Path) -> None:
        """Upgrade result reports agents as updated."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        claude_result = platforms[0]
        agents_info = claude_result["components"]["agents"]
        assert "tapps-reviewer.md" in agents_info["updated"]

    def test_review_fixer_has_isolation_worktree(self, tmp_path: Path) -> None:
        """tapps-review-fixer agent has ``isolation: worktree`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-review-fixer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-review-fixer.md").read_text(encoding="utf-8")
        assert "isolation: worktree" in content


# ---------------------------------------------------------------------------
# Tests: Python quality rule generated after upgrade
# ---------------------------------------------------------------------------


class TestUpgradePythonQualityRule:
    """Verify path-scoped python-quality.md is created/updated."""

    def test_python_quality_rule_exists_after_upgrade(self, tmp_path: Path) -> None:
        """Upgrade creates ``.claude/rules/python-quality.md``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")

        rule_path = tmp_path / ".claude" / "rules" / "python-quality.md"
        assert rule_path.exists()

    def test_python_quality_rule_has_paths_frontmatter(self, tmp_path: Path) -> None:
        """Rule file has ``paths:`` YAML frontmatter scoping to Python files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")

        rule_path = tmp_path / ".claude" / "rules" / "python-quality.md"
        content = rule_path.read_text(encoding="utf-8")
        assert "paths:" in content
        assert '"**/*.py"' in content

    def test_python_quality_rule_updated_on_rerun(self, tmp_path: Path) -> None:
        """Rule is refreshed on subsequent upgrade runs."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        # First run creates it
        result1 = upgrade_pipeline(tmp_path, platform="claude")
        platforms1 = result1["components"]["platforms"]
        rule1 = platforms1[0]["components"]["python_quality_rule"]
        assert rule1["action"] == "created"

        # Second run updates it
        result2 = upgrade_pipeline(tmp_path, platform="claude")
        platforms2 = result2["components"]["platforms"]
        rule2 = platforms2[0]["components"]["python_quality_rule"]
        assert rule2["action"] == "updated"


# ---------------------------------------------------------------------------
# Tests: Permission rules in settings.json
# ---------------------------------------------------------------------------


class TestUpgradePermissionRules:
    """Verify ``.claude/settings.json`` gets permission entries."""

    def test_settings_json_has_permissions_after_upgrade(self, tmp_path: Path) -> None:
        """Upgrade creates settings.json with permission allow list."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")

        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        config = json.loads(settings_path.read_text(encoding="utf-8"))
        allow_list = config.get("permissions", {}).get("allow", [])
        assert "mcp__tapps-mcp" in allow_list
        assert "mcp__tapps-mcp__*" in allow_list

    def test_settings_json_preserves_existing_entries(self, tmp_path: Path) -> None:
        """Upgrade merges into existing settings without losing user entries."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        settings_path = tmp_path / ".claude" / "settings.json"
        existing = {"permissions": {"allow": ["Bash(git *)"]}, "customKey": True}
        settings_path.write_text(json.dumps(existing), encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")

        config = json.loads(settings_path.read_text(encoding="utf-8"))
        allow_list = config["permissions"]["allow"]
        assert "Bash(git *)" in allow_list
        assert "mcp__tapps-mcp" in allow_list
        assert config["customKey"] is True


# ---------------------------------------------------------------------------
# Tests: Dry run
# ---------------------------------------------------------------------------


class TestUpgradeDryRun:
    """Verify dry-run reports all artifact types without writing."""

    def test_dry_run_reports_all_claude_components(self, tmp_path: Path) -> None:
        """Dry run includes all Claude component types in the result."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        assert result["dry_run"] is True

        platforms = result["components"]["platforms"]
        assert len(platforms) > 0
        components = platforms[0]["components"]

        # All Epic 33 artifact types reported
        assert "skills" in components
        assert "agents" in components
        assert "python_quality_rule" in components
        assert "settings" in components

    def test_dry_run_does_not_write_skills(self, tmp_path: Path) -> None:
        """Dry run does not create skill files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        skills_dir = tmp_path / ".claude" / "skills"
        assert not skills_dir.exists()


# ---------------------------------------------------------------------------
# Tests: Idempotency
# ---------------------------------------------------------------------------


class TestUpgradeIdempotent:
    """Verify upgrade is idempotent - running twice produces same result."""

    def test_idempotent_skills(self, tmp_path: Path) -> None:
        """Running upgrade twice produces identical skill files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")
        skills_dir = tmp_path / ".claude" / "skills"
        first_contents: dict[str, str] = {}
        for skill_dir in skills_dir.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                first_contents[skill_dir.name] = skill_file.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        for skill_dir in skills_dir.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                assert skill_file.read_text(encoding="utf-8") == first_contents[skill_dir.name]

    def test_idempotent_agents(self, tmp_path: Path) -> None:
        """Running upgrade twice produces identical agent files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")
        agents_dir = tmp_path / ".claude" / "agents"
        first_contents: dict[str, str] = {}
        for agent_file in agents_dir.iterdir():
            first_contents[agent_file.name] = agent_file.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        for agent_file in agents_dir.iterdir():
            assert agent_file.read_text(encoding="utf-8") == first_contents[agent_file.name]

    def test_idempotent_settings(self, tmp_path: Path) -> None:
        """Running upgrade twice produces identical settings.json."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")
        settings_path = tmp_path / ".claude" / "settings.json"
        first_content = settings_path.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        assert settings_path.read_text(encoding="utf-8") == first_content


# ---------------------------------------------------------------------------
# Tests: Full end-to-end flow
# ---------------------------------------------------------------------------


class TestUpgradeEndToEnd:
    """End-to-end: old artifacts are replaced with corrected ones."""

    def test_full_upgrade_flow_claude(self, tmp_path: Path) -> None:
        """Init with old-style artifacts -> upgrade fixes everything."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        # Create old-style artifacts
        skills_dir = tmp_path / ".claude" / "skills"
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        for skill_name in ["tapps-score", "tapps-gate", "tapps-validate"]:
            _create_old_style_skill(skills_dir, skill_name)
        for agent_name in ["tapps-reviewer.md", "tapps-researcher.md", "tapps-validator.md"]:
            _create_old_style_agent(agents_dir, agent_name)

        # Run upgrade
        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True

        # Verify skills corrected
        for skill_name in ["tapps-score", "tapps-gate", "tapps-validate"]:
            content = (skills_dir / skill_name / "SKILL.md").read_text(encoding="utf-8")
            assert "allowed-tools:" in content or "mcp_tools:" in content
            assert content.startswith("---\n") or content.startswith("*Engagement")

        # Verify agents corrected
        for agent_name in ["tapps-reviewer.md", "tapps-researcher.md", "tapps-validator.md"]:
            content = (agents_dir / agent_name).read_text(encoding="utf-8")
            assert "mcpServers:" in content
            assert "maxTurns:" in content

        # Verify python quality rule
        rule_path = tmp_path / ".claude" / "rules" / "python-quality.md"
        assert rule_path.exists()
        rule_content = rule_path.read_text(encoding="utf-8")
        assert "paths:" in rule_content

        # Verify settings.json permissions
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        config = json.loads(settings_path.read_text(encoding="utf-8"))
        allow_list = config.get("permissions", {}).get("allow", [])
        assert "mcp__tapps-mcp" in allow_list

    def test_cursor_upgrade_creates_agents_and_skills(self, tmp_path: Path) -> None:
        """Cursor platform upgrade creates agents and skills."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_cursor_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="cursor")
        assert result["success"] is True

        # Verify cursor agents exist
        agents_dir = tmp_path / ".cursor" / "agents"
        assert agents_dir.exists()
        assert any(agents_dir.iterdir())

        # Verify cursor skills exist
        skills_dir = tmp_path / ".cursor" / "skills"
        assert skills_dir.exists()
        assert any(skills_dir.iterdir())
