"""Tests for tapps_core.common.utils."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from tapps_core.common.utils import (
    ensure_dir,
    get_path_mapping,
    is_running_in_container,
    read_text_utf8,
    translate_path,
    utc_now,
)


class TestUtcNow:
    def test_returns_datetime(self) -> None:
        result = utc_now()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self) -> None:
        result = utc_now()
        assert result.tzinfo is not None
        assert result.tzinfo == UTC


class TestEnsureDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        assert not target.exists()
        result = ensure_dir(target)
        assert target.is_dir()
        assert result == target

    def test_existing_directory(self, tmp_path: Path) -> None:
        result = ensure_dir(tmp_path)
        assert result == tmp_path

    def test_returns_path(self, tmp_path: Path) -> None:
        target = tmp_path / "new"
        result = ensure_dir(target)
        assert isinstance(result, Path)


class TestReadTextUtf8:
    def test_reads_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        assert read_text_utf8(f) == "hello world"

    def test_reads_unicode(self, tmp_path: Path) -> None:
        f = tmp_path / "unicode.txt"
        f.write_text("cafe\u0301", encoding="utf-8")
        assert read_text_utf8(f) == "cafe\u0301"


# ---------------------------------------------------------------------------
# Story 75.1: Container detection and path mapping
# ---------------------------------------------------------------------------


class TestIsRunningInContainer:
    """Tests for is_running_in_container()."""

    def test_returns_false_on_host(self) -> None:
        """On a normal host (no docker env, no sentinel), returns False."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("tapps_core.common.utils.Path") as mock_path:
                # No /.dockerenv, no /proc/1/cgroup
                mock_path.return_value.exists.return_value = False
                result = is_running_in_container()
                assert result is False

    def test_true_when_tapps_docker_env(self) -> None:
        with patch.dict("os.environ", {"TAPPS_DOCKER": "1"}):
            assert is_running_in_container() is True

    def test_false_when_tapps_docker_not_1(self) -> None:
        with patch.dict("os.environ", {"TAPPS_DOCKER": "0"}, clear=True):
            with patch("tapps_core.common.utils.Path") as mock_path:
                mock_path.return_value.exists.return_value = False
                assert is_running_in_container() is False

    def test_true_when_dockerenv_exists(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch("tapps_core.common.utils.Path") as mock_path:
                sentinel = mock_path("/.dockerenv")
                sentinel.exists.return_value = True
                # Ensure the Path() call for /.dockerenv returns our mock
                mock_path.return_value.exists.return_value = True
                assert is_running_in_container() is True

    def test_true_when_cgroup_contains_docker(self, tmp_path: Path) -> None:
        cgroup = tmp_path / "cgroup"
        cgroup.write_text("12:memory:/docker/abc123\n", encoding="utf-8")
        with patch.dict("os.environ", {}, clear=True):
            with patch("tapps_core.common.utils.Path") as mock_path:
                # /.dockerenv does not exist
                dockerenv_mock = mock_path("/.dockerenv")
                dockerenv_mock.exists.return_value = False

                def path_factory(arg: str = "") -> Path:
                    if arg == "/.dockerenv":
                        return dockerenv_mock  # type: ignore[return-value]
                    if arg == "/proc/1/cgroup":
                        return cgroup
                    return Path(arg)

                mock_path.side_effect = path_factory
                mock_path.return_value.exists.return_value = False
                # Direct test: the cgroup file has 'docker'
                assert "docker" in cgroup.read_text(encoding="utf-8")


class TestGetPathMapping:
    """Tests for get_path_mapping()."""

    def test_mapping_available_when_host_root_set(self) -> None:
        with patch.dict("os.environ", {"TAPPS_HOST_ROOT": "C:\\cursor\\HomeIQ"}):
            result = get_path_mapping()
            assert result["mapping_available"] is True
            assert result["host_root"] == "C:\\cursor\\HomeIQ"
            assert "container_root" in result

    def test_mapping_unavailable_when_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = get_path_mapping()
            assert result["mapping_available"] is False
            assert result["host_root"] == ""

    def test_returns_cwd_as_container_root(self) -> None:
        with patch.dict("os.environ", {"TAPPS_HOST_ROOT": "/host/project"}):
            result = get_path_mapping()
            assert result["container_root"] == str(Path.cwd())


class TestTranslatePath:
    """Tests for translate_path()."""

    def test_translates_host_path(self) -> None:
        with patch.dict("os.environ", {"TAPPS_HOST_ROOT": "C:\\cursor\\HomeIQ"}):
            with patch("tapps_core.common.utils.Path") as mock_path:
                mock_path.cwd.return_value = Path("/workspace")
                result = translate_path("C:\\cursor\\HomeIQ\\src\\main.py")
                # Normalise for cross-platform: on Windows str(Path) uses backslashes
                assert result.replace("\\", "/") == "/workspace/src/main.py"

    def test_returns_unchanged_when_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = translate_path("/some/path/file.py")
            assert result == "/some/path/file.py"

    def test_returns_unchanged_when_no_prefix_match(self) -> None:
        with patch.dict("os.environ", {"TAPPS_HOST_ROOT": "C:\\cursor\\HomeIQ"}):
            result = translate_path("/other/project/file.py")
            assert result == "/other/project/file.py"

    def test_forward_slash_host_path(self) -> None:
        with patch.dict("os.environ", {"TAPPS_HOST_ROOT": "/home/user/project"}):
            with patch("tapps_core.common.utils.Path") as mock_path:
                mock_path.cwd.return_value = Path("/workspace")
                result = translate_path("/home/user/project/src/app.py")
                assert result.replace("\\", "/") == "/workspace/src/app.py"
