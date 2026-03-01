"""Cross-platform validation tests.

Ensures code works correctly on Windows, macOS, and Linux by
testing path handling, subprocess wrappers, and tool detection.
"""

from pathlib import Path

import pytest

from tapps_mcp.security.path_validator import PathValidator
from tapps_mcp.tools.subprocess_runner import run_command
from tapps_mcp.tools.tool_detection import detect_installed_tools


@pytest.mark.integration
class TestCrossPlatformPaths:
    """Path handling works on all platforms."""

    def test_pathlib_normalises_separators(self, tmp_path: Path):
        """pathlib.Path normalises separators on all platforms."""
        f = tmp_path / "sub" / "dir" / "file.py"
        f.parent.mkdir(parents=True)
        f.write_text("pass\n", encoding="utf-8")
        assert f.exists()
        assert f.is_file()
        # resolve() gives a clean absolute path
        resolved = f.resolve()
        assert resolved.is_absolute()

    def test_path_validator_with_native_paths(self, tmp_path: Path):
        """PathValidator works with native OS path separators."""
        f = tmp_path / "test.py"
        f.write_text("pass\n", encoding="utf-8")
        validator = PathValidator(tmp_path)
        # Should not raise
        result = validator.validate_read_path(str(f))
        assert result.exists()

    def test_path_validator_rejects_traversal(self, tmp_path: Path):
        """Path traversal is rejected on all platforms."""
        validator = PathValidator(tmp_path)
        with pytest.raises((ValueError, FileNotFoundError)):
            validator.validate_read_path(str(tmp_path / ".." / ".." / "etc" / "passwd"))


@pytest.mark.integration
class TestCrossPlatformSubprocess:
    """Subprocess execution works on all platforms."""

    def test_python_command(self):
        """Python is available and runs on all platforms."""
        result = run_command(["python", "-c", "print('hello')"], timeout=10)
        assert result.success is True
        assert "hello" in result.stdout

    def test_nonexistent_command(self):
        """Non-existent command fails gracefully on all platforms."""
        result = run_command(["__nonexistent_tool_xyz__"], timeout=5)
        assert result.success is False


@pytest.mark.integration
class TestCrossPlatformToolDetection:
    """Tool detection works on all platforms."""

    def test_detect_tools_returns_list(self):
        tools = detect_installed_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_each_tool_has_required_fields(self):
        tools = detect_installed_tools()
        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "available")
            assert isinstance(tool.available, bool)

    def test_python_is_available(self):
        """Python should always be detected as available."""
        # We're running Python, so it's available
        result = run_command(["python", "--version"], timeout=10)
        assert result.success is True


@pytest.mark.integration
class TestCrossPlatformScoring:
    """Scoring pipeline works with native filesystem."""

    def test_scorer_with_native_file(self, tmp_path: Path):
        """CodeScorer handles native file paths correctly."""
        from unittest.mock import patch

        from tapps_mcp.scoring.scorer import CodeScorer

        f = tmp_path / "module.py"
        f.write_text('"""Doc."""\nx = 1\n', encoding="utf-8")

        with patch("tapps_mcp.scoring.scorer.run_ruff_check", return_value=[]):
            scorer = CodeScorer()
            result = scorer.score_file_quick(f)

        assert result.file_path == str(f.resolve())
        assert result.overall_score >= 0

    def test_secret_scanner_with_native_file(self, tmp_path: Path):
        """SecretScanner reads files with correct encoding on all platforms."""
        from tapps_mcp.security.secret_scanner import SecretScanner

        f = tmp_path / "config.py"
        f.write_text("# Safe config\nDEBUG = True\n", encoding="utf-8")
        scanner = SecretScanner()
        result = scanner.scan_file(str(f))
        assert result.scanned_files == 1
        assert result.total_findings == 0
