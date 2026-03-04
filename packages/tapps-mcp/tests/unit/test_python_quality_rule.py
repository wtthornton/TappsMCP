"""Tests for path-scoped Python quality rule generation (Epic 33.3).

Verifies that ``generate_python_quality_rule`` and
``generate_claude_python_quality_rule`` produce correct content with
``paths:`` YAML frontmatter scoped to ``**/*.py``, and that engagement
level variants produce the expected language.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_mcp.pipeline.platform_generators import (
    generate_claude_python_quality_rule,
    generate_python_quality_rule,
)


def _parse_frontmatter(content: str) -> dict:
    """Extract and parse YAML frontmatter from rule content."""
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


# ---------------------------------------------------------------------------
# Rule content tests
# ---------------------------------------------------------------------------


class TestPythonQualityRuleFrontmatter:
    """Verify paths: frontmatter is correct at all engagement levels."""

    def test_medium_has_paths_frontmatter(self) -> None:
        content = generate_python_quality_rule("medium")
        fm = _parse_frontmatter(content)
        assert fm["paths"] == ["**/*.py"]

    def test_high_has_paths_frontmatter(self) -> None:
        content = generate_python_quality_rule("high")
        fm = _parse_frontmatter(content)
        assert fm["paths"] == ["**/*.py"]

    def test_low_has_paths_frontmatter(self) -> None:
        content = generate_python_quality_rule("low")
        fm = _parse_frontmatter(content)
        assert fm["paths"] == ["**/*.py"]

    def test_default_is_medium(self) -> None:
        default_content = generate_python_quality_rule()
        medium_content = generate_python_quality_rule("medium")
        assert default_content == medium_content

    def test_unknown_level_falls_back_to_medium(self) -> None:
        content = generate_python_quality_rule("nonexistent")
        medium = generate_python_quality_rule("medium")
        assert content == medium


class TestEngagementLevelVariants:
    """Verify engagement level language differences."""

    def test_high_uses_required_language(self) -> None:
        content = generate_python_quality_rule("high")
        assert "REQUIRED:" in content
        assert "Do NOT" in content

    def test_high_references_quick_check(self) -> None:
        content = generate_python_quality_rule("high")
        assert "tapps_quick_check" in content

    def test_high_references_validate_changed(self) -> None:
        content = generate_python_quality_rule("high")
        assert "tapps_validate_changed" in content

    def test_medium_uses_should_language(self) -> None:
        content = generate_python_quality_rule("medium")
        assert "REQUIRED:" not in content
        assert "Do NOT" not in content
        assert "Consider" not in content

    def test_medium_references_quick_check(self) -> None:
        content = generate_python_quality_rule("medium")
        assert "tapps_quick_check" in content

    def test_medium_references_validate_changed(self) -> None:
        content = generate_python_quality_rule("medium")
        assert "tapps_validate_changed" in content

    def test_medium_references_research(self) -> None:
        content = generate_python_quality_rule("medium")
        assert "tapps_research" in content

    def test_low_uses_consider_language(self) -> None:
        content = generate_python_quality_rule("low")
        assert "Consider" in content

    def test_low_no_required_language(self) -> None:
        content = generate_python_quality_rule("low")
        assert "REQUIRED:" not in content
        assert "Do NOT" not in content

    def test_all_levels_have_heading(self) -> None:
        for level in ("high", "medium", "low"):
            content = generate_python_quality_rule(level)
            assert "# Python Quality Rules (TappsMCP)" in content

    def test_all_levels_have_scoring_categories(self) -> None:
        for level in ("high", "medium", "low"):
            content = generate_python_quality_rule(level)
            assert "Complexity" in content
            assert "Security" in content
            assert "Maintainability" in content


# ---------------------------------------------------------------------------
# File generation tests
# ---------------------------------------------------------------------------


class TestGenerateClaudePythonQualityRule:
    """Verify file generation creates the correct file."""

    def test_creates_rule_file(self, tmp_path: Path) -> None:
        generate_claude_python_quality_rule(tmp_path)
        target = tmp_path / ".claude" / "rules" / "python-quality.md"
        assert target.exists()

    def test_creates_rules_directory(self, tmp_path: Path) -> None:
        generate_claude_python_quality_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules").is_dir()

    def test_returns_created_action(self, tmp_path: Path) -> None:
        result = generate_claude_python_quality_rule(tmp_path)
        assert result["action"] == "created"

    def test_returns_updated_on_overwrite(self, tmp_path: Path) -> None:
        generate_claude_python_quality_rule(tmp_path)
        result = generate_claude_python_quality_rule(tmp_path)
        assert result["action"] == "updated"

    def test_file_content_matches_engagement_level(self, tmp_path: Path) -> None:
        generate_claude_python_quality_rule(tmp_path, engagement_level="high")
        content = (tmp_path / ".claude" / "rules" / "python-quality.md").read_text()
        assert "REQUIRED:" in content

    def test_result_contains_file_path(self, tmp_path: Path) -> None:
        result = generate_claude_python_quality_rule(tmp_path)
        assert "file" in result
        assert "python-quality.md" in result["file"]


# ---------------------------------------------------------------------------
# Init integration test
# ---------------------------------------------------------------------------


class TestInitIntegration:
    """Verify tapps_init generates the Python quality rule file."""

    def test_init_generates_python_quality_rule(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "python_quality_rule" in result
        rule_result = result["python_quality_rule"]
        assert rule_result["action"] == "created"
        target = tmp_path / ".claude" / "rules" / "python-quality.md"
        assert target.exists()
        # Setup/Update/Daily workflow doc is always created when not dry_run
        assert "workflow_doc" in result
        assert result["workflow_doc"]["action"] in ("created", "updated")
        assert (tmp_path / "docs" / "TAPPS_WORKFLOW.md").exists()


# ---------------------------------------------------------------------------
# Upgrade integration test
# ---------------------------------------------------------------------------


class TestUpgradeIntegration:
    """Verify tapps_upgrade regenerates the Python quality rule file."""

    def test_upgrade_regenerates_rule(self, tmp_path: Path) -> None:
        # Simulate existing Claude Code project
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "python_quality_rule" in claude_result["components"]
        rule_result = claude_result["components"]["python_quality_rule"]
        assert rule_result["action"] == "created"

    def test_upgrade_dry_run_reports_rule(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert claude_result["components"]["python_quality_rule"] == "would-regenerate"
