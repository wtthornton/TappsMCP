"""Tests for version marker helpers and marker-aware Markdown generators.

Epic 67, Story 67.3: Version Markers for Generated Markdown Artifacts.
"""

from __future__ import annotations

from pathlib import Path


class TestCheckVersionMarker:
    """Tests for _check_version_marker helper."""

    def test_extracts_version_from_first_line(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_generators import _check_version_marker

        target = tmp_path / "test.md"
        target.write_text("<!-- tapps-generated: v1.2.3 -->\n# Hello\n", encoding="utf-8")
        assert _check_version_marker(target) == "1.2.3"

    def test_extracts_version_from_later_line(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_generators import _check_version_marker

        target = tmp_path / "test.md"
        lines = "line1\nline2\n<!-- tapps-generated: v0.8.5 -->\nline4\n"
        target.write_text(lines, encoding="utf-8")
        assert _check_version_marker(target) == "0.8.5"

    def test_returns_none_for_unmarked_file(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_generators import _check_version_marker

        target = tmp_path / "test.md"
        target.write_text("# No marker here\nJust text.\n", encoding="utf-8")
        assert _check_version_marker(target) is None

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_generators import _check_version_marker

        target = tmp_path / "nonexistent.md"
        assert _check_version_marker(target) is None

    def test_ignores_marker_beyond_scan_limit(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_generators import _check_version_marker

        target = tmp_path / "test.md"
        lines = "\n".join([f"line {i}" for i in range(10)])
        lines += "\n<!-- tapps-generated: v1.0.0 -->\n"
        target.write_text(lines, encoding="utf-8")
        assert _check_version_marker(target) is None

    def test_handles_extra_whitespace_in_marker(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_generators import _check_version_marker

        target = tmp_path / "test.md"
        target.write_text("<!--  tapps-generated:  v2.0.0  -->\n", encoding="utf-8")
        assert _check_version_marker(target) == "2.0.0"


class TestAddVersionMarker:
    """Tests for _add_version_marker helper."""

    def test_prepends_marker(self) -> None:
        from tapps_mcp.pipeline.platform_generators import _add_version_marker

        result = _add_version_marker("# Hello\nWorld")
        assert result.startswith("<!-- tapps-generated: v")
        assert "-->\n# Hello\nWorld" in result

    def test_marker_contains_current_version(self) -> None:
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.platform_generators import _add_version_marker

        result = _add_version_marker("content")
        assert f"v{__version__}" in result

    def test_roundtrip_with_check(self, tmp_path: Path) -> None:
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.platform_generators import (
            _add_version_marker,
            _check_version_marker,
        )

        target = tmp_path / "test.md"
        target.write_text(_add_version_marker("# Doc\n"), encoding="utf-8")
        assert _check_version_marker(target) == __version__


class TestPRTemplateVersionMarker:
    """Tests for version marker integration in generate_pr_template."""

    def test_new_file_returns_created(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        result = generate_pr_template(tmp_path)
        assert result["action"] == "created"

    def test_new_file_has_marker(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        content = (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
        assert "<!-- tapps-generated: v" in content

    def test_current_version_returns_up_to_date(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        generate_pr_template(tmp_path)
        result = generate_pr_template(tmp_path)
        assert result["action"] == "up-to-date"

    def test_stale_version_returns_updated(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_templates import generate_pr_template

        # Create with a stale version
        github_dir = tmp_path / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        target = github_dir / "PULL_REQUEST_TEMPLATE.md"
        target.write_text("<!-- tapps-generated: v0.0.1 -->\n# Old\n", encoding="utf-8")

        result = generate_pr_template(tmp_path)
        assert result["action"] == "updated"


class TestAgentProfilesVersionMarker:
    """Tests for version marker integration in generate_agent_profiles."""

    def test_new_files_return_created(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        result = generate_agent_profiles(tmp_path)
        assert result["action"] == "created"
        assert result["count"] == 2

    def test_new_files_have_marker(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        content = (tmp_path / ".github" / "agents" / "tapps-quality.md").read_text()
        assert "<!-- tapps-generated: v" in content

    def test_current_version_returns_up_to_date(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        generate_agent_profiles(tmp_path)
        result = generate_agent_profiles(tmp_path)
        assert result["action"] == "up-to-date"
        assert result["count"] == 0

    def test_stale_version_updates(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_agent_profiles

        # Create with stale version
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        for name in ("tapps-quality.md", "tapps-researcher.md"):
            (agents_dir / name).write_text(
                "<!-- tapps-generated: v0.0.1 -->\n# Old\n", encoding="utf-8"
            )

        result = generate_agent_profiles(tmp_path)
        assert result["action"] == "created"
        assert result["count"] == 2


class TestPathScopedInstructionsVersionMarker:
    """Tests for version marker integration in generate_path_scoped_instructions."""

    def test_new_files_return_created(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        result = generate_path_scoped_instructions(tmp_path)
        assert result["action"] == "created"
        assert result["count"] == 3

    def test_current_version_returns_up_to_date(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_path_scoped_instructions

        generate_path_scoped_instructions(tmp_path)
        result = generate_path_scoped_instructions(tmp_path)
        assert result["action"] == "up-to-date"
        assert result["count"] == 0


class TestEnhancedCopilotInstructionsVersionMarker:
    """Tests for version marker integration in generate_enhanced_copilot_instructions."""

    def test_new_file_returns_created(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        result = generate_enhanced_copilot_instructions(tmp_path)
        assert result["action"] == "created"

    def test_current_version_returns_up_to_date(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        generate_enhanced_copilot_instructions(tmp_path)
        result = generate_enhanced_copilot_instructions(tmp_path)
        assert result["action"] == "up-to-date"

    def test_stale_version_returns_updated(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_copilot import generate_enhanced_copilot_instructions

        github_dir = tmp_path / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        target = github_dir / "copilot-instructions.md"
        target.write_text("<!-- tapps-generated: v0.0.1 -->\n# Old\n", encoding="utf-8")

        result = generate_enhanced_copilot_instructions(tmp_path)
        assert result["action"] == "updated"


class TestSecurityPolicyVersionMarker:
    """Tests for version marker integration in generate_security_policy."""

    def test_new_file_returns_created(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        result = generate_security_policy(tmp_path)
        assert result["action"] == "created"

    def test_new_file_has_marker(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        generate_security_policy(tmp_path)
        content = (tmp_path / "SECURITY.md").read_text()
        assert "<!-- tapps-generated: v" in content

    def test_current_version_returns_up_to_date(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        generate_security_policy(tmp_path)
        result = generate_security_policy(tmp_path)
        assert result["action"] == "up-to-date"

    def test_user_created_file_skipped(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        # User-created file without marker should not be overwritten
        target = tmp_path / "SECURITY.md"
        target.write_text("# My custom security policy\n", encoding="utf-8")
        result = generate_security_policy(tmp_path)
        assert result["action"] == "skipped"

    def test_stale_version_returns_updated(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_security_policy

        target = tmp_path / "SECURITY.md"
        target.write_text("<!-- tapps-generated: v0.0.1 -->\n# Old\n", encoding="utf-8")
        result = generate_security_policy(tmp_path)
        assert result["action"] == "updated"


class TestSetupGuideVersionMarker:
    """Tests for version marker integration in generate_setup_guide."""

    def test_new_file_returns_created(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        result = generate_setup_guide(tmp_path)
        assert result["action"] == "created"

    def test_current_version_returns_up_to_date(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        generate_setup_guide(tmp_path)
        result = generate_setup_guide(tmp_path)
        assert result["action"] == "up-to-date"

    def test_stale_version_returns_updated(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.github_governance import generate_setup_guide

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        target = docs_dir / "GITHUB_SETUP_GUIDE.md"
        target.write_text("<!-- tapps-generated: v0.0.1 -->\n# Old\n", encoding="utf-8")
        result = generate_setup_guide(tmp_path)
        assert result["action"] == "updated"
