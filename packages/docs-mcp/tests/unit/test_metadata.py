"""Tests for docs_mcp.generators.metadata — project metadata extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.generators.metadata import MetadataExtractor, ProjectMetadata


@pytest.fixture
def extractor() -> MetadataExtractor:
    return MetadataExtractor()


# ---------------------------------------------------------------------------
# pyproject.toml (PEP 621)
# ---------------------------------------------------------------------------


class TestPyprojectParsing:
    """Tests for pyproject.toml metadata extraction."""

    def test_basic_fields(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\n'
            'name = "my-lib"\n'
            'version = "1.2.3"\n'
            'description = "A cool library"\n'
            'requires-python = ">=3.12"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.name == "my-lib"
        assert meta.version == "1.2.3"
        assert meta.description == "A cool library"
        assert meta.python_requires == ">=3.12"
        assert meta.source_file == "pyproject.toml"

    def test_author_extraction(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\n'
            'name = "test"\n'
            'version = "0.1.0"\n'
            '\n'
            '[[project.authors]]\n'
            'name = "Alice"\n'
            'email = "alice@example.com"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.author == "Alice"
        assert meta.author_email == "alice@example.com"

    def test_license_as_string(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nlicense = "MIT"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.license == "MIT"

    def test_license_as_table(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n\n[project.license]\ntext = "Apache-2.0"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.license == "Apache-2.0"

    def test_urls_extraction(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n\n'
            '[project.urls]\n'
            'Homepage = "https://example.com"\n'
            'Repository = "https://github.com/user/repo"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.homepage == "https://example.com"
        assert meta.repository == "https://github.com/user/repo"

    def test_dependencies_extraction(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\n'
            'name = "test"\n'
            'dependencies = ["click>=8.0", "pydantic>=2.0"]\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.dependencies == ["click>=8.0", "pydantic>=2.0"]

    def test_optional_dependencies(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\n'
            'name = "test"\n'
            '\n'
            '[project.optional-dependencies]\n'
            'dev = ["pytest", "mypy"]\n'
            'docs = ["sphinx"]\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert "pytest" in meta.dev_dependencies
        assert "mypy" in meta.dev_dependencies
        assert "sphinx" in meta.dev_dependencies

    def test_scripts_as_entry_points(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\n'
            'name = "test"\n'
            '\n'
            '[project.scripts]\n'
            'mycli = "test.cli:main"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.entry_points == {"mycli": "test.cli:main"}

    def test_keywords(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nkeywords = ["mcp", "docs"]\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.keywords == ["mcp", "docs"]

    def test_malformed_toml(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "pyproject.toml").write_text("not valid toml [[[", encoding="utf-8")
        meta = extractor.extract(tmp_path)
        # Falls back to directory name
        assert meta.name == tmp_path.name


# ---------------------------------------------------------------------------
# package.json (Node.js)
# ---------------------------------------------------------------------------


class TestPackageJsonParsing:
    """Tests for package.json metadata extraction."""

    def test_basic_fields(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "my-pkg", "version": "2.0.0", "description": "A Node package", '
            '"license": "ISC"}',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.name == "my-pkg"
        assert meta.version == "2.0.0"
        assert meta.description == "A Node package"
        assert meta.license == "ISC"
        assert meta.source_file == "package.json"

    def test_author_as_object(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "test", "author": {"name": "Bob", "email": "bob@test.com"}}',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.author == "Bob"
        assert meta.author_email == "bob@test.com"

    def test_author_as_string(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "test", "author": "Charlie"}',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.author == "Charlie"

    def test_dependencies(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "test", "dependencies": {"express": "^4.0", "lodash": "^4.17"}, '
            '"devDependencies": {"jest": "^29.0"}}',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert "express" in meta.dependencies
        assert "lodash" in meta.dependencies
        assert "jest" in meta.dev_dependencies

    def test_repository_as_object(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "test", "repository": {"type": "git", "url": "https://github.com/u/r"}}',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.repository == "https://github.com/u/r"

    def test_malformed_json(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "package.json").write_text("{invalid json", encoding="utf-8")
        meta = extractor.extract(tmp_path)
        # Falls back to directory name
        assert meta.name == tmp_path.name


# ---------------------------------------------------------------------------
# Cargo.toml (Rust)
# ---------------------------------------------------------------------------


class TestCargoTomlParsing:
    """Tests for Cargo.toml metadata extraction."""

    def test_basic_fields(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "Cargo.toml").write_text(
            '[package]\n'
            'name = "my-crate"\n'
            'version = "0.3.0"\n'
            'description = "A Rust crate"\n'
            'license = "MIT"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.name == "my-crate"
        assert meta.version == "0.3.0"
        assert meta.description == "A Rust crate"
        assert meta.license == "MIT"
        assert meta.source_file == "Cargo.toml"

    def test_author_with_email(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "test"\nauthors = ["Dave <dave@test.com>"]\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert meta.author == "Dave"
        assert meta.author_email == "dave@test.com"

    def test_dependencies(self, tmp_path: Path, extractor: MetadataExtractor) -> None:
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "test"\n\n'
            '[dependencies]\nserde = "1.0"\ntokio = "1.0"\n\n'
            '[dev-dependencies]\ncriterion = "0.5"\n',
            encoding="utf-8",
        )
        meta = extractor.extract(tmp_path)
        assert "serde" in meta.dependencies
        assert "tokio" in meta.dependencies
        assert "criterion" in meta.dev_dependencies


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    """Tests for fallback when no config file is found."""

    def test_fallback_to_directory_name(
        self, tmp_path: Path, extractor: MetadataExtractor
    ) -> None:
        meta = extractor.extract(tmp_path)
        assert meta.name == tmp_path.name
        assert meta.source_file == ""

    def test_pyproject_takes_precedence(
        self, tmp_path: Path, extractor: MetadataExtractor
    ) -> None:
        """pyproject.toml is tried before package.json."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "from-pyproject"\n', encoding="utf-8"
        )
        (tmp_path / "package.json").write_text(
            '{"name": "from-package-json"}', encoding="utf-8"
        )
        meta = extractor.extract(tmp_path)
        assert meta.name == "from-pyproject"
        assert meta.source_file == "pyproject.toml"
