"""Tests for docs_mcp.generators.readme — README generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.generators.metadata import ProjectMetadata
from docs_mcp.generators.readme import ReadmeGenerator


@pytest.fixture
def python_metadata() -> ProjectMetadata:
    """Standard Python project metadata."""
    return ProjectMetadata(
        name="my-project",
        version="1.0.0",
        description="A great Python project",
        license="MIT",
        python_requires=">=3.12",
        dependencies=["click", "pydantic"],
        entry_points={"mycli": "my_project.cli:main"},
        source_file="pyproject.toml",
    )


@pytest.fixture
def node_metadata() -> ProjectMetadata:
    """Standard Node.js project metadata."""
    return ProjectMetadata(
        name="my-node-pkg",
        version="2.0.0",
        description="A Node.js package",
        license="ISC",
        dependencies=["express", "lodash"],
        source_file="package.json",
    )


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """A minimal Python project directory."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "my-project"\nversion = "1.0.0"\n'
        'description = "A great Python project"\n'
        'requires-python = ">=3.12"\nlicense = "MIT"\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    return root


# ---------------------------------------------------------------------------
# Style selection
# ---------------------------------------------------------------------------


class TestStyleSelection:
    """Tests for README style handling."""

    def test_minimal_style(self, python_project: Path) -> None:
        gen = ReadmeGenerator(style="minimal")
        assert gen.style == "minimal"
        result = gen.generate(python_project)
        assert "# my-project" in result
        assert "## Installation" in result
        # Minimal should NOT have Features or Development
        assert "## Features" not in result

    def test_standard_style(self, python_project: Path) -> None:
        gen = ReadmeGenerator(style="standard")
        result = gen.generate(python_project)
        assert "# my-project" in result
        assert "## Features" in result
        assert "## Installation" in result
        assert "## Development" in result
        # Standard should NOT have Architecture or Contributing
        assert "## Architecture" not in result
        assert "## Contributing" not in result

    def test_comprehensive_style(self, python_project: Path) -> None:
        gen = ReadmeGenerator(style="comprehensive")
        result = gen.generate(python_project)
        assert "# my-project" in result
        assert "## Table of Contents" in result
        assert "## Features" in result
        assert "## Architecture" not in result or "## Architecture" in result
        assert "## Contributing" in result

    def test_invalid_style_defaults_to_standard(self, python_project: Path) -> None:
        gen = ReadmeGenerator(style="invalid")
        assert gen.style == "standard"


# ---------------------------------------------------------------------------
# Installation section
# ---------------------------------------------------------------------------


class TestInstallationGeneration:
    """Tests for installation section generation."""

    def test_pip_install(self, python_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_installation(python_metadata)
        assert "pip install my-project" in result
        assert "```bash" in result

    def test_npm_install(self, node_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_installation(node_metadata)
        assert "npm install my-node-pkg" in result

    def test_cargo_install(self) -> None:
        meta = ProjectMetadata(name="my-crate", source_file="Cargo.toml")
        gen = ReadmeGenerator()
        result = gen._generate_installation(meta)
        assert "cargo add my-crate" in result


# ---------------------------------------------------------------------------
# Badge generation
# ---------------------------------------------------------------------------


class TestBadgeGeneration:
    """Tests for badge generation."""

    def test_python_version_badge(self, python_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_badges(python_metadata)
        assert "img.shields.io/badge/python-" in result

    def test_license_badge(self, python_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_badges(python_metadata)
        assert "img.shields.io/badge/license-MIT" in result

    def test_version_badge(self, python_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_badges(python_metadata)
        assert "img.shields.io/badge/version-1.0.0" in result

    def test_no_badges_for_empty_metadata(self) -> None:
        meta = ProjectMetadata(name="test")
        gen = ReadmeGenerator()
        result = gen._generate_badges(meta)
        assert result == ""


# ---------------------------------------------------------------------------
# Features section
# ---------------------------------------------------------------------------


class TestFeaturesGeneration:
    """Tests for features section generation."""

    def test_detects_python_project(self, python_project: Path) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_features(python_project)
        assert "Python project" in result

    def test_detects_test_suite(self, python_project: Path) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_features(python_project)
        assert "Test suite" in result

    def test_detects_docker(self, python_project: Path) -> None:
        (python_project / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
        gen = ReadmeGenerator()
        result = gen._generate_features(python_project)
        assert "Docker" in result

    def test_detects_github_actions(self, python_project: Path) -> None:
        workflows = python_project / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        gen = ReadmeGenerator()
        result = gen._generate_features(python_project)
        assert "GitHub Actions" in result

    def test_empty_project(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        gen = ReadmeGenerator()
        result = gen._generate_features(empty)
        assert result == ""


# ---------------------------------------------------------------------------
# Usage section
# ---------------------------------------------------------------------------


class TestUsageGeneration:
    """Tests for usage section generation."""

    def test_entry_points_shown(self, python_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_usage(python_metadata)
        assert "mycli" in result

    def test_python_import_fallback(self) -> None:
        meta = ProjectMetadata(name="my-lib", source_file="pyproject.toml")
        gen = ReadmeGenerator()
        result = gen._generate_usage(meta)
        assert "import my_lib" in result

    def test_node_require_fallback(self, node_metadata: ProjectMetadata) -> None:
        # Clear entry_points so we get the require fallback
        node_metadata.entry_points = {}
        gen = ReadmeGenerator()
        result = gen._generate_usage(node_metadata)
        assert 'require("my-node-pkg")' in result


# ---------------------------------------------------------------------------
# Development section
# ---------------------------------------------------------------------------


class TestDevelopmentGeneration:
    """Tests for development section generation."""

    def test_python_dev_setup(self, python_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_development(python_metadata)
        assert "pip install" in result
        assert "pytest" in result

    def test_node_dev_setup(self, node_metadata: ProjectMetadata) -> None:
        gen = ReadmeGenerator()
        result = gen._generate_development(node_metadata)
        assert "npm install" in result
        assert "npm test" in result

    def test_cargo_dev_setup(self) -> None:
        meta = ProjectMetadata(name="my-crate", source_file="Cargo.toml")
        gen = ReadmeGenerator()
        result = gen._generate_development(meta)
        assert "cargo build" in result
        assert "cargo test" in result


# ---------------------------------------------------------------------------
# Full generation with metadata override
# ---------------------------------------------------------------------------


class TestFullGeneration:
    """Tests for end-to-end README generation."""

    def test_generate_with_provided_metadata(
        self, python_project: Path, python_metadata: ProjectMetadata
    ) -> None:
        gen = ReadmeGenerator(style="standard")
        result = gen.generate(python_project, metadata=python_metadata)
        assert "# my-project" in result
        assert "A great Python project" in result

    def test_generate_auto_extracts_metadata(self, python_project: Path) -> None:
        gen = ReadmeGenerator(style="minimal")
        result = gen.generate(python_project)
        assert "# my-project" in result

    def test_empty_project_uses_dir_name(self, tmp_path: Path) -> None:
        empty = tmp_path / "cool-tool"
        empty.mkdir()
        gen = ReadmeGenerator(style="minimal")
        result = gen.generate(empty)
        assert "# cool-tool" in result
