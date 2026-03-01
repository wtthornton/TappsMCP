"""Tests for knowledge base validator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_core.experts.knowledge_validator import KnowledgeBaseValidator

if TYPE_CHECKING:
    from pathlib import Path


class TestKnowledgeBaseValidator:
    def _write_file(self, tmp_path: Path, name: str, content: str) -> Path:
        kd = tmp_path / "knowledge"
        kd.mkdir(exist_ok=True)
        fp = kd / name
        fp.write_text(content, encoding="utf-8")
        return kd

    def test_valid_file_passes(self, tmp_path: Path):
        kd = self._write_file(
            tmp_path,
            "good.md",
            "# Good File\n\n## Section\n\nSome content.\n",
        )
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert len(results) == 1
        assert results[0].is_valid is True
        assert results[0].has_headers is True

    def test_unclosed_code_block_error(self, tmp_path: Path):
        kd = self._write_file(
            tmp_path,
            "bad.md",
            "# Title\n\n```python\nprint('hello')\n",
        )
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert not results[0].is_valid
        assert any(i.rule == "code_block_closed" for i in results[0].issues)

    def test_python_syntax_error_in_code_block(self, tmp_path: Path):
        kd = self._write_file(
            tmp_path,
            "syntax.md",
            "# Title\n\n```python\ndef foo(\n```\n",
        )
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert any(i.rule == "python_syntax" for i in results[0].issues)

    def test_missing_title_info(self, tmp_path: Path):
        kd = self._write_file(
            tmp_path,
            "notitle.md",
            "## Subsection\n\nNo H1 title.\n",
        )
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert any(i.rule == "has_title" for i in results[0].issues)

    def test_header_hierarchy_skip_warning(self, tmp_path: Path):
        kd = self._write_file(
            tmp_path,
            "skip.md",
            "# Title\n\n### Skip H2\n\nContent.\n",
        )
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert any(i.rule == "header_hierarchy" for i in results[0].issues)

    def test_broken_cross_reference(self, tmp_path: Path):
        kd = self._write_file(
            tmp_path,
            "xref.md",
            "# Title\n\nSee [other](nonexistent.md) for details.\n",
        )
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert any(i.rule == "cross_reference" for i in results[0].issues)

    def test_get_summary_format(self, tmp_path: Path):
        kd = self._write_file(tmp_path, "a.md", "# Title\n\nContent.\n")
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        summary = KnowledgeBaseValidator.get_summary(results)
        assert "total_files" in summary
        assert "valid_files" in summary
        assert "errors" in summary

    def test_empty_dir(self, tmp_path: Path):
        kd = tmp_path / "empty"
        kd.mkdir()
        validator = KnowledgeBaseValidator(kd)
        results = validator.validate_all()
        assert results == []
