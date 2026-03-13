"""Tests for C4 diagram generation and interactive HTML (Epics 80, 81.3)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.diagrams import DiagramGenerator, DiagramResult
from docs_mcp.generators.interactive_html import InteractiveHtmlGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_pyproject(root: Path, **kwargs: Any) -> None:
    deps = kwargs.get("dependencies", [])
    deps_str = ", ".join(f'"{d}"' for d in deps)
    content = f"""
[project]
name = "{kwargs.get('name', 'my-project')}"
version = "1.0.0"
description = "{kwargs.get('description', 'A test project')}"
dependencies = [{deps_str}]
"""
    _write(root / "pyproject.toml", content)


# ---------------------------------------------------------------------------
# VALID_TYPES updated
# ---------------------------------------------------------------------------


class TestDiagramTypes:
    def test_c4_types_in_valid_types(self) -> None:
        assert "c4_context" in DiagramGenerator.VALID_TYPES
        assert "c4_container" in DiagramGenerator.VALID_TYPES
        assert "c4_component" in DiagramGenerator.VALID_TYPES

    def test_original_types_preserved(self) -> None:
        assert "dependency" in DiagramGenerator.VALID_TYPES
        assert "class_hierarchy" in DiagramGenerator.VALID_TYPES
        assert "module_map" in DiagramGenerator.VALID_TYPES
        assert "er_diagram" in DiagramGenerator.VALID_TYPES

    def test_total_type_count(self) -> None:
        assert len(DiagramGenerator.VALID_TYPES) == 7


# ---------------------------------------------------------------------------
# C4 System Context (Epic 80.1)
# ---------------------------------------------------------------------------


class TestC4Context:
    def test_mermaid_format(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi"])
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_context", output_format="mermaid")

        assert result.diagram_type == "c4_context"
        assert result.format == "mermaid"
        assert "C4Context" in result.content
        assert "my-project" in result.content
        assert result.node_count >= 2

    def test_plantuml_format(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi"])
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_context", output_format="plantuml")

        assert "@startuml" in result.content
        assert "C4_Context" in result.content
        assert "my-project" in result.content

    def test_detects_database_actor(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["sqlalchemy"])
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_context", output_format="mermaid")

        assert "Database" in result.content

    def test_detects_external_api(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["httpx"])
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_context", output_format="mermaid")

        assert "ExternalAPI" in result.content

    def test_detects_mcp_client(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["mcp[cli]"])
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_context", output_format="mermaid")

        assert "MCPClient" in result.content

    def test_fallback_user_actor(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_context", output_format="mermaid")

        assert "User" in result.content


# ---------------------------------------------------------------------------
# C4 Container (Epic 80.2)
# ---------------------------------------------------------------------------


class TestC4Container:
    def test_mermaid_workspace_packages(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _make_pyproject(tmp_path / "packages" / "core", name="my-core", description="Core lib")
        _make_pyproject(tmp_path / "packages" / "api", name="my-api", description="API server")

        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_container", output_format="mermaid")

        assert "C4Container" in result.content
        assert "my-core" in result.content
        assert "my-api" in result.content
        assert result.node_count >= 2

    def test_plantuml_format(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _make_pyproject(tmp_path / "packages" / "core", name="core")

        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_container", output_format="plantuml")

        assert "@startuml" in result.content
        assert "C4_Container" in result.content

    def test_detects_docker(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "Dockerfile", "FROM python:3.12")

        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_container", output_format="mermaid")

        assert "Docker" in result.content

    def test_src_layout(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "src" / "mypackage" / "__init__.py", "")

        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_container", output_format="mermaid")

        assert "mypackage" in result.content


# ---------------------------------------------------------------------------
# C4 Component (Epic 80.3)
# ---------------------------------------------------------------------------


class TestC4Component:
    def test_mermaid_format(self, tmp_path: Path) -> None:
        # Create a Python package with modules
        pkg = tmp_path / "src" / "mypkg"
        _write(pkg / "__init__.py", "")
        _write(pkg / "core.py", "def hello(): pass\ndef world(): pass\n")
        _write(pkg / "utils.py", "def helper(): pass\n")

        gen = DiagramGenerator()
        result = gen.generate(
            tmp_path / "src" / "mypkg",
            diagram_type="c4_component",
            output_format="mermaid",
        )

        assert result.diagram_type == "c4_component"
        assert "C4Component" in result.content

    def test_plantuml_format(self, tmp_path: Path) -> None:
        pkg = tmp_path / "src" / "mypkg"
        _write(pkg / "__init__.py", "")
        _write(pkg / "core.py", "def func(): pass\n")

        gen = DiagramGenerator()
        result = gen.generate(
            tmp_path / "src" / "mypkg",
            diagram_type="c4_component",
            output_format="plantuml",
        )

        assert "@startuml" in result.content
        assert "C4_Component" in result.content

    def test_empty_package_degraded(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="c4_component", output_format="mermaid")

        # Empty package should degrade gracefully
        assert result.content == "" or result.degraded


# ---------------------------------------------------------------------------
# Interactive HTML (Epic 81.3)
# ---------------------------------------------------------------------------


class TestInteractiveHtmlGenerator:
    def test_basic_generation(self) -> None:
        diagrams = [
            ("Module Map", "graph TD\n  A --> B\n  B --> C"),
            ("Dependencies", "graph LR\n  X --> Y"),
        ]
        gen = InteractiveHtmlGenerator()
        result = gen.generate(diagrams, title="My Architecture")

        assert "<!DOCTYPE html>" in result.content
        assert "My Architecture" in result.content
        assert "mermaid" in result.content
        assert result.diagram_count == 2

    def test_empty_diagrams(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate([], title="Empty")

        assert result.diagram_count == 0
        assert "No diagrams" in result.content

    def test_controls_present(self) -> None:
        diagrams = [("Test", "graph TD\n  A --> B")]
        gen = InteractiveHtmlGenerator()
        result = gen.generate(diagrams)

        assert "zoom-in" in result.content
        assert "zoom-out" in result.content
        assert "zoom-reset" in result.content

    def test_toc_generated(self) -> None:
        diagrams = [
            ("Module Map", "graph TD\n  A --> B"),
            ("Class Diagram", "classDiagram\n  A <|-- B"),
        ]
        gen = InteractiveHtmlGenerator()
        result = gen.generate(diagrams)

        assert "Module Map" in result.content
        assert "Class Diagram" in result.content
        assert 'class="toc"' in result.content

    def test_html_escaping(self) -> None:
        diagrams = [("<Script>alert(1)</Script>", "graph TD\n  A --> B")]
        gen = InteractiveHtmlGenerator()
        result = gen.generate(diagrams)

        assert "<Script>" not in result.content
        assert "&lt;Script&gt;" in result.content

    def test_theme_validation(self) -> None:
        gen = InteractiveHtmlGenerator()
        # Invalid theme falls back to default
        result = gen.generate(
            [("Test", "graph TD\n  A")],
            theme="invalid",
        )
        assert result.diagram_count == 1

    def test_print_css_included(self) -> None:
        diagrams = [("Test", "graph TD\n  A")]
        gen = InteractiveHtmlGenerator()
        result = gen.generate(diagrams)

        assert "@media print" in result.content


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestDocsGenerateInteractiveDiagramsTool:
    def _make_settings(self, root: Path) -> MagicMock:
        settings = MagicMock()
        settings.project_root = root
        settings.diagram_format = "mermaid"
        return settings

    def test_success(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi"])
        _write(tmp_path / "src" / "app" / "__init__.py", "")
        _write(tmp_path / "src" / "app" / "main.py", "def run(): pass\n")
        from docs_mcp.server_gen_tools import docs_generate_interactive_diagrams

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = self._make_settings(tmp_path)
            result = _run(docs_generate_interactive_diagrams(
                diagram_types="c4_context",
                project_root=str(tmp_path),
            ))

        assert result["success"] is True
        assert result["data"]["diagram_count"] >= 1
        assert "<!DOCTYPE html>" in result["data"]["content"]

    def test_no_types(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_interactive_diagrams

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = self._make_settings(tmp_path)
            result = _run(docs_generate_interactive_diagrams(
                diagram_types="",
                project_root=str(tmp_path),
            ))

        assert result["success"] is False
        assert result["error"]["code"] == "NO_TYPES"

    def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_interactive_diagrams

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = _run(docs_generate_interactive_diagrams(project_root=bad_path))
        assert result["success"] is False
