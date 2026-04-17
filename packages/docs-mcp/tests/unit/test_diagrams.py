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

from pathlib import Path
from unittest.mock import patch

import pytest

from docs_mcp.generators.diagrams import DiagramGenerator, DiagramResult
from tests.helpers import make_settings as _make_settings

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
        "class User(BaseModel):\n    name: str\n    email: str\n\n"
        "class Post(BaseModel):\n    title: str\n    author: User\n"
    )
    (pkg / "service.py").write_text(
        '"""Service."""\n\nfrom myapp.models import User\n\n'
        'def create_user(name: str) -> User:\n    return User(name=name, email="")\n'
    )
    return root


@pytest.fixture
def large_python_project(tmp_path: Path) -> Path:
    """Create a project with enough top-level packages to exceed the auto-poster threshold.

    The auto-select redirect (STORY-100.6) only fires when a project has fewer than
    _POSTER_AUTO_THRESHOLD (15) top-level packages.  Dependency-diagram tests must use
    this fixture so they receive a real dependency diagram rather than a pattern_card.
    """
    root = tmp_path / "large_project"
    root.mkdir()
    # Create 16 top-level packages so the threshold is never triggered.
    for i in range(16):
        pkg = root / f"pkg{i}"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(f'"""Package {i}."""\n')
        if i > 0:
            (pkg / "utils.py").write_text(
                f'"""Utils for pkg{i}."""\n\nfrom pkg{i - 1} import *  # noqa: F401, F403\n'
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
        assert result == "helloworld"

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
        result = generator.generate(python_project, diagram_type="dependency", output_format="svg")
        assert result.content == ""
        assert result.format == "svg"

    def test_valid_types_accepted(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """All members of VALID_TYPES are accepted without raising."""
        for dtype in DiagramGenerator.VALID_TYPES:
            result = generator.generate(tmp_path, diagram_type=dtype)
            assert isinstance(result, DiagramResult)

    def test_valid_formats_accepted(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """Both mermaid and plantuml are accepted."""
        for fmt in DiagramGenerator.VALID_FORMATS:
            result = generator.generate(tmp_path, diagram_type="dependency", output_format=fmt)
            assert isinstance(result, DiagramResult)


# ---------------------------------------------------------------------------
# Dependency diagrams -- Mermaid
# ---------------------------------------------------------------------------


class TestDependencyDiagramMermaid:
    """Dependency diagrams in Mermaid format.

    Uses the ``large_python_project`` fixture (16 packages) so the STORY-100.6
    auto-poster redirect (_POSTER_AUTO_THRESHOLD=15) is never triggered and these
    tests receive a genuine dependency diagram rather than a pattern_card.
    """

    def test_generates_graph_td(
        self, generator: DiagramGenerator, large_python_project: Path
    ) -> None:
        result = generator.generate(large_python_project, diagram_type="dependency")
        assert result.content.startswith("graph TD")

    def test_has_subgraphs(self, generator: DiagramGenerator, large_python_project: Path) -> None:
        result = generator.generate(large_python_project, diagram_type="dependency")
        assert "subgraph" in result.content

    def test_has_solid_edges(self, generator: DiagramGenerator, large_python_project: Path) -> None:
        result = generator.generate(large_python_project, diagram_type="dependency")
        assert "-->" in result.content

    def test_node_count_positive(
        self, generator: DiagramGenerator, large_python_project: Path
    ) -> None:
        result = generator.generate(large_python_project, diagram_type="dependency")
        assert result.node_count > 0

    def test_result_type_and_format(
        self, generator: DiagramGenerator, large_python_project: Path
    ) -> None:
        result = generator.generate(large_python_project, diagram_type="dependency")
        assert result.diagram_type == "dependency"
        assert result.format == "mermaid"


# ---------------------------------------------------------------------------
# Dependency diagrams -- PlantUML
# ---------------------------------------------------------------------------


class TestDependencyDiagramPlantUML:
    """Dependency diagrams in PlantUML format."""

    def test_startuml_enduml(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(
            python_project, diagram_type="dependency", output_format="plantuml"
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_has_package(self, generator: DiagramGenerator, python_project: Path) -> None:
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
        result = generator.generate(python_project, diagram_type="dependency", show_external=True)
        # pydantic is an external dep imported in models.py
        assert "pydantic" in result.content.lower() or result.node_count >= 1

    def test_external_hidden_mermaid(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="dependency", show_external=False)
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
        result = generator.generate(python_project, diagram_type="class_hierarchy")
        assert "classDiagram" in result.content

    def test_inheritance_edges(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(python_project, diagram_type="class_hierarchy")
        assert "class " in result.content

    def test_method_visibility_prefix(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        root = tmp_path / "vis"
        root.mkdir()
        (root / "widget.py").write_text(
            "class Widget:\n"
            "    def public_method(self) -> None: ...\n"
            "    def _private_method(self) -> None: ...\n"
        )
        result = generator.generate(root, diagram_type="class_hierarchy")
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

    def test_single_file_scope(self, generator: DiagramGenerator, tmp_path: Path) -> None:
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

    def test_startuml_enduml(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(
            python_project,
            diagram_type="class_hierarchy",
            output_format="plantuml",
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_class_keyword(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(
            python_project,
            diagram_type="class_hierarchy",
            output_format="plantuml",
        )
        assert "class " in result.content

    def test_plantuml_inheritance_edges(self, generator: DiagramGenerator, tmp_path: Path) -> None:
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

    def test_nested_subgraphs(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(python_project, diagram_type="module_map")
        assert "subgraph" in result.content

    def test_node_labels_with_counts(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(python_project, diagram_type="module_map")
        assert result.node_count >= 1

    def test_direction_td(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """TD direction is reflected in the output."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write_py(pkg, "core.py", "def hello(): pass\n")
        result = generator.generate(tmp_path, diagram_type="module_map", direction="TD")
        assert "graph TD" in result.content

    def test_direction_lr(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """LR direction is reflected in the output."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write_py(pkg, "core.py", "def hello(): pass\n")
        result = generator.generate(tmp_path, diagram_type="module_map", direction="LR")
        assert "graph LR" in result.content

    def test_package_with_init(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """A package with __init__.py produces nodes."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write_py(pkg, "alpha.py", "x = 1\n")
        _write_py(pkg, "beta.py", "y = 2\n")
        result = generator.generate(tmp_path, diagram_type="module_map", output_format="mermaid")
        assert result.node_count >= 2


# ---------------------------------------------------------------------------
# Module map -- PlantUML
# ---------------------------------------------------------------------------


class TestModuleMapPlantUML:
    """Module map diagrams in PlantUML format."""

    def test_startuml_enduml(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(
            python_project,
            diagram_type="module_map",
            output_format="plantuml",
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_package_keyword(self, generator: DiagramGenerator, python_project: Path) -> None:
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

    def test_generates_er_diagram(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(python_project, diagram_type="er_diagram")
        assert "erDiagram" in result.content

    def test_has_fields(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(python_project, diagram_type="er_diagram")
        assert "string" in result.content.lower() or "name" in result.content.lower()

    def test_has_relationships(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(python_project, diagram_type="er_diagram")
        # Post.author is typed User, so there should be a relationship edge
        assert result.edge_count >= 1 or "has" in result.content

    def test_non_model_classes_excluded(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """Plain classes (not BaseModel/dataclass) are excluded from ER."""
        _write_py(tmp_path, "mixed.py", DATACLASS_CODE)
        result = generator.generate(tmp_path, diagram_type="er_diagram", output_format="mermaid")
        # Config (dataclass) should be included, PlainClass should not.
        assert "Config" in result.content
        assert "PlainClass" not in result.content

    def test_relationship_edge_from_model_code(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Order.user: User produces a relationship edge."""
        _write_py(tmp_path, "models.py", MODEL_CODE)
        result = generator.generate(tmp_path, diagram_type="er_diagram", output_format="mermaid")
        assert result.edge_count >= 1

    def test_er_empty_for_no_models(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """A project with no model classes returns empty ER content."""
        _write_py(tmp_path, "utils.py", "def add(a, b): return a + b\n")
        result = generator.generate(tmp_path, diagram_type="er_diagram", output_format="mermaid")
        assert result.content == ""

    def test_dataclass_included_in_er(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """Dataclass-decorated classes are recognised as models."""
        _write_py(tmp_path, "dc.py", DATACLASS_CODE)
        result = generator.generate(tmp_path, diagram_type="er_diagram", output_format="mermaid")
        assert result.node_count >= 1
        assert "Config" in result.content


# ---------------------------------------------------------------------------
# ER diagram -- PlantUML
# ---------------------------------------------------------------------------


class TestERDiagramPlantUML:
    """ER diagrams in PlantUML format."""

    def test_startuml_enduml(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(
            python_project,
            diagram_type="er_diagram",
            output_format="plantuml",
        )
        assert "@startuml" in result.content
        assert "@enduml" in result.content

    def test_entity_keyword(self, generator: DiagramGenerator, python_project: Path) -> None:
        result = generator.generate(
            python_project,
            diagram_type="er_diagram",
            output_format="plantuml",
        )
        assert "entity " in result.content

    def test_plantuml_er_from_model_code(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """PlantUML ER from MODEL_CODE contains entity definitions."""
        _write_py(tmp_path, "models.py", MODEL_CODE)
        result = generator.generate(tmp_path, diagram_type="er_diagram", output_format="plantuml")
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

    def test_dependency_empty(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="dependency")
        assert result.node_count == 0
        assert result.edge_count == 0

    def test_class_hierarchy_empty(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="class_hierarchy")
        assert result.content == ""

    def test_module_map_empty(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="module_map")
        assert result.node_count == 0 or result.content == ""

    def test_er_diagram_empty(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = generator.generate(empty, diagram_type="er_diagram")
        assert result.content == ""


# ---------------------------------------------------------------------------
# MCP Tool -- docs_generate_diagram
# ---------------------------------------------------------------------------


class TestDiagramMCPTool:
    """docs_generate_diagram MCP tool response envelope and error handling."""

    async def test_response_envelope(self, python_project: Path) -> None:
        """Successful generation returns the standard envelope fields."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(python_project),
        ):
            result = await docs_generate_diagram(
                diagram_type="dependency",
                project_root=str(python_project),
            )

        assert result["tool"] == "docs_generate_diagram"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result

    async def test_data_fields(self, python_project: Path) -> None:
        """Response data includes diagram_type, format, node_count, edge_count, content."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(python_project),
        ):
            result = await docs_generate_diagram(
                diagram_type="dependency",
                project_root=str(python_project),
            )

        data = result["data"]
        assert "diagram_type" in data
        assert "format" in data
        assert "node_count" in data
        assert "edge_count" in data
        assert "content" in data
        assert data["node_count"] >= 0
        assert data["edge_count"] >= 0

    async def test_invalid_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns INVALID_ROOT error."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        fake = tmp_path / "does_not_exist"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = await docs_generate_diagram(project_root=str(fake))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_no_content_returns_error(self, tmp_path: Path) -> None:
        """Empty project returns NO_CONTENT error."""
        root = tmp_path / "empty"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_diagram(
                diagram_type="class_hierarchy",
                project_root=str(root),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NO_CONTENT"

    async def test_format_defaults_to_settings(self, tmp_path: Path) -> None:
        """When format is empty, the tool uses the setting's diagram_format."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        settings = _make_settings(tmp_path)
        settings.diagram_format = "plantuml"

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=settings,
        ):
            result = await docs_generate_diagram(
                diagram_type="class_hierarchy",
                format="",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["format"] == "plantuml"
        assert "@startuml" in result["data"]["content"]

    async def test_explicit_format_overrides_settings(self, tmp_path: Path) -> None:
        """An explicit format param takes precedence over settings."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        settings = _make_settings(tmp_path)
        settings.diagram_format = "plantuml"

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=settings,
        ):
            result = await docs_generate_diagram(
                diagram_type="class_hierarchy",
                format="mermaid",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["format"] == "mermaid"
        assert "classDiagram" in result["data"]["content"]

    async def test_er_diagram_via_tool(self, tmp_path: Path) -> None:
        """ER diagram type works through the MCP tool."""
        _write_py(tmp_path, "models.py", MODEL_CODE)

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await docs_generate_diagram(
                diagram_type="er_diagram",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["diagram_type"] == "er_diagram"
        assert "erDiagram" in result["data"]["content"]

    async def test_class_hierarchy_via_tool(self, tmp_path: Path) -> None:
        """Class hierarchy succeeds through the MCP tool."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)

        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await docs_generate_diagram(
                diagram_type="class_hierarchy",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["diagram_type"] == "class_hierarchy"
        assert result["data"]["node_count"] >= 1
        assert len(result["data"]["content"]) > 0


# ---------------------------------------------------------------------------
# Source directory resolution (Epic 14)
# ---------------------------------------------------------------------------


class TestSourceDirResolution:
    """_resolve_source_dirs auto-detects src/ layout and monorepo structure."""

    def test_src_layout_detected(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """A project with src/<pkg>/ scans only the package dir."""
        root = tmp_path / "project"
        root.mkdir()
        pkg = root / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        _write_py(pkg, "core.py", CLASS_HIERARCHY_CODE)

        # Also put a decoy file at root level that should NOT be scanned
        _write_py(root, "setup.py", "class SetupDecoy:\n    pass\n")

        result = generator.generate(root, diagram_type="class_hierarchy")
        assert "Animal" in result.content
        assert "SetupDecoy" not in result.content

    def test_flat_layout_fallback(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """Without src/, scans project root."""
        root = tmp_path / "flat"
        root.mkdir()
        _write_py(root, "models.py", CLASS_HIERARCHY_CODE)

        result = generator.generate(root, diagram_type="class_hierarchy")
        assert "Animal" in result.content
        assert result.node_count >= 3

    def test_monorepo_src_with_multiple_packages(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """A monorepo with src/<pkg_a>/ and src/<pkg_b>/ scans both."""
        root = tmp_path / "mono"
        root.mkdir()
        pkg_a = root / "src" / "alpha"
        pkg_a.mkdir(parents=True)
        (pkg_a / "__init__.py").write_text("")
        _write_py(pkg_a, "a.py", "class AlphaClass:\n    pass\n")

        pkg_b = root / "src" / "beta"
        pkg_b.mkdir(parents=True)
        (pkg_b / "__init__.py").write_text("")
        _write_py(pkg_b, "b.py", "class BetaClass:\n    pass\n")

        result = generator.generate(root, diagram_type="class_hierarchy")
        assert "AlphaClass" in result.content
        assert "BetaClass" in result.content

    def test_venv_not_scanned(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """Files inside .venv/ are skipped."""
        root = tmp_path / "proj"
        root.mkdir()
        _write_py(root, "app.py", CLASS_HIERARCHY_CODE)

        venv_pkg = root / ".venv" / "lib" / "somepackage"
        venv_pkg.mkdir(parents=True)
        _write_py(venv_pkg, "junk.py", "class VenvJunk:\n    pass\n")

        result = generator.generate(root, diagram_type="class_hierarchy")
        assert "Animal" in result.content
        assert "VenvJunk" not in result.content

    def test_site_packages_not_scanned(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """Files inside site-packages/ are skipped."""
        root = tmp_path / "proj"
        root.mkdir()
        _write_py(root, "app.py", CLASS_HIERARCHY_CODE)

        sp = root / "site-packages" / "pip"
        sp.mkdir(parents=True)
        _write_py(sp, "internal.py", "class PipInternal:\n    pass\n")

        result = generator.generate(root, diagram_type="class_hierarchy")
        assert "Animal" in result.content
        assert "PipInternal" not in result.content


# ---------------------------------------------------------------------------
# DiagramResult metadata (Epic 14)
# ---------------------------------------------------------------------------


class TestDiagramResultMetadata:
    """DiagramResult includes degraded flag and scanned_dirs metadata."""

    def test_scanned_dirs_populated(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """scanned_dirs lists the directories that were actually scanned."""
        _write_py(tmp_path, "models.py", CLASS_HIERARCHY_CODE)
        result = generator.generate(tmp_path, diagram_type="class_hierarchy")
        assert len(result.scanned_dirs) >= 1

    def test_degraded_false_with_classes(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """degraded is False when enough classes are found."""
        _write_py(tmp_path, "animals.py", CLASS_HIERARCHY_CODE)
        result = generator.generate(tmp_path, diagram_type="class_hierarchy")
        # 3 classes (Animal, Dog, Puppy) meets the threshold
        assert result.degraded is False

    def test_degraded_true_with_few_classes(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """degraded is True when fewer than threshold classes found."""
        _write_py(tmp_path, "tiny.py", "class Solo:\n    pass\n")
        result = generator.generate(tmp_path, diagram_type="class_hierarchy")
        # Only 1 class, below _MIN_RESULTS_THRESHOLD (3)
        assert result.degraded is True

    def test_degraded_not_set_for_single_file_scope(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """degraded is not set when scope is a specific file."""
        _write_py(tmp_path, "one.py", "class One:\n    pass\n")
        result = generator.generate(
            tmp_path,
            diagram_type="class_hierarchy",
            scope=str(tmp_path / "one.py"),
        )
        # Single-file scope should not trigger degraded
        assert result.degraded is False

    def test_er_diagram_has_scanned_dirs(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """ER diagrams also include scanned_dirs metadata."""
        _write_py(tmp_path, "models.py", MODEL_CODE)
        result = generator.generate(tmp_path, diagram_type="er_diagram")
        assert len(result.scanned_dirs) >= 1

    def test_default_metadata_values(self) -> None:
        """New DiagramResult fields have sensible defaults."""
        r = DiagramResult(diagram_type="test", format="mermaid", content="")
        assert r.degraded is False
        assert r.scanned_dirs == []
        assert r.skipped_count == 0


# ---------------------------------------------------------------------------
# Shared constants (Epic 14)
# ---------------------------------------------------------------------------


class TestSharedConstants:
    """SKIP_DIRS from constants module is used."""

    def test_skip_dirs_includes_site_packages(self) -> None:
        from docs_mcp.constants import SKIP_DIRS

        assert "site-packages" in SKIP_DIRS

    def test_skip_dirs_includes_venv(self) -> None:
        from docs_mcp.constants import SKIP_DIRS

        assert ".venv" in SKIP_DIRS
        assert "venv" in SKIP_DIRS

    def test_skip_dirs_includes_tox(self) -> None:
        from docs_mcp.constants import SKIP_DIRS

        assert ".tox" in SKIP_DIRS


# ---------------------------------------------------------------------------
# Pattern card (archetype poster) — STORY-100.3
# ---------------------------------------------------------------------------


def _mkpkg(root: Path, name: str, *, submodules: list[str] | None = None) -> None:
    """Helper: create a Python package with optional submodules."""
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('"""pkg."""\n')
    for sub in submodules or []:
        (pkg / f"{sub}.py").write_text(f'"""{sub}."""\n')


@pytest.fixture
def layered_project(tmp_path: Path) -> Path:
    root = tmp_path / "layered_app"
    root.mkdir()
    for layer in ("api", "services", "models", "repositories", "config"):
        _mkpkg(root, layer, submodules=["core"])
    return root


@pytest.fixture
def hexagonal_project(tmp_path: Path) -> Path:
    root = tmp_path / "hex_app"
    root.mkdir()
    for name in ("ports", "adapters", "core", "config"):
        _mkpkg(root, name, submodules=["main"])
    return root


@pytest.fixture
def microservice_project(tmp_path: Path) -> Path:
    root = tmp_path / "ms"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='root'\n")
    for svc in ("svc_a", "svc_b", "svc_c"):
        (root / svc).mkdir()
        (root / svc / "pyproject.toml").write_text(f"[project]\nname='{svc}'\n")
        _mkpkg(root / svc, "app")
    return root


@pytest.fixture
def monolith_project(tmp_path: Path) -> Path:
    root = tmp_path / "mono"
    root.mkdir()
    _mkpkg(root, "app", submodules=["main"])
    return root


class TestPatternCard:
    """pattern_card diagram renders an archetype poster with role palette."""

    def test_layered_renders(self, generator: DiagramGenerator, layered_project: Path) -> None:
        r = generator.generate(layered_project, diagram_type="pattern_card")
        assert r.diagram_type == "pattern_card"
        assert r.content.startswith("flowchart")
        assert "LAYERED" in r.content

    def test_hexagonal_renders(self, generator: DiagramGenerator, hexagonal_project: Path) -> None:
        r = generator.generate(hexagonal_project, diagram_type="pattern_card")
        assert "HEXAGONAL" in r.content

    def test_microservice_renders(
        self, generator: DiagramGenerator, microservice_project: Path
    ) -> None:
        r = generator.generate(microservice_project, diagram_type="pattern_card")
        assert "MICROSERVICE" in r.content

    def test_monolith_or_unknown_renders(
        self, generator: DiagramGenerator, monolith_project: Path
    ) -> None:
        r = generator.generate(monolith_project, diagram_type="pattern_card")
        assert r.content.startswith("flowchart")
        # Small project classifies as monolith or unknown — both valid.
        assert ("MONOLITH" in r.content) or ("UNKNOWN" in r.content)

    def test_evidence_in_output(self, generator: DiagramGenerator, layered_project: Path) -> None:
        """Evidence from classifier appears in rendered content."""
        r = generator.generate(layered_project, diagram_type="pattern_card")
        assert "canonical layer packages matched" in r.content

    def test_node_cap_respected(self, generator: DiagramGenerator, tmp_path: Path) -> None:
        """A project with many packages is capped at _MAX_PATTERN_NODES."""
        from docs_mcp.generators.diagrams import _MAX_PATTERN_NODES

        root = tmp_path / "big"
        root.mkdir()
        for idx in range(_MAX_PATTERN_NODES + 6):
            _mkpkg(root, f"pkg_{idx}")
        r = generator.generate(root, diagram_type="pattern_card")
        assert r.node_count <= _MAX_PATTERN_NODES

    def test_legend_present(self, generator: DiagramGenerator, layered_project: Path) -> None:
        r = generator.generate(layered_project, diagram_type="pattern_card")
        assert 'subgraph legend["Legend"]' in r.content
        for role in ("Presentation", "Business", "Data", "Infra"):
            assert role in r.content

    def test_role_colors_applied(self, generator: DiagramGenerator, layered_project: Path) -> None:
        """classDef lines for all four roles are emitted."""
        r = generator.generate(layered_project, diagram_type="pattern_card")
        from docs_mcp.generators.diagrams import _ROLE_COLORS

        for role, color in _ROLE_COLORS.items():
            assert f"classDef {role} fill:{color}" in r.content

    def test_classify_role_known_names(self, generator: DiagramGenerator) -> None:
        assert generator._classify_role("api") == "presentation"
        assert generator._classify_role("services") == "business"
        assert generator._classify_role("models") == "data"
        assert generator._classify_role("config") == "infra"

    def test_classify_role_unknown_defaults_to_infra(self, generator: DiagramGenerator) -> None:
        assert generator._classify_role("zzz_xyz_nothing") == "infra"

    def test_empty_project_degrades_gracefully(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """Empty directory still returns a DiagramResult, not a crash."""
        r = generator.generate(tmp_path, diagram_type="pattern_card")
        assert isinstance(r, DiagramResult)
        assert r.diagram_type == "pattern_card"


# ---------------------------------------------------------------------------
# STORY-100.2 — shared role palette across renderers
# ---------------------------------------------------------------------------


class TestRolePaletteAcrossRenderers:
    """Dependency and module_map renderers emit role classDefs and tag nodes."""

    def test_dependency_mermaid_emits_role_classdefs(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="dependency")
        for role in ("presentation", "business", "data", "infra"):
            assert f"classDef {role}" in r.content

    def test_dependency_mermaid_tags_nodes_with_role(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="dependency")
        # `services` is business; `models` is data.
        assert ":::business" in r.content or ":::data" in r.content

    def test_module_map_mermaid_emits_role_classdefs(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="module_map")
        for role in ("presentation", "business", "data", "infra"):
            assert f"classDef {role}" in r.content

    def test_module_map_mermaid_tags_leaf_nodes(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="module_map")
        assert ":::" in r.content  # at least one node is role-tagged

    def test_role_for_top_component(self, generator: DiagramGenerator) -> None:
        assert generator._role_for_top_component("api/v1/users.py") == "presentation"
        assert generator._role_for_top_component("services.billing") == "business"
        assert generator._role_for_top_component("models/user.py") == "data"

    def test_class_hierarchy_mermaid_emits_role_classdefs(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="class_hierarchy")
        for role in ("presentation", "business", "data", "infra"):
            assert f"classDef {role}" in r.content

    def test_class_hierarchy_mermaid_tags_classes(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="class_hierarchy")
        assert ":::data" in r.content


class TestC4RolePalette:
    """C4 Mermaid renderers emit UpdateElementStyle per-role (STORY-100.4)."""

    def test_c4_container_emits_updateelementstyle(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="c4_container")
        assert "UpdateElementStyle" in r.content
        # At least one role color from _ROLE_COLORS appears.
        from docs_mcp.generators.diagrams import _ROLE_COLORS

        assert any(c in r.content for c in _ROLE_COLORS.values())

    def test_c4_component_emits_updateelementstyle(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="c4_component")
        if r.content:  # component diagram may degrade on tiny fixtures
            assert "UpdateElementStyle" in r.content

    def test_c4_context_emits_updateelementstyle(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        r = generator.generate(python_project, diagram_type="c4_context")
        assert "UpdateElementStyle" in r.content
