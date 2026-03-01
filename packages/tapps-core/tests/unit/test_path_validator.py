"""Tests for security.path_validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.common.exceptions import PathValidationError
from tapps_core.security.path_validator import PathValidator, assert_write_allowed


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "tests").mkdir()
    return tmp_path


@pytest.fixture
def validator(tmp_project: Path) -> PathValidator:
    return PathValidator(tmp_project)


class TestPathValidator:
    def test_validate_path_within_root(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        f = tmp_project / "src" / "main.py"
        result = validator.validate_path(f, must_exist=True)
        assert result == f.resolve()

    def test_validate_path_outside_root_raises(
        self, validator: PathValidator, tmp_path: Path
    ) -> None:
        outside = tmp_path.parent / "outside.py"
        outside.write_text("x")
        with pytest.raises(PathValidationError, match="outside project root"):
            validator.validate_path(outside, must_exist=False)

    def test_validate_path_not_found_raises(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            validator.validate_path(tmp_project / "missing.py", must_exist=True)

    def test_validate_path_not_found_ok_when_not_required(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        result = validator.validate_path(tmp_project / "new.py", must_exist=False)
        assert result == (tmp_project / "new.py").resolve()

    def test_validate_path_too_large(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        big = tmp_project / "big.bin"
        big.write_bytes(b"x" * 100)
        with pytest.raises(PathValidationError, match="too large"):
            validator.validate_path(big, must_exist=True, max_file_size=50)

    def test_validate_path_size_ok_when_disabled(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        big = tmp_project / "big.bin"
        big.write_bytes(b"x" * 100)
        result = validator.validate_path(big, must_exist=True, max_file_size=None)
        assert result == big.resolve()

    def test_validate_read_path(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        f = tmp_project / "src" / "main.py"
        assert validator.validate_read_path(f) == f.resolve()

    def test_validate_write_path(
        self, validator: PathValidator, tmp_project: Path
    ) -> None:
        f = tmp_project / "output.txt"
        assert validator.validate_write_path(f) == f.resolve()

    def test_url_encoded_traversal_rejected(self, validator: PathValidator) -> None:
        with pytest.raises(PathValidationError, match="Suspicious"):
            validator.validate_path("%2e%2e/etc/passwd", must_exist=False)

    def test_null_byte_rejected(self, validator: PathValidator) -> None:
        with pytest.raises(PathValidationError, match="Null byte"):
            validator.validate_path("file\x00.py", must_exist=False)


class TestAssertWriteAllowed:
    def test_write_within_root(self, tmp_project: Path) -> None:
        assert_write_allowed(tmp_project / "src" / "new.py", tmp_project)

    def test_write_outside_root_raises(self, tmp_project: Path) -> None:
        with pytest.raises(PathValidationError):
            assert_write_allowed(tmp_project.parent / "hack.py", tmp_project)

    def test_write_with_allowed_prefix(self, tmp_project: Path) -> None:
        assert_write_allowed(
            tmp_project / "src" / "new.py", tmp_project, allowed_prefixes=["src", "tests"]
        )

    def test_write_with_disallowed_prefix(self, tmp_project: Path) -> None:
        with pytest.raises(PathValidationError, match="not under an allowed prefix"):
            assert_write_allowed(
                tmp_project / "docs" / "new.md", tmp_project, allowed_prefixes=["src", "tests"]
            )
