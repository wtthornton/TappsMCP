"""Tests for Cursor BugBot Rules generation (Story 12.14).

Verifies that generate_bugbot_rules creates .cursor/BUGBOT.md
with the correct quality standards and security requirements.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_generators import generate_bugbot_rules


class TestFileCreation:
    """Tests for file creation and structure."""

    def test_creates_file(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        target = tmp_path / ".cursor" / "BUGBOT.md"
        assert target.exists()

    def test_creates_cursor_dir(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        assert (tmp_path / ".cursor").is_dir()

    def test_result_dict(self, tmp_path):
        result = generate_bugbot_rules(tmp_path)
        assert result["action"] == "created"
        assert "BUGBOT.md" in result["file"]


class TestContent:
    """Tests for file content sections."""

    def test_has_quality_standards_section(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "Code Quality Standards" in content

    def test_has_security_requirements(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "Security Requirements" in content

    def test_has_hardcoded_secrets(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "Hardcoded" in content or "hardcoded" in content

    def test_has_testing_requirements(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "Testing Requirements" in content

    def test_has_cyclomatic_complexity(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "cyclomatic complexity" in content

    def test_has_eval_or_exec(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "eval()" in content or "exec()" in content

    def test_references_scoring_categories(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        # Check for all 7 scoring categories
        assert "Correctness" in content
        assert "Security" in content
        assert "Maintainability" in content
        assert "Performance" in content
        assert "Documentation" in content
        assert "Testing" in content
        assert "Style" in content

    def test_has_style_rules(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert "Python Style Rules" in content


class TestIdempotency:
    """Tests for idempotent behavior."""

    def test_idempotent_overwrite(self, tmp_path):
        generate_bugbot_rules(tmp_path)
        content1 = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        generate_bugbot_rules(tmp_path)
        content2 = (tmp_path / ".cursor" / "BUGBOT.md").read_text()
        assert content1 == content2
