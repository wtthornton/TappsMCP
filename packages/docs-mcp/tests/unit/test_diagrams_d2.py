"""Tests for D2 diagram format support (Epic 81.1, 81.2, 81.4).

Covers:
- D2 output for all 8 diagram types (dependency, class_hierarchy, module_map,
  er_diagram, c4_context, c4_container, c4_component, sequence)
- D2 theme system (default, sketch, terminal)
- D2 format validation and acceptance
- docs_generate_diagram MCP tool with format=d2 and theme parameter
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.diagrams import DiagramGenerator, DiagramResult


# ---------------------------------------------------------------------------
# Sample source snippets
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


@pytest.fixture
def class_project(tmp_path: Path) -> Path:
    """Create a project with a class hierarchy."""
    root = tmp_path / "cls_proj"
    root.mkdir()
    src = root / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "animals.py").write_text(CLASS_HIERARCHY_CODE)
    return root


@pytest.fixture
def model_project(tmp_path: Path) -> Path:
    """Create a project with Pydantic models for ER diagrams."""
    root = tmp_path / "model_proj"
    root.mkdir()
    src = root / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "models.py").write_text(MODEL_CODE)
    return root


# ---------------------------------------------------------------------------
# D2 format acceptance
# ---------------------------------------------------------------------------


class TestD2FormatValidation:
    """D2 is a valid format option."""

    def test_d2_in_valid_formats(self) -> None:
        """d2 is listed in DiagramGenerator.VALID_FORMATS."""
        assert "d2" in DiagramGenerator.VALID_FORMATS

    def test_d2_accepted_by_generate(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """D2 format does not return empty due to validation."""
        result = generator.generate(
            tmp_path, diagram_type="dependency", output_format="d2"
        )
        assert isinstance(result, DiagramResult)
        assert result.format == "d2"


# ---------------------------------------------------------------------------
# D2 theme system (Story 81.4)
# ---------------------------------------------------------------------------


class TestD2ThemeSystem:
    """D2 theme support for default, sketch, and terminal."""

    def test_valid_themes(self) -> None:
        """VALID_THEMES contains all three themes."""
        assert "default" in DiagramGenerator.VALID_THEMES
        assert "sketch" in DiagramGenerator.VALID_THEMES
        assert "terminal" in DiagramGenerator.VALID_THEMES

    def test_default_theme_no_directives(
        self, generator: DiagramGenerator
    ) -> None:
        """Default theme produces no extra D2 directives."""
        generator._d2_theme = "default"
        block = generator._d2_theme_block()
        assert block == []

    def test_sketch_theme_directives(
        self, generator: DiagramGenerator
    ) -> None:
        """Sketch theme emits sketch: true."""
        generator._d2_theme = "sketch"
        block = generator._d2_theme_block()
        assert any("sketch: true" in line for line in block)

    def test_terminal_theme_directives(
        self, generator: DiagramGenerator
    ) -> None:
        """Terminal theme emits theme-id: 200."""
        generator._d2_theme = "terminal"
        block = generator._d2_theme_block()
        assert any("theme-id: 200" in line for line in block)

    def test_theme_passed_through_generate(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """Theme parameter is stored and used in D2 output."""
        result = generator.generate(
            class_project,
            diagram_type="class_hierarchy",
            output_format="d2",
            theme="sketch",
        )
        assert "sketch: true" in result.content

    def test_invalid_theme_defaults_to_default(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """Invalid theme falls back to default (no directives)."""
        result = generator.generate(
            class_project,
            diagram_type="class_hierarchy",
            output_format="d2",
            theme="invalid_theme",
        )
        assert "sketch" not in result.content
        assert "theme-id" not in result.content


# ---------------------------------------------------------------------------
# D2: dependency diagrams (Story 81.1)
# ---------------------------------------------------------------------------


class TestDependencyD2:
    """Dependency diagram in D2 format."""

    def test_dependency_d2_basic(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 dependency diagram produces valid output."""
        result = generator.generate(
            python_project, diagram_type="dependency", output_format="d2"
        )
        assert result.format == "d2"
        assert result.diagram_type == "dependency"
        assert "direction:" in result.content

    def test_dependency_d2_has_nodes(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 dependency diagram includes module nodes."""
        result = generator.generate(
            python_project, diagram_type="dependency", output_format="d2"
        )
        assert result.node_count > 0

    def test_dependency_d2_direction_lr(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """LR direction maps to D2 'direction: right'."""
        result = generator.generate(
            python_project,
            diagram_type="dependency",
            output_format="d2",
            direction="LR",
        )
        assert "direction: right" in result.content

    def test_dependency_d2_direction_td(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """TD direction maps to D2 'direction: down'."""
        result = generator.generate(
            python_project,
            diagram_type="dependency",
            output_format="d2",
            direction="TD",
        )
        assert "direction: down" in result.content


# ---------------------------------------------------------------------------
# D2: class hierarchy diagrams (Story 81.1)
# ---------------------------------------------------------------------------


class TestClassHierarchyD2:
    """Class hierarchy diagram in D2 format."""

    def test_class_d2_basic(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """D2 class diagram produces valid output with class shapes."""
        result = generator.generate(
            class_project, diagram_type="class_hierarchy", output_format="d2"
        )
        assert result.format == "d2"
        assert result.content != ""
        assert "shape: class" in result.content

    def test_class_d2_has_nodes(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """D2 class diagram includes correct node count."""
        result = generator.generate(
            class_project, diagram_type="class_hierarchy", output_format="d2"
        )
        assert result.node_count == 3  # Animal, Dog, Puppy

    def test_class_d2_has_inheritance_edges(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """D2 class diagram renders inheritance with dashed arrows."""
        result = generator.generate(
            class_project, diagram_type="class_hierarchy", output_format="d2"
        )
        assert result.edge_count == 2  # Dog->Animal, Puppy->Dog
        assert "stroke-dash" in result.content

    def test_class_d2_includes_methods(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """D2 class diagram includes method declarations."""
        result = generator.generate(
            class_project, diagram_type="class_hierarchy", output_format="d2"
        )
        assert "speak()" in result.content

    def test_class_d2_includes_attributes(
        self, generator: DiagramGenerator, class_project: Path
    ) -> None:
        """D2 class diagram includes class variable attributes."""
        result = generator.generate(
            class_project, diagram_type="class_hierarchy", output_format="d2"
        )
        assert "+name" in result.content


# ---------------------------------------------------------------------------
# D2: module map diagrams (Story 81.1)
# ---------------------------------------------------------------------------


class TestModuleMapD2:
    """Module map diagram in D2 format."""

    def test_module_map_d2_basic(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 module map produces valid output with nested containers."""
        result = generator.generate(
            python_project, diagram_type="module_map", output_format="d2"
        )
        assert result.format == "d2"
        assert result.content != ""
        assert "direction:" in result.content

    def test_module_map_d2_has_nodes(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 module map includes package modules."""
        result = generator.generate(
            python_project, diagram_type="module_map", output_format="d2"
        )
        assert result.node_count > 0

    def test_module_map_d2_uses_containers(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 module map uses nested containers via {}."""
        result = generator.generate(
            python_project, diagram_type="module_map", output_format="d2"
        )
        assert "{" in result.content


# ---------------------------------------------------------------------------
# D2: ER diagrams (Story 81.1)
# ---------------------------------------------------------------------------


class TestERDiagramD2:
    """ER diagram in D2 format."""

    def test_er_d2_basic(
        self, generator: DiagramGenerator, model_project: Path
    ) -> None:
        """D2 ER diagram produces valid output with sql_table shapes."""
        result = generator.generate(
            model_project, diagram_type="er_diagram", output_format="d2"
        )
        assert result.format == "d2"
        assert result.content != ""
        assert "shape: sql_table" in result.content

    def test_er_d2_has_models(
        self, generator: DiagramGenerator, model_project: Path
    ) -> None:
        """D2 ER diagram includes model entities."""
        result = generator.generate(
            model_project, diagram_type="er_diagram", output_format="d2"
        )
        assert result.node_count == 2  # User, Order
        assert "User" in result.content
        assert "Order" in result.content

    def test_er_d2_has_relationship_edges(
        self, generator: DiagramGenerator, model_project: Path
    ) -> None:
        """D2 ER diagram renders relationships."""
        result = generator.generate(
            model_project, diagram_type="er_diagram", output_format="d2"
        )
        assert result.edge_count > 0
        assert "has" in result.content

    def test_er_d2_field_types(
        self, generator: DiagramGenerator, model_project: Path
    ) -> None:
        """D2 ER diagram maps Python types to ER types."""
        result = generator.generate(
            model_project, diagram_type="er_diagram", output_format="d2"
        )
        assert "string" in result.content  # str -> string
        assert "float" in result.content


# ---------------------------------------------------------------------------
# D2: C4 context diagrams (Story 81.2)
# ---------------------------------------------------------------------------


class TestC4ContextD2:
    """C4 System Context diagram in D2 format."""

    def test_c4_context_d2_basic(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 context diagram produces valid output."""
        result = generator.generate(
            python_project, diagram_type="c4_context", output_format="d2"
        )
        assert result.format == "d2"
        assert result.content != ""
        assert result.node_count >= 2

    def test_c4_context_d2_has_actors(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 context diagram has actor shapes."""
        result = generator.generate(
            python_project, diagram_type="c4_context", output_format="d2"
        )
        assert "shape:" in result.content

    def test_c4_context_d2_has_relationships(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 context diagram includes relationship edges."""
        result = generator.generate(
            python_project, diagram_type="c4_context", output_format="d2"
        )
        assert result.edge_count > 0
        assert "Uses" in result.content


# ---------------------------------------------------------------------------
# D2: C4 container diagrams (Story 81.2)
# ---------------------------------------------------------------------------


class TestC4ContainerD2:
    """C4 Container diagram in D2 format."""

    def test_c4_container_d2_basic(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 container diagram produces valid output."""
        result = generator.generate(
            python_project, diagram_type="c4_container", output_format="d2"
        )
        assert result.format == "d2"
        assert result.content != ""
        assert result.node_count > 0

    def test_c4_container_d2_nested(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 container diagram uses D2 nested containers."""
        result = generator.generate(
            python_project, diagram_type="c4_container", output_format="d2"
        )
        assert "{" in result.content


# ---------------------------------------------------------------------------
# D2: C4 component diagrams (Story 81.2)
# ---------------------------------------------------------------------------


class TestC4ComponentD2:
    """C4 Component diagram in D2 format."""

    def test_c4_component_d2_basic(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 component diagram produces valid output."""
        result = generator.generate(
            python_project, diagram_type="c4_component", output_format="d2"
        )
        assert result.format == "d2"
        assert isinstance(result, DiagramResult)

    def test_c4_component_d2_with_scope(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 C4 component diagram with scoped package."""
        result = generator.generate(
            python_project,
            diagram_type="c4_component",
            output_format="d2",
            scope="myapp",
        )
        assert result.format == "d2"


# ---------------------------------------------------------------------------
# D2: sequence diagrams (Story 81.2)
# ---------------------------------------------------------------------------


class TestSequenceD2:
    """Sequence diagram in D2 format."""

    def test_sequence_d2_from_spec(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """D2 sequence diagram renders from flow_spec JSON."""
        import json

        spec = json.dumps({
            "title": "Login Flow",
            "participants": ["Client", "Server", "Database"],
            "messages": [
                {"from": "Client", "to": "Server", "label": "POST /login"},
                {"from": "Server", "to": "Database", "label": "SELECT user"},
                {"from": "Database", "to": "Server", "label": "result",
                 "type": "reply"},
                {"from": "Server", "to": "Client", "label": "200 OK",
                 "type": "reply"},
            ],
        })
        result = generator.generate(
            tmp_path,
            diagram_type="sequence",
            output_format="d2",
            flow_spec=spec,
        )
        assert result.format == "d2"
        assert "shape: sequence_diagram" in result.content
        assert "Login Flow" in result.content
        assert result.node_count == 3
        assert result.edge_count == 4

    def test_sequence_d2_sync_messages(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """D2 sequence diagram renders sync messages as solid arrows."""
        import json

        spec = json.dumps({
            "participants": ["A", "B"],
            "messages": [
                {"from": "A", "to": "B", "label": "call"},
            ],
        })
        result = generator.generate(
            tmp_path,
            diagram_type="sequence",
            output_format="d2",
            flow_spec=spec,
        )
        assert "A -> B: call" in result.content
        assert "stroke-dash" not in result.content.split("A -> B: call")[1].split("\n")[0]

    def test_sequence_d2_reply_messages(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """D2 sequence diagram renders reply messages with dashed stroke."""
        import json

        spec = json.dumps({
            "participants": ["A", "B"],
            "messages": [
                {"from": "A", "to": "B", "label": "response", "type": "reply"},
            ],
        })
        result = generator.generate(
            tmp_path,
            diagram_type="sequence",
            output_format="d2",
            flow_spec=spec,
        )
        assert "stroke-dash: 3" in result.content

    def test_sequence_d2_async_messages(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """D2 sequence diagram renders async messages with longer dashes."""
        import json

        spec = json.dumps({
            "participants": ["A", "B"],
            "messages": [
                {"from": "A", "to": "B", "label": "fire", "type": "async"},
            ],
        })
        result = generator.generate(
            tmp_path,
            diagram_type="sequence",
            output_format="d2",
            flow_spec=spec,
        )
        assert "stroke-dash: 5" in result.content

    def test_sequence_d2_with_notes(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        """D2 sequence diagram renders notes."""
        import json

        spec = json.dumps({
            "participants": ["Client", "Server"],
            "messages": [
                {"from": "Client", "to": "Server", "label": "request"},
            ],
            "notes": [
                {"over": "Server", "text": "Validates token"},
            ],
        })
        result = generator.generate(
            tmp_path,
            diagram_type="sequence",
            output_format="d2",
            flow_spec=spec,
        )
        assert "Validates token" in result.content

    def test_sequence_d2_auto_detect(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        """D2 sequence diagram auto-detects from import graph."""
        result = generator.generate(
            python_project, diagram_type="sequence", output_format="d2"
        )
        assert result.format == "d2"
        if result.content:
            assert "shape: sequence_diagram" in result.content


# ---------------------------------------------------------------------------
# D2 with themes across diagram types
# ---------------------------------------------------------------------------


class TestD2ThemesAcrossTypes:
    """Verify theme integration works across all diagram types."""

    def test_sketch_theme_in_dependency(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="dependency",
            output_format="d2",
            theme="sketch",
        )
        assert "sketch: true" in result.content

    def test_terminal_theme_in_er(
        self, generator: DiagramGenerator, model_project: Path
    ) -> None:
        result = generator.generate(
            model_project,
            diagram_type="er_diagram",
            output_format="d2",
            theme="terminal",
        )
        assert "theme-id: 200" in result.content

    def test_sketch_theme_in_c4_context(
        self, generator: DiagramGenerator, python_project: Path
    ) -> None:
        result = generator.generate(
            python_project,
            diagram_type="c4_context",
            output_format="d2",
            theme="sketch",
        )
        assert "sketch: true" in result.content

    def test_terminal_theme_in_sequence(
        self, generator: DiagramGenerator, tmp_path: Path
    ) -> None:
        import json

        spec = json.dumps({
            "participants": ["A", "B"],
            "messages": [{"from": "A", "to": "B", "label": "call"}],
        })
        result = generator.generate(
            tmp_path,
            diagram_type="sequence",
            output_format="d2",
            flow_spec=spec,
            theme="terminal",
        )
        assert "theme-id: 200" in result.content


# ---------------------------------------------------------------------------
# MCP tool envelope (docs_generate_diagram with D2)
# ---------------------------------------------------------------------------


class TestDocsGenerateDiagramD2:
    """docs_generate_diagram MCP tool with D2 format and theme."""

    def test_tool_accepts_d2_format(self, python_project: Path) -> None:
        """MCP tool generates D2 output when format=d2."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(python_project),
        ), patch("docs_mcp.server_gen_tools._record_call"):
            result = _run(docs_generate_diagram(
                diagram_type="class_hierarchy",
                format="d2",
                project_root=str(python_project),
            ))

        assert result.get("success") is True
        data = result.get("data", {})
        assert data.get("format") == "d2"
        assert "shape: class" in data.get("content", "")

    def test_tool_accepts_theme_parameter(self, python_project: Path) -> None:
        """MCP tool passes theme to DiagramGenerator."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(python_project),
        ), patch("docs_mcp.server_gen_tools._record_call"):
            result = _run(docs_generate_diagram(
                diagram_type="class_hierarchy",
                format="d2",
                theme="sketch",
                project_root=str(python_project),
            ))

        assert result.get("success") is True
        data = result.get("data", {})
        assert "sketch: true" in data.get("content", "")

    def test_tool_d2_er_diagram(self, model_project: Path) -> None:
        """MCP tool generates D2 ER diagrams."""
        from docs_mcp.server_gen_tools import docs_generate_diagram

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(model_project),
        ), patch("docs_mcp.server_gen_tools._record_call"):
            result = _run(docs_generate_diagram(
                diagram_type="er_diagram",
                format="d2",
                project_root=str(model_project),
            ))

        assert result.get("success") is True
        data = result.get("data", {})
        assert "shape: sql_table" in data.get("content", "")
