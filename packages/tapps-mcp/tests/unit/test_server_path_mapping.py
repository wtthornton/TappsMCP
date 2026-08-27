"""Tests for host path mapping in server._validate_file_path."""

from unittest.mock import patch

import pytest

from tapps_mcp.common.exceptions import PathValidationError
from tapps_mcp.config.settings import TappsMCPSettings
from tapps_mcp.server import _normalize_path_for_mapping, _validate_file_path


class TestNormalizePathForMapping:
    def test_forward_slashes_unchanged(self):
        assert _normalize_path_for_mapping("a/b/c") == "a/b/c"

    def test_backslashes_to_forward(self):
        assert _normalize_path_for_mapping("a\\b\\c") == "a/b/c"

    def test_windows_drive_lowercased(self):
        assert _normalize_path_for_mapping("C:\\projects\\myapp") == "c:/projects/myapp"
        assert _normalize_path_for_mapping("D:/foo") == "d:/foo"

    def test_trailing_slash_stripped(self):
        assert _normalize_path_for_mapping("C:/projects/myapp/") == "c:/projects/myapp"

    def test_strip_whitespace(self):
        assert _normalize_path_for_mapping("  a/b  ") == "a/b"

    def test_empty_becomes_slash(self):
        assert _normalize_path_for_mapping("") == "/"
        assert _normalize_path_for_mapping("/") == "/"


class TestValidateFilePathHostMapping:
    """When host_project_root is set, absolute host paths are mapped to project_root."""

    @patch("tapps_mcp.server.load_settings")
    def test_host_path_mapped_to_relative(self, mock_load_settings, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")
        host_root = str(tmp_path).replace("\\", "\\")  # keep as-is for Windows

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=tmp_path,
            host_project_root=host_root,
        )

        # Client sends absolute host path; server should map to project_root/src/main.py
        result = _validate_file_path(str(tmp_path / "src" / "main.py"))
        assert result == (tmp_path / "src" / "main.py").resolve()
        assert result.exists()

    @patch("tapps_mcp.server.load_settings")
    def test_windows_style_host_path_mapped(self, mock_load_settings, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")
        # Simulate Windows path from client (use backslashes)
        host_root = str(tmp_path).replace("/", "\\") if "/" in str(tmp_path) else str(tmp_path)

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=tmp_path,
            host_project_root=host_root,
        )

        # Send path with backslashes (Windows style)
        input_path = (tmp_path / "src" / "main.py").as_posix().replace("/", "\\")
        result = _validate_file_path(input_path)
        assert result == (tmp_path / "src" / "main.py").resolve()

    @patch("tapps_mcp.server.load_settings")
    def test_relative_path_unchanged_when_host_root_set(self, mock_load_settings, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=tmp_path,
            host_project_root=str(tmp_path),
        )

        result = _validate_file_path("src/main.py")
        assert result == (tmp_path / "src" / "main.py").resolve()

    @patch("tapps_mcp.server.load_settings")
    def test_path_outside_project_root_fails(self, mock_load_settings, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")
        outside = tmp_path.parent / "outside_project"
        outside.mkdir(exist_ok=True)
        (outside / "file.py").write_text("z = 3\n")

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=tmp_path,
            host_project_root=str(tmp_path),
        )

        # Path outside project_root should still fail even with host mapping
        with pytest.raises(PathValidationError):
            _validate_file_path(str(outside / "file.py"))


class TestValidateFilePathHostRootIsAncestor:
    """TAP-6494 (VAL-14): host_project_root as a shared multi-repo ancestor
    of project_root, not a 1:1 alias of it — the real layout on a machine
    where many checkouts live under one parent directory."""

    @patch("tapps_mcp.server.load_settings")
    def test_absolute_in_root_path_resolves_regardless_of_ancestor_host_root(
        self, mock_load_settings, tmp_path
    ):
        parent = tmp_path
        project_root = parent / "tapps-mcp-clone"
        project_root.mkdir()
        (project_root / "foo.py").write_text("x = 1\n")

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=project_root,
            host_project_root=str(parent),
        )

        result = _validate_file_path(str(project_root / "foo.py"))
        assert result == (project_root / "foo.py").resolve()

    @patch("tapps_mcp.server.load_settings")
    def test_sibling_repo_under_shared_ancestor_refused_as_outside_not_not_found(
        self, mock_load_settings, tmp_path
    ):
        parent = tmp_path
        project_root = parent / "tapps-mcp-clone"
        project_root.mkdir()
        sibling = parent / "HomeIQ"
        sibling.mkdir()
        target = sibling / "config.yaml"
        target.write_text("x: 1\n")

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=project_root,
            host_project_root=str(parent),
        )

        with pytest.raises(PathValidationError) as exc_info:
            _validate_file_path(str(target))

        # Must be the honest "outside project root" refusal quoting the
        # caller's own path, never a FileNotFoundError over a guessed one.
        assert "outside project root" in str(exc_info.value)
        assert str(target) in str(exc_info.value)

    @patch("tapps_mcp.server.load_settings")
    def test_relative_suffix_under_ancestor_maps_into_project_root(
        self, mock_load_settings, tmp_path
    ):
        parent = tmp_path
        project_root = parent / "tapps-mcp-clone"
        (project_root / "src").mkdir(parents=True)
        (project_root / "src" / "main.py").write_text("x = 1\n")

        mock_load_settings.return_value = TappsMCPSettings(
            project_root=project_root,
            host_project_root=str(parent),
        )

        # A host-side path naming this same project (parent/tapps-mcp-clone/...)
        # still maps correctly even though host_project_root is the ancestor.
        result = _validate_file_path(str(project_root / "src" / "main.py"))
        assert result == (project_root / "src" / "main.py").resolve()
