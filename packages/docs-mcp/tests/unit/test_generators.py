"""Tests for docs_mcp MCP generation tools (server_gen_tools.py).

Covers the three MCP tool handlers:
- ``docs_generate_readme``
- ``docs_generate_changelog``
- ``docs_generate_release_notes``

Unit tests for the underlying generator classes live in their own files:
- ``test_readme_generator.py`` (ReadmeGenerator)
- ``test_smart_merge.py`` (SmartMerger)
- ``test_release_notes.py`` (ReleaseNotesGenerator)
- ``test_changelog.py`` (ChangelogGenerator)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from docs_mcp.generators.release_notes import ReleaseNotes
from tests.helpers import make_commit as _commit
from tests.helpers import make_settings as _make_settings
from tests.helpers import make_version as _version


# ---------------------------------------------------------------------------
# docs_generate_readme MCP tool tests
# ---------------------------------------------------------------------------


class TestDocsGenerateReadme:
    """Tests for the docs_generate_readme MCP tool handler."""

    async def test_generate_readme_standard(self, tmp_path: Path) -> None:
        """Generate a standard README for a Python project."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "test-proj"\nversion = "0.1.0"\n'
            'description = "Test project"\nlicense = "MIT"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="standard", project_root=str(root))

        assert result["success"] is True
        assert result["tool"] == "docs_generate_readme"
        assert "data" in result
        data = result["data"]
        assert data["style"] == "standard"
        assert data["content_length"] > 0
        assert "# test-proj" in data["content"]

    async def test_generate_readme_minimal(self, tmp_path: Path) -> None:
        """Minimal style generates a simpler README."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "mini"\nversion = "0.1.0"\n'
            'description = "Minimal"\nlicense = "MIT"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="minimal", project_root=str(root))

        assert result["success"] is True
        content = result["data"]["content"]
        assert "# mini" in content
        assert "## Installation" in content
        # Minimal should not have Features
        assert "## Features" not in content

    async def test_generate_readme_invalid_style(self, tmp_path: Path) -> None:
        """Invalid style returns an error response."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="nonexistent", project_root=str(root))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_STYLE"

    async def test_generate_readme_with_merge(self, tmp_path: Path) -> None:
        """When merge=True and README exists, SmartMerger is invoked."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "merge-test"\nversion = "1.0.0"\n'
            'description = "Merge test"\nlicense = "MIT"\n',
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            "# Old Title\n\n## Custom Section\n\nUser content here\n",
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="standard", merge=True, project_root=str(root))

        assert result["success"] is True
        data = result["data"]
        assert data["merged"] is True
        # User content should be preserved
        assert "User content here" in data["content"]

    async def test_generate_readme_no_merge(self, tmp_path: Path) -> None:
        """When merge=False, existing content is replaced entirely."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "no-merge"\nversion = "1.0.0"\n'
            'description = "No merge"\nlicense = "MIT"\n',
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            "# Old Title\n\n## Custom Section\n\nUser content\n",
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="minimal", merge=False, project_root=str(root))

        assert result["success"] is True
        data = result["data"]
        assert data["merged"] is False
        assert "# no-merge" in data["content"]

    async def test_generate_readme_response_envelope(self, tmp_path: Path) -> None:
        """Response has the standard success_response envelope."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "envelope-test"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="minimal", project_root=str(root))

        assert "tool" in result
        assert "success" in result
        assert "elapsed_ms" in result
        assert "data" in result
        assert result["elapsed_ms"] >= 0
        assert "next_steps" in result["data"]

    async def test_generate_readme_writes_file(self, tmp_path: Path) -> None:
        """Verify the tool writes the README file to disk."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "disk-write"\nversion = "1.0.0"\n'
            'description = "Test disk write"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_readme(style="minimal", project_root=str(root))

        assert result["success"] is True
        readme_path = root / "README.md"
        assert readme_path.exists()
        content = readme_path.read_text(encoding="utf-8")
        assert "# disk-write" in content


# ---------------------------------------------------------------------------
# docs_generate_changelog MCP tool tests
# ---------------------------------------------------------------------------


class TestDocsGenerateChangelog:
    """Tests for the docs_generate_changelog MCP tool handler."""

    async def test_invalid_format_returns_error(self, tmp_path: Path) -> None:
        """Invalid format parameter returns an error."""
        from docs_mcp.server_gen_tools import docs_generate_changelog

        result = await docs_generate_changelog(format="invalid-format", project_root=str(tmp_path))
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_FORMAT"

    async def test_nonexistent_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns an error."""
        from docs_mcp.server_gen_tools import docs_generate_changelog

        fake = tmp_path / "does_not_exist"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = await docs_generate_changelog(project_root=str(fake))
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_generate_changelog_success(self, tmp_path: Path) -> None:
        """Successful changelog generation with mocked version detector."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("1.0.0", "2026-01-15T00:00:00+00:00", [
                _commit("feat: initial release"),
            ]),
        ]

        from docs_mcp.server_gen_tools import docs_generate_changelog

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer.__init__",
                return_value=None,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer.get_commits",
                return_value=[],
            ),
        ):
            result = await docs_generate_changelog(project_root=str(root))

        assert result["success"] is True
        assert result["data"]["version_count"] == 1
        assert "# Changelog" in result["data"]["content"]

    async def test_generate_changelog_response_envelope(self, tmp_path: Path) -> None:
        """Response has correct structure."""
        root = tmp_path / "proj"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_changelog

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=[],
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer.__init__",
                return_value=None,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer.get_commits",
                return_value=[],
            ),
        ):
            result = await docs_generate_changelog(project_root=str(root))

        assert result["tool"] == "docs_generate_changelog"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "format" in result["data"]
        assert "content" in result["data"]

    async def test_generate_changelog_conventional_format(self, tmp_path: Path) -> None:
        """Conventional format works correctly."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("1.0.0", "2026-01-15T00:00:00+00:00", [
                _commit("feat: add feature"),
                _commit("fix: fix bug"),
            ]),
        ]

        from docs_mcp.server_gen_tools import docs_generate_changelog

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer.__init__",
                return_value=None,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer.get_commits",
                return_value=[],
            ),
        ):
            result = await docs_generate_changelog(format="conventional", project_root=str(root))

        assert result["success"] is True
        assert result["data"]["format"] == "conventional"
        assert "# Changelog" in result["data"]["content"]


# ---------------------------------------------------------------------------
# docs_generate_release_notes MCP tool tests
# ---------------------------------------------------------------------------


class TestDocsGenerateReleaseNotes:
    """Tests for the docs_generate_release_notes MCP tool handler."""

    async def test_nonexistent_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns an error."""
        from docs_mcp.server_gen_tools import docs_generate_release_notes

        fake = tmp_path / "no_such_dir"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = await docs_generate_release_notes(project_root=str(fake))
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_no_versions_returns_error(self, tmp_path: Path) -> None:
        """Error when no semver tags exist."""
        root = tmp_path / "proj"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_release_notes

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=[],
            ),
        ):
            result = await docs_generate_release_notes(project_root=str(root))

        assert result["success"] is False
        assert result["error"]["code"] == "NO_VERSIONS"

    async def test_version_not_found_returns_error(self, tmp_path: Path) -> None:
        """Error when requested version does not exist."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("1.0.0", "2026-01-15T00:00:00+00:00", [
                _commit("feat: initial"),
            ]),
        ]

        from docs_mcp.server_gen_tools import docs_generate_release_notes

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
        ):
            result = await docs_generate_release_notes(version="9.9.9", project_root=str(root))

        assert result["success"] is False
        assert result["error"]["code"] == "VERSION_NOT_FOUND"

    async def test_generate_release_notes_latest(self, tmp_path: Path) -> None:
        """Generate notes for the latest version (no version arg)."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("2.0.0", "2026-02-15T00:00:00+00:00", [
                _commit("feat: v2 feature"),
            ]),
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: v1 feature"),
            ]),
        ]

        from docs_mcp.server_gen_tools import docs_generate_release_notes

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
        ):
            result = await docs_generate_release_notes(project_root=str(root))

        assert result["success"] is True
        data = result["data"]
        assert data["version"] == "2.0.0"
        assert data["date"] == "2026-02-15"
        assert "v2 feature" in data["features"][0]
        assert "# Release 2.0.0" in data["markdown"]

    async def test_generate_release_notes_specific_version(self, tmp_path: Path) -> None:
        """Generate notes for a specific version."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("2.0.0", "2026-02-15T00:00:00+00:00", [
                _commit("feat: v2 feature"),
            ]),
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: v1 feature"),
                _commit("fix: v1 fix", author="Alice"),
            ]),
        ]

        from docs_mcp.server_gen_tools import docs_generate_release_notes

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
        ):
            result = await docs_generate_release_notes(version="1.0.0", project_root=str(root))

        assert result["success"] is True
        data = result["data"]
        assert data["version"] == "1.0.0"
        assert len(data["features"]) >= 1
        assert len(data["fixes"]) >= 1
        assert "Alice" in data["contributors"]

    async def test_generate_release_notes_response_envelope(self, tmp_path: Path) -> None:
        """Response has the standard success_response envelope."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("1.0.0", "2026-01-01T00:00:00+00:00", []),
        ]

        from docs_mcp.server_gen_tools import docs_generate_release_notes

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
        ):
            result = await docs_generate_release_notes(project_root=str(root))

        assert result["tool"] == "docs_generate_release_notes"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result
        assert "markdown" in result["data"]
        assert "highlights" in result["data"]
        assert "breaking_changes" in result["data"]

    async def test_generate_release_notes_breaking_in_highlights(self, tmp_path: Path) -> None:
        """Breaking changes appear in highlights."""
        root = tmp_path / "proj"
        root.mkdir()

        versions = [
            _version("2.0.0", "2026-02-01T00:00:00+00:00", [
                _commit("feat!: redesign API"),
                _commit("feat: new dashboard"),
            ]),
        ]

        from docs_mcp.server_gen_tools import docs_generate_release_notes

        with (
            patch(
                "docs_mcp.server_helpers._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.analyzers.version_detector.VersionDetector.detect_versions",
                return_value=versions,
            ),
        ):
            result = await docs_generate_release_notes(project_root=str(root))

        assert result["success"] is True
        data = result["data"]
        assert len(data["breaking_changes"]) == 1
        # Highlights should include BREAKING prefix
        assert any("BREAKING" in h for h in data["highlights"])
