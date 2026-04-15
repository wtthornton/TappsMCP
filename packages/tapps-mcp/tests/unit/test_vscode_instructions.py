"""Tests for VS Code / Copilot Instructions generation (Story 12.13).

Verifies that generate_copilot_instructions creates
.github/copilot-instructions.md with the correct content.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_generators import generate_copilot_instructions


class TestFileCreation:
    """Tests for file creation and structure."""

    def test_creates_file(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        target = tmp_path / ".github" / "copilot-instructions.md"
        assert target.exists()

    def test_creates_github_dir(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        assert (tmp_path / ".github").is_dir()

    def test_result_dict(self, tmp_path):
        result = generate_copilot_instructions(tmp_path)
        assert result["action"] == "created"
        assert "copilot-instructions.md" in result["file"]


class TestContent:
    """Tests for file content."""

    def test_has_heading(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "# TappsMCP Quality Tools" in content

    def test_has_session_start(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "tapps_session_start" in content

    def test_has_quick_check(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "tapps_quick_check" in content

    def test_has_quality_gate(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "tapps_quality_gate" in content

    def test_has_validate_changed(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "tapps_validate_changed" in content

    def test_has_lookup_docs(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "tapps_lookup_docs" in content

    def test_has_workflow_section(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert "## Workflow" in content

    def test_no_yaml_frontmatter(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert not content.startswith("---")

    def test_references_vscode_mcp_json(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert ".vscode/mcp.json" in content


class TestIdempotency:
    """Tests for idempotent behavior."""

    def test_idempotent_overwrite(self, tmp_path):
        generate_copilot_instructions(tmp_path)
        content1 = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        generate_copilot_instructions(tmp_path)
        content2 = (tmp_path / ".github" / "copilot-instructions.md").read_text()
        assert content1 == content2
