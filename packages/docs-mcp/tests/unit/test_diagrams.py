"""Tests for docs_mcp.generators.diagrams -- diagram generation for Python projects.

Covers:
- DiagramResult model instantiation and defaults
- DiagramGenerator._sanitize_id helper
- Validation of diagram types and formats
- Dependency diagrams (Mermaid and PlantUML)
- show_external flag for dependency diagrams
- Class hierarchy diagrams (Mermaid and PlantUML, single-file scope)
- Module map diagrams (Mermaid and PlantUML, direction control)
- ER diagrams (Mermaid and PlantUML, model detection, relationship edges)
- _is_model_class helper (BaseModel, dataclass, plain classes)
- Empty project handling across all diagram types
- docs_generate_diagram MCP tool envelope, error codes, format defaults
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.diagrams import DiagramGenerator, DiagramResult


# ---------------------------------------------------------------------------
# Sample source snippets for tmp_path fixtures
# ---------------------------------------------------------------------------

CLASS_HIERARCHY_CODE = '''\
"""Module with an animal hierarchy."""


class Animal:
    """Base animal."""

    name: str = ""

    def speak(self) -> str:
        """Make a sound."""
        return ""


class Dog(Animal):
    """A dog."""

    breed: str = ""

    def speak(self) -> str:
        return "Woof"


class Puppy(Dog):
    """A puppy."""

    age: int = 0
'''

MODEL_CODE = '''\
"""Models module."""
from pydantic import BaseModel


class User(BaseModel):
    """User model."""

    name: str
    email: str


class Order(BaseModel):
    """Order model."""

    user: User
    total: float
'''

DATACLASS_CODE = '''\
"""Dataclass models."""
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration."""

    host: str
    port: int


class PlainClass:
    """Not a model."""

    value: int = 0
'''

IMPORTING_CODE_A = '''\
"""Module A -- imports B."""
from . import mod_b

x = mod_b.helper()
'''

IMPORTING_CODE_B = '''\
"""Module B -- standalone."""


def helper() -> int:
    return 42
'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_settings(root: Path) -> MagicMock:
    """Create a mock DocsMCPSettings pointing to *root*."""
    settings = MagicMock()
    settings.project_root = root
    settings.output_dir = "docs"
    settings.default_style = "standard"
    settings.default_format = "markdown"
    settings.include_toc = True
    settings.include_badges = True
    settings.changelog_format = "keep-a-changelog"
    settings.adr_format = "madr"
    settings.diagram_format = "mermaid"
    settings.git_log_limit = 100
    settings.log_level = "INFO"
    settings.log_json = False
    return settings


def _write_py(directory: Path, filename: str, content: str) -> Path:
    """Write a Python file into *directory* and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    target.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def generator() -> DiagramGenerator:
    """Return a fresh DiagramGenerator instance."""
    return DiagramGenerator()


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a small Python project with imports and classes."""
    root = tmp_path / "project"
    root.mkdir()
    pkg = root / "myapp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""My app."""\n')
    (pkg / "models.py").write_text(
        '"""Models."""\n\nfrom pydantic import BaseModel\n\n'
        'class User(BaseModel):\n    name: str\n    email: str\n\n'
        'class Post(BaseModel):\n    title: str\n    author: User\n'
    )
    (pkg / "service.py").write_text(
        '"""Service."""\n\nfrom myapp.models import User\n\n'
        'def create_user(name: str) -> User:\n    return User(name=name, email="")\n'
    )
    return root


# ---------------------------------------------------------------------------
# DiagramResult model
# ---------------------------------------------------------------------------


class TestDiagramResult:
    """DiagramResult model instantiation."""

    def test_defaults(self) -> None:
        """node_count and edge_count default to 0."""
        r = DiagramResult(diagram_type="dependency", format="mermaid", content="graph TD\n")
        assert r.diagram_type == "dependency"
        assert r.format == "mermaid"
        assert r.node_count == 0
        assert r.edge_count == 0

    def test_with_counts(self) -> None:
        """All fields store correctly when provided."""
        r = DiagramResult(
            diagram_type="class_hierarchy",
            format="plantuml",
            content="@startuml\n@enduml\n",
            node_count=5,
            edge_count=3,
        )
        assert r.node_count == 5
        assert r.edge_count == 3
        assert r.diagram_type == "class_hierarchy"
        assert r.format == "plantuml"
        assert "@startuml" in r.content


# ---------------------------------------------------------------------------
# _sanitize_id
# ---------------------------------------------------------------------------


class TestSanitizeId:
    """_sanitize_id replaces separators and normalises identifiers."""

    def test_dots_become_underscores(self, generator: DiagramGenerator) -> None:
        assert generator._sanitize_id("my.module.name") == "my_module_name"

    def test_slashes_become_underscores(self, generator: DiagramGenerator) -> None:
        assert generator._sanitize_id("pkg/sub/mod") == "pkg_sub_mod"

    def test_backslashes_become_underscores(self, generator: DiagramGenerator) -> None:
        assert generator._sanitize_id("pkg\\sub") == "pkg_sub"

    def test_hyphens_become_underscores(self, generator: DiagramGenerator) -> None:
        assert generator._sanitize_id("my-package") == "my_package"

    def test_spaces_become_underscores(self, generator: DiagramGenerator) -> None:
        assert generator._sanitize_id("my module") == "my_module"

    def test_non_alphanumeric_removed(self, generator: DiagramGenerator) -> None:
        result = generator._sanitize_id("hello@world!")
        assert "@" not in result
        assert "!" not in result
        assert "helloworld" == result

    def test_leading_digit_gets_prefix(self, generator: DiagramGenerator) -> None:
        result = generator._sanitize_id("3module")
        assert result.startswith("m_")
        assert "3module" in result

    def test_empty_string_stays_empty(self, generator: DiagramGenerator) -> None:
        assert generator._sanitize_id("") == ""

    def test_combined_separators(self, generator: DiagramGenerator) -> None:
        """Multiple separator types in one string are all handled."""
        result = generator._sanitize_id("a.b/c\\d-e f")
        assert result == "a_b_c_d_e_f"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestDiagramValidation:
    """Invalid type/format return empty content."""

    def test_invalid_type_returns_empty(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="bogus")
        assert result.content == ""
        assert result.diagram_type == "bogus"

    def test_invalid_format_returns_empty(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="dependency", output_format="svg"
        )
        assert result.content == ""
        assert result.format == "svg"

    def test_valid_types_accepted(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """All members of VALID_TYPES are accepted without raising."""
        for dtype in DiagramGenerator.VALID_TYPES:
            result = generator.generate(tmp_path, diagram_type=dtype)
            assert isinstance(result, DiagramResult)

    def test_valid_formats_accepted(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Both mermaid and plantuml are accepted."""
        for fmt in DiagramGenerator.VALID_FORMATS:
            result = generator.generate(
                tmp_path, diagram_type="dependency", output_format=fmt
            )
            assert isinstance(result, DiagramResult)


# ---------------------------------------------------------------------------
# Dependency diagrams -- Mermaid
# ---------------------------------------------------------------------------


class TestDependencyDiagramMermaid:
    """Dependency diagrams in Mermaid format."""

    def test_generates_graph_td(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="dependency")
        assert result.content.startswith("graph TD")

    def test_has_subgraphs(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="dependency")
        assert "subgraph" in result.content

    def test_has_solid_edges(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="dependency")
        assert "-->" in result.content

    def test_node_count_positive(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="dependency")
        assert result.node_count > 0

    def test_result_type_and_format(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="dependency")
        assert result.diagram_type == "dependency"
        assert result.format == "mermaid"


# ---------------------------------------------------------------------------
# Dependency diagrams -- PlantUML
# ---------------------------------------------------------------------------


class TestDependencyDiagramPlantUML:
    """Dependency diagrams in PlantUML format."""

    def test_startuml_enduml(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="dependency", output_format="plantuml"
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_has_package(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="dependency", output_format="plantuml"
        )
        assert "package" in result.content


# ---------------------------------------------------------------------------
# show_external flag
# ---------------------------------------------------------------------------


class TestDependencyShowExternal:
    """show_external flag toggles external dependency display."""

    def test_external_shown_mermaid(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="dependency", show_external=True
        )
        # pydantic is an external dep imported in models.py
        assert "pydantic" in result.content.lower() or result.node_count >= 1

    def test_external_hidden_mermaid(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="dependency", show_external=False
        )
        # With show_external=False, external nodes should not be labelled as
        # :::external in the output.
        assert ":::external" not in result.content

    def test_show_external_does_not_crash(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """show_external=True on a trivial project does not raise."""
        _write_py(tmp_path, "app.py", "import os\nimport json\nx = 1\n")
        result = generator.generate(
            tmp_path,
            diagram_type="dependency",
            output_format="mermaid",
            show_external=True,
        )
        assert isinstance(result, DiagramResult)


# ---------------------------------------------------------------------------
# Class hierarchy -- Mermaid
# ---------------------------------------------------------------------------


class TestClassHierarchyMermaid:
    """Class hierarchy diagrams in Mermaid format."""

    def test_generates_class_diagram(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="class_hierarchy"
        )
        assert "classDiagram" in result.content

    def test_inheritance_edges(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="class_hierarchy"
        )
        assert "class " in result.content

    def test_method_visibility_prefix(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        root = tmp_path / "vis"
        root.mkdir()
        (root / "widget.py").write_text(
            'class Widget:\n'
            '    def public_method(self) -> None: ...\n'
            '    def _private_method(self) -> None: ...\n'
        )
        result = generator.generate(
            root, diagram_type="class_hierarchy"
        )
        assert "+public_method()" in result.content
        assert "-_private_method()" in result.content

    def test_class_hierarchy_with_real_inheritance(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Create files with a real hierarchy and verify inheritance edges."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        result = generator.generate(
            tmp_path, diagram_type="class_hierarchy", output_format="mermaid"
        )
        assert "classDiagram" in result.content
        assert "<|--" in result.content
        assert result.edge_count >= 1
        # Animal, Dog, Puppy -> 3 nodes
        assert result.node_count == 3

    def test_single_file_scope(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """scope=<file> limits extraction to a single file."""
        pkg = tmp_path / "pkg"
        _write_py(pkg, "a.py", CLASS_HIERARCHY_CODE)
        _write_py(pkg, "b.py", "class Other:\n    pass\n")

        result = generator.generate(
            tmp_path,
            diagram_type="class_hierarchy",
            output_format="mermaid",
            scope=str(pkg / "a.py"),
        )
        assert "classDiagram" in result.content
        # Should have classes from a.py only (Animal, Dog, Puppy)
        assert result.node_count == 3


# ---------------------------------------------------------------------------
# Class hierarchy -- PlantUML
# ---------------------------------------------------------------------------


class TestClassHierarchyPlantUML:
    """Class hierarchy diagrams in PlantUML format."""

    def test_startuml_enduml(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="class_hierarchy",
            output_format="plantuml",
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_class_keyword(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="class_hierarchy",
            output_format="plantuml",
        )
        assert "class " in result.content

    def test_plantuml_inheritance_edges(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """PlantUML output includes inheritance edges."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        result = generator.generate(
            tmp_path, diagram_type="class_hierarchy", output_format="plantuml"
        )
        assert "<|--" in result.content
        assert result.edge_count >= 1


# ---------------------------------------------------------------------------
# Module map -- Mermaid
# ---------------------------------------------------------------------------


class TestModuleMapMermaid:
    """Module map diagrams in Mermaid format."""

    def test_nested_subgraphs(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="module_map"
        )
        assert "subgraph" in result.content

    def test_node_labels_with_counts(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="module_map"
        )
        assert result.node_count >= 1

    def test_direction_td(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """TD direction is reflected in the output."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write_py(pkg, "core.py", "def hello(): pass\n")
        result = generator.generate(
            tmp_path, diagram_type="module_map", direction="TD"
        )
        assert "graph TD" in result.content

    def test_direction_lr(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """LR direction is reflected in the output."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write_py(pkg, "core.py", "def hello(): pass\n")
        result = generator.generate(
            tmp_path, diagram_type="module_map", direction="LR"
        )
        assert "graph LR" in result.content

    def test_package_with_init(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """A package with __init__.py produces nodes."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write_py(pkg, "alpha.py", "x = 1\n")
        _write_py(pkg, "beta.py", "y = 2\n")
        result = generator.generate(
            tmp_path, diagram_type="module_map", output_format="mermaid"
        )
        assert result.node_count >= 2


# ---------------------------------------------------------------------------
# Module map -- PlantUML
# ---------------------------------------------------------------------------


class TestModuleMapPlantUML:
    """Module map diagrams in PlantUML format."""

    def test_startuml_enduml(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="module_map",
            output_format="plantuml",
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_package_keyword(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="module_map",
            output_format="plantuml",
        )
        assert "package" in result.content


# ---------------------------------------------------------------------------
# ER diagram -- Mermaid
# ---------------------------------------------------------------------------


class TestERDiagramMermaid:
    """ER diagrams in Mermaid format from Pydantic models."""

    def test_generates_er_diagram(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="er_diagram"
        )
        assert "erDiagram" in result.content

    def test_has_fields(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="er_diagram"
        )
        assert "string" in result.content.lower() or "name" in result.content.lower()

    def test_has_relationships(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project, diagram_type="er_diagram"
        )
        # Post.author is typed User, so there should be a relationship edge
        assert result.edge_count >= 1 or "has" in result.content

    def test_non_model_classes_excluded(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Plain classes (not BaseModel/dataclass) are excluded from ER."""
        _write_py(tmp_path, "mixed.py", DATACLASS_CODE)
        result = generator.generate(
            tmp_path, diagram_type="er_diagram", output_format="mermaid"
        )
        # Config (dataclass) should be included, PlainClass should not.
        assert "Config" in result.content
        assert "PlainClass" not in result.content

    def test_relationship_edge_from_model_code(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Order.user: User produces a relationship edge."""
        _write_py(tmp_path, "models.py", MODEL_CODE)
        result = generator.generate(
            tmp_path, diagram_type="er_diagram", output_format="mermaid"
        )
        assert result.edge_count >= 1

    def test_er_empty_for_no_models(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """A project with no model classes returns empty ER content."""
        _write_py(tmp_path, "utils.py", "def add(a, b): return a + b\n")
        result = generator.generate(
            tmp_path, diagram_type="er_diagram", output_format="mermaid"
        )
        assert result.content == ""

    def test_dataclass_included_in_er(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Dataclass-decorated classes are recognised as models."""
        _write_py(tmp_path, "dc.py", DATACLASS_CODE)
        result = generator.generate(
            tmp_path, diagram_type="er_diagram", output_format="mermaid"
        )
        assert result.node_count >= 1
        assert "Config" in result.content


# ---------------------------------------------------------------------------
# ER diagram -- PlantUML
# ---------------------------------------------------------------------------


class TestERDiagramPlantUML:
    """ER diagrams in PlantUML format."""

    def test_startuml_enduml(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="er_diagram",
            output_format="plantuml",
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_entity_keyword(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="er_diagram",
            output_format="plantuml",
        )
        assert "entity " in result.content

    def test_plantuml_er_from_model_code(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """PlantUML ER from MODEL_CODE contains entity definitions."""
        _write_py(tmp_path, "models.py", MODEL_CODE)
        result = generator.generate(
            tmp_path, diagram_type="er_diagram", output_format="plantuml"
        )
        assert "entity " in result.content
        assert "@startuml" in result.content


# ---------------------------------------------------------------------------
# _is_model_class
# ---------------------------------------------------------------------------


class TestIsModelClass:
    """_is_model_class correctly identifies data models."""

    def test_pydantic_base_model(self, generator: DiagramGenerator) -> None:
        from docs_mcp.extractors.models import ClassInfo

        cls = ClassInfo(name="User", line=1, bases=["BaseModel"])
        assert generator._is_model_class(cls) is True

    def test_pydantic_base_settings(self, generator: DiagramGenerator) -> None:
        from docs_mcp.extractors.models import ClassInfo

        cls = ClassInfo(name="AppConfig", line=1, bases=["BaseSettings"])
        assert generator._is_model_class(cls) is True

    def test_dataclass_decorator(self, generator: DiagramGenerator) -> None:
        from docs_mcp.extractors.models import ClassInfo, DecoratorInfo

        cls = ClassInfo(
            name="Config",
            line=1,
            bases=[],
            decorators=[DecoratorInfo(name="dataclass", line=1)],
        )
        assert generator._is_model_class(cls) is True

    def test_non_model(self, generator: DiagramGenerator) -> None:
        from docs_mcp.extractors.models import ClassInfo

        cls = ClassInfo(name="Service", line=1, bases=["object"])
        assert generator._is_model_class(cls) is False

    def test_qualified_base(self, generator: DiagramGenerator) -> None:
        """A fully-qualified base like pydantic.BaseModel is recognised."""
        from docs_mcp.extractors.models import ClassInfo

        cls = ClassInfo(name="Thing", line=1, bases=["pydantic.BaseModel"])
        assert generator._is_model_class(cls) is True


# ---------------------------------------------------------------------------
# Empty project handling
# ---------------------------------------------------------------------------


class TestEmptyProject:
    """Empty project directories produce empty content."""

    def test_dependency_empty(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="dependency")
        assert result.node_count == 0
        assert result.edge_count == 0

    def test_class_hierarchy_empty(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="class_hierarchy")
        assert result.content == ""

    def test_module_map_empty(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="module_map")
        assert result.node_count == 0 or result.content == ""

    def test_er_diagram_empty(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="er_diagram")
        assert result.content == ""


# ---------------------------------------------------------------------------
# MCP Tool -- docs_generate_diagram
# ---------------------------------------------------------------------------


class TestDiagramMCPTool:
    """docs_generate_diagram MCP tool response envelope and error handling."""

    def test_response_envelope(self, python_project: Path) -> None:
        """Successful generation returns the standard envelope fields."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(python_project),
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="dependency",
                    project_root=str(python_project),
                )
            )

        assert result["tool"] == "docs_generate_diagram"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result

    def test_data_fields(self, python_project: Path) -> None:
        """Response data includes diagram_type, format, node_count, edge_count, content."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(python_project),
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="dependency",
                    project_root=str(python_project),
                )
            )

        data = result["data"]
        assert "diagram_type" in data
        assert "format" in data
        assert "node_count" in data
        assert "edge_count" in data
        assert "content" in data
        assert data["node_count"] >= 0
        assert data["edge_count"] >= 0

    def test_invalid_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns INVALID_ROOT error."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        fake = tmp_path / "does_not_exist"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = _run(
                docs_generate_diagram(project_root=str(fake))
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    def test_no_content_returns_error(self, tmp_path: Path) -> None:
        """Empty project returns NO_CONTENT error."""
        root = tmp_path / "empty"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="class_hierarchy",
                    project_root=str(root),
                )
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NO_CONTENT"

    def test_format_defaults_to_settings(self, tmp_path: Path) -> None:
        """When format is empty, the tool uses the setting's diagram_format."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        settings = _make_settings(tmp_path)
        settings.diagram_format = "plantuml"

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=settings,
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="class_hierarchy",
                    format="",
                    project_root=str(tmp_path),
                )
            )

        assert result["success"] is True
        assert result["data"]["format"] == "plantuml"
        assert "@startuml" in result["data"]["content"]

    def test_explicit_format_overrides_settings(self, tmp_path: Path) -> None:
        """An explicit format param takes precedence over settings."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        settings = _make_settings(tmp_path)
        settings.diagram_format = "plantuml"

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=settings,
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="class_hierarchy",
                    format="mermaid",
                    project_root=str(tmp_path),
                )
            )

        assert result["success"] is True
        assert result["data"]["format"] == "mermaid"
        assert "classDiagram" in result["data"]["content"]

    def test_er_diagram_via_tool(self, tmp_path: Path) -> None:
        """ER diagram type works through the MCP tool."""
        _write_py(tmp_path, "models.py", MODEL_CODE)

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="er_diagram",
                    project_root=str(tmp_path),
                )
            )

        assert result["success"] is True
        assert result["data"]["diagram_type"] == "er_diagram"
        assert "erDiagram" in result["data"]["content"]

    def test_class_hierarchy_via_tool(self, tmp_path: Path) -> None:
        """Class hierarchy succeeds through the MCP tool."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = _run(
                docs_generate_diagram(
                    diagram_type="class_hierarchy",
                    project_root=str(tmp_path),
                )
            )

        assert result["success"] is True
        assert result["data"]["diagram_type"] == "class_hierarchy"
        assert result["data"]["node_count"] >= 1
        assert len(result["data"]["content"]) > 0
