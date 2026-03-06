"""Tests for docs_mcp.generators.architecture -- architecture report generation.

Covers:
- ArchitectureResult model instantiation and defaults
- ArchitectureGenerator.generate() with minimal project
- ArchitectureGenerator.generate() with multi-package project
- SVG diagram rendering (architecture + dependency flow)
- Component value description generation
- Package collection from module map
- Edge collection from dependency graph
- HTML output structure (hero, sections, footer)
- docs_generate_architecture MCP tool envelope and error handling
- Output file writing via output_path parameter
- Custom title and subtitle override
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.architecture import (
    ArchitectureGenerator,
    ArchitectureResult,
)


# ---------------------------------------------------------------------------
# Sample project fixtures
# ---------------------------------------------------------------------------

SAMPLE_MODULE = '''\
"""Data processing module."""

from pathlib import Path


class DataLoader:
    """Loads data from various sources."""

    def load(self, path: str) -> list[dict[str, str]]:
        """Load data from a file."""
        return []

    def validate(self, data: list[dict[str, str]]) -> bool:
        """Validate loaded data."""
        return True


class DataTransformer:
    """Transforms data into output format."""

    def transform(self, records: list[dict[str, str]]) -> str:
        """Transform records to CSV."""
        return ""


def process(path: str) -> str:
    """Process a file end-to-end."""
    return ""
'''

SAMPLE_INIT = '''\
"""Core analytics package."""
'''


@pytest.fixture
def arch_project(tmp_path: Path) -> Path:
    """Create a project with multiple packages for architecture testing."""
    root = tmp_path / "myproject"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\n'
        'name = "my-analytics"\n'
        'version = "3.0.0"\n'
        'description = "Analytics platform for data processing"\n'
        'requires-python = ">=3.12"\n'
        'license = "MIT"\n'
        'dependencies = ["pydantic", "structlog", "httpx"]\n'
        '\n[project.optional-dependencies]\n'
        'dev = ["pytest", "ruff", "mypy"]\n',
        encoding="utf-8",
    )

    # src/analytics/ package
    src = root / "src"
    analytics = src / "analytics"
    analytics.mkdir(parents=True)
    (analytics / "__init__.py").write_text(SAMPLE_INIT, encoding="utf-8")
    (analytics / "loader.py").write_text(SAMPLE_MODULE, encoding="utf-8")

    # src/analytics/transforms/ sub-package
    transforms = analytics / "transforms"
    transforms.mkdir()
    (transforms / "__init__.py").write_text('"""Transform utilities."""\n', encoding="utf-8")
    (transforms / "csv.py").write_text(
        '"""CSV transform."""\n\ndef to_csv(data: list) -> str:\n    return ""\n',
        encoding="utf-8",
    )

    return root


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """Create an empty project with just pyproject.toml."""
    root = tmp_path / "empty"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "empty-proj"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestArchitectureResult:
    """Tests for ArchitectureResult model."""

    def test_defaults(self) -> None:
        result = ArchitectureResult(content="<html></html>")
        assert result.format == "html"
        assert result.package_count == 0
        assert result.module_count == 0
        assert result.edge_count == 0
        assert result.class_count == 0
        assert result.degraded is False

    def test_with_stats(self) -> None:
        result = ArchitectureResult(
            content="<html>test</html>",
            package_count=5,
            module_count=20,
            edge_count=15,
            class_count=8,
        )
        assert result.package_count == 5
        assert result.module_count == 20


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


class TestArchitectureGenerator:
    """Tests for ArchitectureGenerator."""

    def test_generate_minimal_project(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert result.format == "html"
        assert result.content
        assert "<!DOCTYPE html>" in result.content
        assert "my-analytics" in result.content
        assert "Architecture Report" in result.content

    def test_generate_contains_hero(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert 'class="hero"' in result.content
        assert 'class="hero-title"' in result.content

    def test_generate_contains_svg(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert "<svg" in result.content
        assert "</svg>" in result.content

    def test_generate_contains_component_cards(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert 'class="component-card"' in result.content

    def test_generate_contains_stats(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert 'class="stat-number"' in result.content
        assert "Packages" in result.content
        assert "Modules" in result.content

    def test_generate_contains_tech_stack(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert "pydantic" in result.content
        assert "structlog" in result.content

    def test_generate_contains_footer(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert "DocsMCP" in result.content
        assert 'class="footer"' in result.content

    def test_custom_title_and_subtitle(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(
            arch_project,
            title="Custom Title",
            subtitle="Custom tagline here",
        )

        assert "Custom Title" in result.content
        assert "Custom tagline here" in result.content

    def test_empty_project_produces_output(self, empty_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(empty_project)

        assert result.format == "html"
        assert result.content
        assert "<!DOCTYPE html>" in result.content

    def test_metadata_extraction(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert "v3.0.0" in result.content
        assert "MIT" in result.content

    def test_api_surface_classes(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        assert "DataLoader" in result.content
        assert "DataTransformer" in result.content

    def test_package_count_populated(self, arch_project: Path) -> None:
        gen = ArchitectureGenerator()
        result = gen.generate(arch_project)

        # Should detect at least analytics package
        assert result.package_count >= 1 or result.module_count >= 1


# ---------------------------------------------------------------------------
# Component value description
# ---------------------------------------------------------------------------


class TestComponentValueDescription:
    """Tests for _generate_component_value helper."""

    def test_with_docstring(self) -> None:
        gen = ArchitectureGenerator()
        text = gen._generate_component_value(
            "analytics", "Provides data analytics features", 5, 10, 3,
        )
        assert "analytics" in text
        assert "5 modules" in text
        assert "10 functions" in text
        assert "3 classes" in text

    def test_without_docstring(self) -> None:
        gen = ArchitectureGenerator()
        text = gen._generate_component_value("utils", "", 2, 5, 0)
        assert "utils" in text
        assert "5 functions" in text

    def test_classes_only(self) -> None:
        gen = ArchitectureGenerator()
        text = gen._generate_component_value("models", "", 1, 0, 4)
        assert "4 classes" in text
        assert "abstractions" in text


# ---------------------------------------------------------------------------
# Package/edge collection helpers
# ---------------------------------------------------------------------------


class TestCollectPackages:
    """Tests for _collect_packages helper."""

    def test_none_module_map(self) -> None:
        gen = ArchitectureGenerator()
        assert gen._collect_packages(None) == []

    def test_from_module_map(self, arch_project: Path) -> None:
        from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

        mm = ModuleMapAnalyzer().analyze(arch_project, depth=3)
        gen = ArchitectureGenerator()
        packages = gen._collect_packages(mm)
        assert len(packages) >= 1
        # Module map resolves into the analytics package, exposing its children
        names = [p["name"] for p in packages]
        assert any(n in names for n in ("analytics", "loader", "transforms"))


class TestCollectEdges:
    """Tests for _collect_edges helper."""

    def test_none_graph(self) -> None:
        gen = ArchitectureGenerator()
        assert gen._collect_edges(None, []) == []

    def test_no_packages(self) -> None:
        gen = ArchitectureGenerator()
        graph = MagicMock()
        graph.edges = []
        assert gen._collect_edges(graph, []) == []


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------


class TestDocsGenerateArchitectureTool:
    """Tests for the docs_generate_architecture MCP tool."""

    def test_invalid_root(self) -> None:
        from docs_mcp.server_gen_tools import docs_generate_architecture

        result = asyncio.run(
            docs_generate_architecture(project_root="/nonexistent/path/xyz")
        )
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    def test_success_envelope(self, arch_project: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_architecture

        result = asyncio.run(
            docs_generate_architecture(project_root=str(arch_project))
        )
        assert result["success"] is True
        assert result["tool"] == "docs_generate_architecture"
        assert "data" in result
        assert result["data"]["format"] == "html"
        assert "<!DOCTYPE html>" in result["data"]["content"]

    def test_write_to_file(self, arch_project: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_architecture

        out_path = arch_project / "docs" / "ARCHITECTURE.html"
        result = asyncio.run(
            docs_generate_architecture(
                project_root=str(arch_project),
                output_path=str(out_path),
            )
        )
        assert result["success"] is True
        assert result["data"]["written_to"] == str(out_path)
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_custom_title(self, arch_project: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_architecture

        result = asyncio.run(
            docs_generate_architecture(
                project_root=str(arch_project),
                title="My Custom Report",
            )
        )
        assert result["success"] is True
        assert "My Custom Report" in result["data"]["content"]

    def test_relative_output_path(self, arch_project: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_architecture

        result = asyncio.run(
            docs_generate_architecture(
                project_root=str(arch_project),
                output_path="architecture.html",
            )
        )
        assert result["success"] is True
        assert (arch_project / "architecture.html").exists()
