"""Tests for Cursor rule types enhancement (Story 12.11).

Verifies that generate_cursor_rules() creates three distinct .mdc rule files
with different rule types: alwaysApply, autoAttach (globs), and agentRequested
(description).
"""

from __future__ import annotations

import yaml

from tapps_mcp.pipeline.platform_generators import generate_cursor_rules


def _parse_frontmatter(content: str) -> dict:
    """Extract and parse YAML frontmatter from content."""
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


class TestRuleCreation:
    """Tests for rule file creation."""

    def test_creates_three_rules(self, tmp_path):
        generate_cursor_rules(tmp_path)
        rules_dir = tmp_path / ".cursor" / "rules"
        assert (rules_dir / "tapps-pipeline.mdc").exists()
        assert (rules_dir / "tapps-python-quality.mdc").exists()
        assert (rules_dir / "tapps-expert-consultation.mdc").exists()

    def test_creates_rules_dir(self, tmp_path):
        generate_cursor_rules(tmp_path)
        assert (tmp_path / ".cursor" / "rules").is_dir()

    def test_result_dict(self, tmp_path):
        result = generate_cursor_rules(tmp_path)
        assert len(result["created"]) == 3
        assert len(result["skipped"]) == 0


class TestPipelineRule:
    """Tests for tapps-pipeline.mdc (alwaysApply rule)."""

    def test_always_apply_true(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert fm["alwaysApply"] is True

    def test_no_globs(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert "globs" not in fm

    def test_no_description(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert "description" not in fm

    def test_body_references_session_start(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").read_text()
        assert "tapps_session_start" in content


class TestPythonQualityRule:
    """Tests for tapps-python-quality.mdc (autoAttach rule)."""

    def test_globs_star_py(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-python-quality.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert fm["globs"] == "*.py"

    def test_always_apply_false(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-python-quality.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert fm["alwaysApply"] is False

    def test_no_description(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-python-quality.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert "description" not in fm

    def test_body_references_quick_check(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-python-quality.mdc").read_text()
        assert "tapps_quick_check" in content


class TestExpertConsultationRule:
    """Tests for tapps-expert-consultation.mdc (agentRequested rule)."""

    def test_has_description(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-expert-consultation.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert "description" in fm
        assert isinstance(fm["description"], str)
        assert len(fm["description"]) > 0

    def test_no_globs(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-expert-consultation.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert "globs" not in fm

    def test_no_always_apply(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-expert-consultation.mdc").read_text()
        fm = _parse_frontmatter(content)
        assert "alwaysApply" not in fm

    def test_body_references_consult_expert(self, tmp_path):
        generate_cursor_rules(tmp_path)
        content = (tmp_path / ".cursor" / "rules" / "tapps-expert-consultation.mdc").read_text()
        assert "tapps_consult_expert" in content


class TestSkipExisting:
    """Tests for skip-on-exists behavior."""

    def test_skips_existing_rule(self, tmp_path):
        rules_dir = tmp_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        custom = "# My custom rule\n"
        (rules_dir / "tapps-pipeline.mdc").write_text(custom)

        result = generate_cursor_rules(tmp_path)

        assert "tapps-pipeline.mdc" in result["skipped"]
        assert (rules_dir / "tapps-pipeline.mdc").read_text() == custom
        # Other rules should still be created
        assert (rules_dir / "tapps-python-quality.mdc").exists()
        assert (rules_dir / "tapps-expert-consultation.mdc").exists()
