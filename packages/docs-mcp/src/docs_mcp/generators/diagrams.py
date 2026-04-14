"""Diagram generation for Python project structures.

Generates Mermaid and PlantUML diagrams from project analysis results,
including dependency graphs, class hierarchies, module maps, and ER diagrams.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import structlog
from pydantic import BaseModel

from docs_mcp.constants import SKIP_DIRS

if TYPE_CHECKING:
    from docs_mcp.analyzers.dependency import ImportGraph
    from docs_mcp.analyzers.models import ModuleMap, ModuleNode
    from docs_mcp.analyzers.pattern import ArchetypeResult
    from docs_mcp.extractors.models import ClassInfo

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Maximum number of nodes before truncation in dependency/module diagrams.
_MAX_DEPENDENCY_NODES = 50
# Maximum depth for auto-generated sequence diagrams to avoid explosion.
_MAX_SEQUENCE_DEPTH = 3
# Maximum number of participants in a sequence diagram.
_MAX_SEQUENCE_PARTICIPANTS = 15
# Maximum number of messages in a sequence diagram.
_MAX_SEQUENCE_MESSAGES = 40
# Maximum number of classes rendered in class/ER diagrams.
_MAX_CLASS_NODES = 30
# Maximum number of files to scan when extracting classes project-wide.
_MAX_SCAN_FILES = 30
# Minimum classes/modules before a quality warning is emitted.
_MIN_RESULTS_THRESHOLD = 3
# Maximum packages shown on a pattern_card poster (README-embeddable size).
_MAX_PATTERN_NODES = 8

# Fixed semantic-role palette. Shared across renderers (STORY-100.2 will
# re-use these colors for the other 7 diagram types so every docs-mcp visual
# speaks the same visual language).
_ROLE_COLORS: dict[str, str] = {
    "presentation": "#F5A9D0",
    "business": "#14B8A6",
    "data": "#9333EA",
    "infra": "#6B7280",
}

# Package-name keywords that map to each semantic role.
_ROLE_KEYWORDS: dict[str, frozenset[str]] = {
    "presentation": frozenset(
        {
            "api", "web", "ui", "views", "controllers", "routes",
            "presentation", "cli", "server", "handlers", "endpoints",
        }
    ),
    "business": frozenset(
        {
            "services", "service", "business", "domain", "usecases",
            "use_cases", "application", "core", "generators", "analyzers",
            "validators", "extractors", "pipeline", "tools", "workflow",
        }
    ),
    "data": frozenset(
        {
            "repositories", "repository", "dao", "data_access", "models",
            "entities", "persistence", "db", "database", "memory",
            "storage", "cache", "store",
        }
    ),
    "infra": frozenset(
        {
            "config", "settings", "security", "logging", "metrics",
            "telemetry", "infrastructure", "distribution", "integrations",
            "utils", "common", "constants", "monitoring", "observability",
        }
    ),
}

# Mapping from Python type annotation substrings to ER-diagram type names.
_PYTHON_TYPE_TO_ER: dict[str, str] = {
    "str": "string",
    "int": "int",
    "float": "float",
    "bool": "boolean",
}

# Suffixes that indicate non-source directories.
_SKIP_SUFFIXES: frozenset[str] = frozenset({".egg-info"})


class DiagramResult(BaseModel):
    """Result of diagram generation."""

    diagram_type: str
    format: str
    content: str
    node_count: int = 0
    edge_count: int = 0
    degraded: bool = False
    scanned_dirs: list[str] = []
    skipped_count: int = 0


class DiagramGenerator:
    """Generates visual diagrams from project analysis data.

    Supports eight diagram types (dependency, class_hierarchy, module_map,
    er_diagram, c4_context, c4_container, c4_component, sequence) in three
    output formats (mermaid, plantuml, d2).
    """

    VALID_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "dependency",
            "class_hierarchy",
            "module_map",
            "er_diagram",
            "c4_context",
            "c4_container",
            "c4_component",
            "sequence",
            "pattern_card",
        }
    )
    VALID_FORMATS: ClassVar[frozenset[str]] = frozenset({"mermaid", "plantuml", "d2"})
    VALID_THEMES: ClassVar[frozenset[str]] = frozenset({"default", "sketch", "terminal"})

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        project_root: Path,
        *,
        diagram_type: str = "dependency",
        output_format: str = "mermaid",
        scope: str = "project",
        depth: int = 2,
        direction: str = "TD",
        show_external: bool = False,
        flow_spec: str = "",
        theme: str = "default",
    ) -> DiagramResult:
        """Generate a diagram for a project.

        Args:
            project_root: Root directory of the project.
            diagram_type: One of ``dependency``, ``class_hierarchy``,
                ``module_map``, ``er_diagram``, ``c4_context``,
                ``c4_container``, ``c4_component``, or ``sequence``.
            output_format: Output format -- ``mermaid``, ``plantuml``,
                or ``d2``.
            scope: Scope of the diagram; ``project`` for the whole project
                or a file path for a single file (class/ER diagrams).
            depth: Depth limit for module map / dependency diagrams.
            direction: Graph direction (``TD``, ``LR``, etc.).
            show_external: Whether to include external dependencies.
            flow_spec: JSON string defining a manual sequence flow.
                Expected format: ``{"participants": ["A", "B"],
                "messages": [{"from": "A", "to": "B", "label": "call"}]}``.
                When empty, auto-detects from import graph entry points.
            theme: D2 theme -- ``default``, ``sketch``, or ``terminal``.
                Ignored for mermaid and plantuml formats.

        Returns:
            A :class:`DiagramResult` with the rendered content.
        """
        if diagram_type not in self.VALID_TYPES:
            logger.warning("invalid_diagram_type", diagram_type=diagram_type)
            return DiagramResult(
                diagram_type=diagram_type, format=output_format, content=""
            )

        if output_format not in self.VALID_FORMATS:
            logger.warning("invalid_format", format=output_format)
            return DiagramResult(
                diagram_type=diagram_type, format=output_format, content=""
            )

        # Store theme for D2 renderers to access.
        self._d2_theme = theme if theme in self.VALID_THEMES else "default"

        dispatch = {
            "dependency": lambda: self._generate_dependency(
                project_root, depth, direction, show_external, output_format
            ),
            "class_hierarchy": lambda: self._generate_class_hierarchy(
                project_root, scope, output_format
            ),
            "module_map": lambda: self._generate_module_map(
                project_root, depth, direction, output_format
            ),
            "er_diagram": lambda: self._generate_er_diagram(
                project_root, scope, output_format
            ),
            "c4_context": lambda: self._generate_c4_context(
                project_root, output_format
            ),
            "c4_container": lambda: self._generate_c4_container(
                project_root, output_format
            ),
            "c4_component": lambda: self._generate_c4_component(
                project_root, scope, output_format
            ),
            "sequence": lambda: self._generate_sequence(
                project_root, output_format, depth, flow_spec
            ),
            "pattern_card": lambda: self._generate_pattern_card(
                project_root, output_format
            ),
        }

        return dispatch[diagram_type]()

    # ------------------------------------------------------------------
    # Source directory resolution
    # ------------------------------------------------------------------

    def _resolve_source_dirs(self, project_root: Path) -> list[Path]:
        """Auto-detect source directories for the project.

        Checks for ``src/`` layout with package subdirectories first,
        then falls back to ``project_root`` itself.
        """
        src_dir = project_root / "src"
        if src_dir.is_dir():
            packages = [
                d
                for d in src_dir.iterdir()
                if d.is_dir()
                and not self._should_skip_dir(d)
                and (d / "__init__.py").exists()
            ]
            if packages:
                return packages
            return [src_dir]
        return [project_root]

    @staticmethod
    def _should_skip_dir(directory: Path) -> bool:
        """Check if a directory should be skipped during traversal."""
        name = directory.name
        if name in SKIP_DIRS:
            return True
        if name.startswith("."):
            return True
        return any(name.endswith(suffix) for suffix in _SKIP_SUFFIXES)

    # ------------------------------------------------------------------
    # ID sanitisation
    # ------------------------------------------------------------------

    def _sanitize_id(self, name: str) -> str:
        """Sanitize a name for use as a diagram node identifier.

        Replaces path separators, dots, hyphens and spaces with underscores,
        strips remaining non-alphanumeric characters, and ensures the id
        does not start with a digit.
        """
        sanitized = re.sub(r"[./\\\s-]", "_", name)
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "", sanitized)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"m_{sanitized}"
        return sanitized

    # ------------------------------------------------------------------
    # Dependency diagram
    # ------------------------------------------------------------------

    def _generate_dependency(
        self,
        project_root: Path,
        depth: int,
        direction: str,
        show_external: bool,
        output_format: str,
    ) -> DiagramResult:
        """Generate a dependency / import-graph diagram."""
        try:
            from docs_mcp.analyzers.dependency import ImportGraphBuilder

            builder = ImportGraphBuilder()
            graph = builder.build(project_root)
        except Exception:
            logger.warning("dependency_build_failed", path=str(project_root))
            return DiagramResult(
                diagram_type="dependency", format=output_format, content=""
            )

        try:
            if output_format == "mermaid":
                content, nodes, edges = self._dependency_to_mermaid(
                    graph, direction, show_external
                )
            elif output_format == "d2":
                content, nodes, edges = self._dependency_to_d2(
                    graph, direction, show_external
                )
            else:
                content, nodes, edges = self._dependency_to_plantuml(
                    graph, direction, show_external
                )
        except Exception:
            logger.warning("dependency_render_failed")
            return DiagramResult(
                diagram_type="dependency", format=output_format, content=""
            )

        return DiagramResult(
            diagram_type="dependency",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
        )

    def _dependency_to_mermaid(
        self,
        graph: ImportGraph,
        direction: str,
        show_external: bool,
    ) -> tuple[str, int, int]:
        """Render an import graph as a Mermaid flowchart.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        modules = list(graph.modules)
        truncated = len(modules) > _MAX_DEPENDENCY_NODES
        if truncated:
            modules = modules[:_MAX_DEPENDENCY_NODES]
        module_set = set(modules)

        # Group modules by first path component (package).
        packages: dict[str, list[str]] = {}
        for mod in modules:
            parts = mod.split("/")
            pkg = parts[0] if len(parts) > 1 else ""
            packages.setdefault(pkg, []).append(mod)

        lines: list[str] = [f"graph {direction}"]

        # Emit subgraphs and nodes.
        node_count = 0
        emitted_ids: set[str] = set()

        for pkg, pkg_modules in sorted(packages.items()):
            if pkg:
                pkg_id = self._sanitize_id(pkg)
                lines.append(f'    subgraph {pkg_id}["{pkg}"]')
                for mod in sorted(pkg_modules):
                    mod_id = self._sanitize_id(mod)
                    label = mod.split("/")[-1]
                    leaf = label.rsplit(".", 1)[0] or pkg
                    role = self._classify_role(leaf)
                    if role == "infra":
                        role = self._role_for_top_component(pkg)
                    lines.append(f'        {mod_id}["{label}"]:::{role}')
                    emitted_ids.add(mod_id)
                    node_count += 1
                lines.append("    end")
            else:
                for mod in sorted(pkg_modules):
                    mod_id = self._sanitize_id(mod)
                    label = mod.split("/")[-1]
                    leaf = label.rsplit(".", 1)[0] or mod
                    role = self._classify_role(leaf)
                    if role == "infra":
                        role = self._role_for_top_component(mod)
                    lines.append(f'    {mod_id}["{label}"]:::{role}')
                    emitted_ids.add(mod_id)
                    node_count += 1

        # Collect external nodes (if requested).
        external_ids: set[str] = set()

        # Emit edges.
        edge_count = 0
        for edge in graph.edges:
            if edge.source not in module_set or edge.target not in module_set:
                continue
            src_id = self._sanitize_id(edge.source)
            tgt_id = self._sanitize_id(edge.target)
            if edge.import_type in ("type_checking", "conditional", "lazy"):
                lines.append(f"    {src_id} -.-> {tgt_id}")
            else:
                lines.append(f"    {src_id} --> {tgt_id}")
            edge_count += 1

        # External edges.
        if show_external:
            for mod_path, ext_list in graph.external_imports.items():
                if mod_path not in module_set:
                    continue
                src_id = self._sanitize_id(mod_path)
                for ext_name in ext_list:
                    ext_top = ext_name.split(".")[0]
                    ext_id = self._sanitize_id(ext_top)
                    if ext_id not in external_ids:
                        lines.append(
                            f'    {ext_id}["{ext_top}"]:::external'
                        )
                        external_ids.add(ext_id)
                        node_count += 1
                    lines.append(f"    {src_id} -.-> {ext_id}")
                    edge_count += 1

        if truncated:
            lines.append(
                f"    %% Truncated: showing {_MAX_DEPENDENCY_NODES}"
                f" of {len(graph.modules)} modules"
            )

        lines.extend(self._role_classdef_mermaid_lines())
        content = "\n".join(lines) + "\n"
        return content, node_count, edge_count

    def _dependency_to_plantuml(
        self,
        graph: ImportGraph,
        direction: str,
        show_external: bool,
    ) -> tuple[str, int, int]:
        """Render an import graph as PlantUML component diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        modules = list(graph.modules)
        truncated = len(modules) > _MAX_DEPENDENCY_NODES
        if truncated:
            modules = modules[:_MAX_DEPENDENCY_NODES]
        module_set = set(modules)

        packages: dict[str, list[str]] = {}
        for mod in modules:
            parts = mod.split("/")
            pkg = parts[0] if len(parts) > 1 else ""
            packages.setdefault(pkg, []).append(mod)

        # Map direction to PlantUML equivalent.
        puml_direction = (
            "left to right direction" if direction == "LR" else "top to bottom direction"
        )

        lines: list[str] = ["@startuml", puml_direction, ""]

        node_count = 0
        for pkg, pkg_modules in sorted(packages.items()):
            if pkg:
                lines.append(f'package "{pkg}" {{')
                for mod in sorted(pkg_modules):
                    label = mod.split("/")[-1]
                    lines.append(f"    [{label}]")
                    node_count += 1
                lines.append("}")
            else:
                for mod in sorted(pkg_modules):
                    label = mod.split("/")[-1]
                    lines.append(f"[{label}]")
                    node_count += 1

        lines.append("")

        edge_count = 0
        for edge in graph.edges:
            if edge.source not in module_set or edge.target not in module_set:
                continue
            src_label = edge.source.split("/")[-1]
            tgt_label = edge.target.split("/")[-1]
            if edge.import_type in ("type_checking", "conditional", "lazy"):
                lines.append(f"[{src_label}] ..> [{tgt_label}]")
            else:
                lines.append(f"[{src_label}] --> [{tgt_label}]")
            edge_count += 1

        if show_external:
            lines.append("")
            external_ids: set[str] = set()
            for mod_path, ext_list in graph.external_imports.items():
                if mod_path not in module_set:
                    continue
                src_label = mod_path.split("/")[-1]
                for ext_name in ext_list:
                    ext_top = ext_name.split(".")[0]
                    if ext_top not in external_ids:
                        lines.append(f"cloud {ext_top}")
                        external_ids.add(ext_top)
                        node_count += 1
                    lines.append(f"[{src_label}] ..> {ext_top}")
                    edge_count += 1

        if truncated:
            lines.append(
                f"' Truncated: showing {_MAX_DEPENDENCY_NODES}"
                f" of {len(graph.modules)} modules"
            )

        lines.append("")
        lines.append("@enduml")
        content = "\n".join(lines) + "\n"
        return content, node_count, edge_count

    # ------------------------------------------------------------------
    # Class hierarchy diagram
    # ------------------------------------------------------------------

    def _generate_class_hierarchy(
        self,
        project_root: Path,
        scope: str,
        output_format: str,
    ) -> DiagramResult:
        """Generate a class hierarchy diagram."""
        try:
            classes, scanned_dirs, skipped = self._collect_classes(project_root, scope)
        except Exception:
            logger.warning("class_collection_failed", path=str(project_root))
            return DiagramResult(
                diagram_type="class_hierarchy",
                format=output_format,
                content="",
            )

        degraded = scope == "project" and len(classes) < _MIN_RESULTS_THRESHOLD
        if degraded:
            logger.warning(
                "diagram_possibly_degraded",
                diagram_type="class_hierarchy",
                class_count=len(classes),
                scanned_dirs=scanned_dirs,
            )

        if not classes:
            return DiagramResult(
                diagram_type="class_hierarchy",
                format=output_format,
                content="",
                degraded=degraded,
                scanned_dirs=scanned_dirs,
                skipped_count=skipped,
            )

        try:
            if output_format == "mermaid":
                content, nodes, edges = self._classes_to_mermaid(classes)
            elif output_format == "d2":
                content, nodes, edges = self._classes_to_d2(classes)
            else:
                content, nodes, edges = self._classes_to_plantuml(classes)
        except Exception:
            logger.warning("class_render_failed")
            return DiagramResult(
                diagram_type="class_hierarchy",
                format=output_format,
                content="",
            )

        return DiagramResult(
            diagram_type="class_hierarchy",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
            degraded=degraded,
            scanned_dirs=scanned_dirs,
            skipped_count=skipped,
        )

    def _collect_classes(
        self,
        project_root: Path,
        scope: str,
    ) -> tuple[list[tuple[str, ClassInfo]], list[str], int]:
        """Collect ClassInfo objects from the project.

        Args:
            project_root: Root of the project.
            scope: ``"project"`` for all files, or a file path.

        Returns:
            Tuple of (classes, scanned_dir_names, skipped_file_count).
        """
        from docs_mcp.extractors.python import PythonExtractor

        extractor = PythonExtractor()
        classes: list[tuple[str, ClassInfo]] = []

        if scope != "project":
            file_path = Path(scope)
            if not file_path.is_absolute():
                file_path = project_root / file_path
            if file_path.is_file():
                info = extractor.extract(file_path, project_root=project_root)
                module_name = file_path.stem
                for cls in info.classes:
                    classes.append((module_name, cls))
            return classes, [str(file_path)], 0

        # Resolve source directories instead of scanning entire project_root.
        source_dirs = self._resolve_source_dirs(project_root)
        scanned_dir_names = [str(d.relative_to(project_root)) for d in source_dirs]

        file_count = 0
        skipped_count = 0
        scan_done = False
        for src_dir in source_dirs:
            if scan_done:
                break
            for py_file in sorted(src_dir.rglob("*.py")):
                if self._should_skip_path(py_file):
                    skipped_count += 1
                    continue
                if file_count >= _MAX_SCAN_FILES:
                    scan_done = True
                    break
                file_count += 1
                info = extractor.extract(py_file, project_root=project_root)
                module_name = py_file.stem
                for cls in info.classes:
                    classes.append((module_name, cls))

        return classes, scanned_dir_names, skipped_count

    @staticmethod
    def _should_skip_path(path: Path) -> bool:
        """Return True if any path component is in ``SKIP_DIRS``."""
        return any(part in SKIP_DIRS for part in path.parts)

    def _classes_to_mermaid(
        self,
        classes: list[tuple[str, ClassInfo]],
    ) -> tuple[str, int, int]:
        """Render classes as a Mermaid class diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        classes = classes[:_MAX_CLASS_NODES]
        class_names = {cls.name for _, cls in classes}

        lines: list[str] = ["classDiagram"]
        edge_count = 0

        for module_name, cls in classes:
            cls_id = self._sanitize_id(cls.name)
            role = self._classify_role(module_name)
            lines.append(f"    class {cls_id}:::{role} {{")

            # Class variables as attributes.
            for var in cls.class_variables:
                annotation = var.annotation or ""
                if annotation:
                    lines.append(f"        +{var.name}: {annotation}")
                else:
                    lines.append(f"        +{var.name}")

            # Methods.
            for method in cls.methods:
                prefix = "-" if method.name.startswith("_") else "+"
                ret = ""
                if method.return_annotation:
                    ret = f" {method.return_annotation}"
                lines.append(f"        {prefix}{method.name}(){ret}")

            lines.append("    }")

        # Inheritance edges (only for bases present in the collected set).
        for _module, cls in classes:
            cls_id = self._sanitize_id(cls.name)
            for base in cls.bases:
                base_simple = base.split(".")[-1]
                if base_simple in class_names:
                    base_id = self._sanitize_id(base_simple)
                    lines.append(f"    {base_id} <|-- {cls_id}")
                    edge_count += 1

        lines.extend(self._role_classdef_mermaid_lines())
        content = "\n".join(lines) + "\n"
        return content, len(classes), edge_count

    def _classes_to_plantuml(
        self,
        classes: list[tuple[str, ClassInfo]],
    ) -> tuple[str, int, int]:
        """Render classes as a PlantUML class diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        classes = classes[:_MAX_CLASS_NODES]
        class_names = {cls.name for _, cls in classes}

        lines: list[str] = ["@startuml", ""]
        edge_count = 0

        for _module, cls in classes:
            lines.append(f"class {cls.name} {{")

            for var in cls.class_variables:
                annotation = var.annotation or ""
                if annotation:
                    lines.append(f"    +{var.name}: {annotation}")
                else:
                    lines.append(f"    +{var.name}")

            for method in cls.methods:
                prefix = "-" if method.name.startswith("_") else "+"
                ret = ""
                if method.return_annotation:
                    ret = f" {method.return_annotation}"
                lines.append(f"    {prefix}{method.name}(){ret}")

            lines.append("}")

        lines.append("")

        for _module, cls in classes:
            for base in cls.bases:
                base_simple = base.split(".")[-1]
                if base_simple in class_names:
                    lines.append(f"{base_simple} <|-- {cls.name}")
                    edge_count += 1

        lines.append("")
        lines.append("@enduml")
        content = "\n".join(lines) + "\n"
        return content, len(classes), edge_count

    # ------------------------------------------------------------------
    # Module map diagram
    # ------------------------------------------------------------------

    def _generate_module_map(
        self,
        project_root: Path,
        depth: int,
        direction: str,
        output_format: str,
    ) -> DiagramResult:
        """Generate a module-map diagram."""
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            result = analyzer.analyze(project_root, depth=depth)
        except Exception:
            logger.warning("module_map_failed", path=str(project_root))
            return DiagramResult(
                diagram_type="module_map", format=output_format, content=""
            )

        try:
            if output_format == "mermaid":
                content, nodes, edges = self._module_map_to_mermaid(
                    result, direction
                )
            elif output_format == "d2":
                content, nodes, edges = self._module_map_to_d2(
                    result, direction
                )
            else:
                content, nodes, edges = self._module_map_to_plantuml(
                    result, direction
                )
        except Exception:
            logger.warning("module_map_render_failed")
            return DiagramResult(
                diagram_type="module_map", format=output_format, content=""
            )

        return DiagramResult(
            diagram_type="module_map",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
        )

    def _module_map_to_mermaid(
        self,
        module_map: ModuleMap,
        direction: str,
    ) -> tuple[str, int, int]:
        """Render a module map as a Mermaid flowchart.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        lines: list[str] = [f"graph {direction}"]
        node_count = 0

        project_id = self._sanitize_id(module_map.project_name)
        lines.append(f'    subgraph {project_id}["{module_map.project_name}"]')
        node_count = self._emit_module_nodes_mermaid(
            module_map.module_tree, lines, indent=8, top_role=None
        )
        lines.append("    end")

        lines.extend(self._role_classdef_mermaid_lines())
        content = "\n".join(lines) + "\n"
        # Module maps have no edges -- they show structure only.
        return content, node_count, 0

    def _emit_module_nodes_mermaid(
        self,
        nodes: list[ModuleNode],
        lines: list[str],
        indent: int,
        top_role: str | None = None,
    ) -> int:
        """Recursively emit Mermaid nodes for a module tree.

        Returns:
            The number of nodes emitted.
        """

        pad = " " * indent
        count = 0

        for node in nodes:
            node_id = self._sanitize_id(node.path or node.name)
            node_role = top_role or self._classify_role(node.name)
            if node.is_package:
                label = f"{node.name}/"
                lines.append(f'{pad}subgraph {node_id}["{label}"]')
                count += self._emit_module_nodes_mermaid(
                    node.submodules, lines, indent + 4, top_role=node_role
                )
                lines.append(f"{pad}end")
            else:
                label_parts: list[str] = [node.name]
                stats: list[str] = []
                if node.function_count:
                    stats.append(f"{node.function_count}F")
                if node.class_count:
                    stats.append(f"{node.class_count}C")
                if stats:
                    label_parts.append(f" ({', '.join(stats)})")
                label = "".join(label_parts)
                lines.append(f'{pad}{node_id}["{label}"]:::{node_role}')
                count += 1

        return count

    def _module_map_to_plantuml(
        self,
        module_map: ModuleMap,
        direction: str,
    ) -> tuple[str, int, int]:
        """Render a module map as a PlantUML diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        puml_direction = (
            "left to right direction" if direction == "LR" else "top to bottom direction"
        )

        lines: list[str] = ["@startuml", puml_direction, ""]

        lines.append(f'package "{module_map.project_name}" {{')
        node_count = self._emit_module_nodes_plantuml(
            module_map.module_tree, lines, indent=4
        )
        lines.append("}")

        lines.append("")
        lines.append("@enduml")
        content = "\n".join(lines) + "\n"
        return content, node_count, 0

    def _emit_module_nodes_plantuml(
        self,
        nodes: list[ModuleNode],
        lines: list[str],
        indent: int,
    ) -> int:
        """Recursively emit PlantUML nodes for a module tree.

        Returns:
            The number of nodes emitted.
        """

        pad = " " * indent
        count = 0

        for node in nodes:
            if node.is_package:
                lines.append(f'{pad}package "{node.name}/" {{')
                count += self._emit_module_nodes_plantuml(
                    node.submodules, lines, indent + 4
                )
                lines.append(f"{pad}}}")
            else:
                stats: list[str] = []
                if node.function_count:
                    stats.append(f"{node.function_count}F")
                if node.class_count:
                    stats.append(f"{node.class_count}C")
                suffix = f" ({', '.join(stats)})" if stats else ""
                lines.append(f"{pad}[{node.name}{suffix}]")
                count += 1

        return count

    # ------------------------------------------------------------------
    # ER diagram
    # ------------------------------------------------------------------

    def _generate_er_diagram(
        self,
        project_root: Path,
        scope: str,
        output_format: str,
    ) -> DiagramResult:
        """Generate an entity-relationship diagram from model classes."""
        try:
            classes, scanned_dirs, skipped = self._collect_classes(project_root, scope)
        except Exception:
            logger.warning("er_class_collection_failed", path=str(project_root))
            return DiagramResult(
                diagram_type="er_diagram", format=output_format, content=""
            )

        models = [
            (mod, cls) for mod, cls in classes if self._is_model_class(cls)
        ]

        if not models:
            return DiagramResult(
                diagram_type="er_diagram",
                format=output_format,
                content="",
                scanned_dirs=scanned_dirs,
                skipped_count=skipped,
            )

        try:
            if output_format == "mermaid":
                content, nodes, edges = self._models_to_mermaid_er(models)
            elif output_format == "d2":
                content, nodes, edges = self._models_to_d2_er(models)
            else:
                content, nodes, edges = self._models_to_plantuml_er(models)
        except Exception:
            logger.warning("er_render_failed")
            return DiagramResult(
                diagram_type="er_diagram", format=output_format, content=""
            )

        return DiagramResult(
            diagram_type="er_diagram",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
            scanned_dirs=scanned_dirs,
            skipped_count=skipped,
        )

    def _is_model_class(self, cls: ClassInfo) -> bool:
        """Return True if *cls* looks like a data model or dataclass."""
        model_bases = {"BaseModel", "BaseSettings"}
        if any(base.split(".")[-1] in model_bases for base in cls.bases):
            return True

        return any("dataclass" in decorator.name for decorator in cls.decorators)

    def _map_python_type(self, annotation: str) -> str:
        """Map a Python type annotation string to a simple ER type name."""
        for py_type, er_type in _PYTHON_TYPE_TO_ER.items():
            if py_type in annotation:
                return er_type
        return "string"

    def _models_to_mermaid_er(
        self,
        models: list[tuple[str, ClassInfo]],
    ) -> tuple[str, int, int]:
        """Render model classes as a Mermaid ER diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        models = models[:_MAX_CLASS_NODES]
        model_names = {cls.name for _, cls in models}

        lines: list[str] = ["erDiagram"]
        edge_count = 0

        for _module, cls in models:
            cls_id = self._sanitize_id(cls.name)
            lines.append(f"    {cls_id} {{")
            for var in cls.class_variables:
                er_type = self._map_python_type(var.annotation or "")
                lines.append(f"        {er_type} {var.name}")
            lines.append("    }")

        # Detect relationships: if a field's annotation mentions another
        # model name, emit a relationship edge.
        for _module, cls in models:
            cls_id = self._sanitize_id(cls.name)
            for var in cls.class_variables:
                annotation = var.annotation or ""
                for other_name in model_names:
                    if other_name == cls.name:
                        continue
                    if other_name in annotation:
                        other_id = self._sanitize_id(other_name)
                        lines.append(
                            f'    {cls_id} ||--o{{ {other_id} : "has"'
                        )
                        edge_count += 1

        content = "\n".join(lines) + "\n"
        return content, len(models), edge_count

    def _models_to_plantuml_er(
        self,
        models: list[tuple[str, ClassInfo]],
    ) -> tuple[str, int, int]:
        """Render model classes as a PlantUML ER diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        models = models[:_MAX_CLASS_NODES]
        model_names = {cls.name for _, cls in models}

        lines: list[str] = ["@startuml", ""]
        edge_count = 0

        for _module, cls in models:
            lines.append(f"entity {cls.name} {{")
            for var in cls.class_variables:
                er_type = self._map_python_type(var.annotation or "")
                lines.append(f"    {var.name} : {er_type}")
            lines.append("}")

        lines.append("")

        for _module, cls in models:
            for var in cls.class_variables:
                annotation = var.annotation or ""
                for other_name in model_names:
                    if other_name == cls.name:
                        continue
                    if other_name in annotation:
                        lines.append(
                            f'{cls.name} ||--o{{ {other_name} : "has"'
                        )
                        edge_count += 1

        lines.append("")
        lines.append("@enduml")
        content = "\n".join(lines) + "\n"
        return content, len(models), edge_count

    # ------------------------------------------------------------------
    # C4 System Context diagram (Epic 80.1)
    # ------------------------------------------------------------------

    def _generate_c4_context(
        self,
        project_root: Path,
        output_format: str,
    ) -> DiagramResult:
        """Generate a C4 System Context diagram."""
        from docs_mcp.generators.metadata import MetadataExtractor

        extractor = MetadataExtractor()
        metadata = extractor.extract(project_root)
        project_name = metadata.name or project_root.name
        description = metadata.description or "Software system"

        # Detect external actors from common patterns
        actors: list[tuple[str, str]] = []  # (name, description)
        deps = [d.split("[")[0].split(">")[0].split("=")[0].strip().lower()
                for d in metadata.dependencies]

        if any(d in deps for d in ("fastapi", "flask", "django", "starlette")):
            actors.append(("User", "End user interacting via web browser or API client"))
        if any(d in deps for d in ("sqlalchemy", "psycopg2", "pymongo", "redis")):
            actors.append(("Database", "Persistent data store"))
        if any(d in deps for d in ("httpx", "requests", "aiohttp")):
            actors.append(("ExternalAPI", "Third-party API service"))
        if any("mcp" in d for d in deps):
            actors.append(("MCPClient", "MCP-capable AI coding assistant"))

        if not actors:
            actors.append(("User", "Primary system user"))

        if output_format == "mermaid":
            content, nodes, edges = self._c4_context_mermaid(
                project_name, description, actors
            )
        elif output_format == "d2":
            content, nodes, edges = self._c4_context_d2(
                project_name, description, actors
            )
        else:
            content, nodes, edges = self._c4_context_plantuml(
                project_name, description, actors
            )

        return DiagramResult(
            diagram_type="c4_context",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
        )

    def _c4_context_mermaid(
        self,
        name: str,
        description: str,
        actors: list[tuple[str, str]],
    ) -> tuple[str, int, int]:
        lines = ["C4Context"]
        lines.append(f'    title System Context diagram for {name}')
        lines.append("")

        node_count = 1 + len(actors)
        edge_count = len(actors)

        # System boundary
        lines.append(f'    System({self._sanitize_id(name)}, "{name}", "{description}")')
        lines.append("")

        # External actors
        for actor_name, actor_desc in actors:
            aid = self._sanitize_id(actor_name)
            if actor_name in ("Database",):
                lines.append(f'    SystemDb({aid}, "{actor_name}", "{actor_desc}")')
            elif actor_name in ("ExternalAPI",):
                lines.append(f'    System_Ext({aid}, "{actor_name}", "{actor_desc}")')
            else:
                lines.append(f'    Person({aid}, "{actor_name}", "{actor_desc}")')

        lines.append("")

        # Relationships
        sys_id = self._sanitize_id(name)
        for actor_name, _ in actors:
            aid = self._sanitize_id(actor_name)
            lines.append(f'    Rel({aid}, {sys_id}, "Uses")')

        # Role-based styling — system is business; actors map by kind.
        styled: list[tuple[str, str]] = [(sys_id, "business")]
        for actor_name, _ in actors:
            aid = self._sanitize_id(actor_name)
            if actor_name == "Database":
                styled.append((aid, "data"))
            elif actor_name == "ExternalAPI":
                styled.append((aid, "infra"))
            else:
                styled.append((aid, "presentation"))
        lines.append("")
        lines.extend(self._role_c4_updateelementstyle_lines(styled))

        lines.append("")
        return "\n".join(lines) + "\n", node_count, edge_count

    def _c4_context_plantuml(
        self,
        name: str,
        description: str,
        actors: list[tuple[str, str]],
    ) -> tuple[str, int, int]:
        lines = ["@startuml"]
        lines.append("!include <C4/C4_Context>")
        lines.append("")
        lines.append(f"title System Context diagram for {name}")
        lines.append("")

        node_count = 1 + len(actors)
        edge_count = len(actors)

        sys_id = self._sanitize_id(name)
        lines.append(f'System({sys_id}, "{name}", "{description}")')
        lines.append("")

        for actor_name, actor_desc in actors:
            aid = self._sanitize_id(actor_name)
            if actor_name in ("Database",):
                lines.append(f'SystemDb({aid}, "{actor_name}", "{actor_desc}")')
            elif actor_name in ("ExternalAPI",):
                lines.append(f'System_Ext({aid}, "{actor_name}", "{actor_desc}")')
            else:
                lines.append(f'Person({aid}, "{actor_name}", "{actor_desc}")')

        lines.append("")
        for actor_name, _ in actors:
            aid = self._sanitize_id(actor_name)
            lines.append(f'Rel({aid}, {sys_id}, "Uses")')

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines) + "\n", node_count, edge_count

    # ------------------------------------------------------------------
    # C4 Container diagram (Epic 80.2)
    # ------------------------------------------------------------------

    def _generate_c4_container(
        self,
        project_root: Path,
        output_format: str,
    ) -> DiagramResult:
        """Generate a C4 Container diagram from package structure."""
        from docs_mcp.generators.metadata import MetadataExtractor

        extractor = MetadataExtractor()
        metadata = extractor.extract(project_root)
        project_name = metadata.name or project_root.name

        # Detect containers from package structure
        containers: list[tuple[str, str, str]] = []  # (name, tech, description)

        # Check for workspace packages
        packages_dir = project_root / "packages"
        if packages_dir.is_dir():
            for pkg_dir in sorted(packages_dir.iterdir()):
                if pkg_dir.is_dir() and (pkg_dir / "pyproject.toml").exists():
                    pkg_meta = extractor.extract(pkg_dir)
                    containers.append((
                        pkg_meta.name or pkg_dir.name,
                        "Python",
                        pkg_meta.description or f"Package: {pkg_dir.name}",
                    ))

        # Check for src layout
        if not containers:
            src_dir = project_root / "src"
            if src_dir.is_dir():
                for pkg_dir in sorted(src_dir.iterdir()):
                    if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
                        containers.append((
                            pkg_dir.name, "Python", f"Python package: {pkg_dir.name}"
                        ))

        # Fallback: top-level Python packages
        if not containers:
            for d in sorted(project_root.iterdir()):
                if (d.is_dir() and (d / "__init__.py").exists()
                        and not self._should_skip_dir(d)):
                    containers.append((d.name, "Python", f"Package: {d.name}"))

        # Detect infrastructure containers
        if (project_root / "Dockerfile").exists():
            containers.append(("Docker", "Docker", "Container runtime"))
        if (project_root / "docker-compose.yml").exists() or (
            project_root / "docker-compose.yaml"
        ).exists():
            containers.append(("DockerCompose", "Docker Compose", "Service orchestration"))

        if not containers:
            containers.append((project_name, "Python", "Main application"))

        if output_format == "mermaid":
            content, nodes, edges = self._c4_container_mermaid(project_name, containers)
        elif output_format == "d2":
            content, nodes, edges = self._c4_container_d2(project_name, containers)
        else:
            content, nodes, edges = self._c4_container_plantuml(project_name, containers)

        return DiagramResult(
            diagram_type="c4_container",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
        )

    def _c4_container_mermaid(
        self,
        name: str,
        containers: list[tuple[str, str, str]],
    ) -> tuple[str, int, int]:
        lines = ["C4Container"]
        lines.append(f'    title Container diagram for {name}')
        lines.append("")
        lines.append(f'    System_Boundary({self._sanitize_id(name)}, "{name}") {{')

        edges = 0
        styled: list[tuple[str, str]] = []
        for cname, tech, desc in containers:
            cid = self._sanitize_id(cname)
            lines.append(f'        Container({cid}, "{cname}", "{tech}", "{desc}")')
            if tech == "Docker" or "Docker" in cname:
                styled.append((cid, "infra"))
            else:
                styled.append((cid, self._classify_role(cname)))

        lines.append("    }")
        lines.append("")

        # Add relationships between containers
        if len(containers) > 1:
            first_id = self._sanitize_id(containers[0][0])
            for i in range(1, min(len(containers), 5)):
                cid = self._sanitize_id(containers[i][0])
                lines.append(f'    Rel({first_id}, {cid}, "Uses")')
                edges += 1

        lines.append("")
        lines.extend(self._role_c4_updateelementstyle_lines(styled))
        lines.append("")
        return "\n".join(lines) + "\n", len(containers), edges

    def _c4_container_plantuml(
        self,
        name: str,
        containers: list[tuple[str, str, str]],
    ) -> tuple[str, int, int]:
        lines = ["@startuml"]
        lines.append("!include <C4/C4_Container>")
        lines.append("")
        lines.append(f"title Container diagram for {name}")
        lines.append("")
        lines.append(f'System_Boundary({self._sanitize_id(name)}, "{name}") {{')

        edges = 0
        for cname, tech, desc in containers:
            cid = self._sanitize_id(cname)
            lines.append(f'    Container({cid}, "{cname}", "{tech}", "{desc}")')

        lines.append("}")
        lines.append("")

        if len(containers) > 1:
            first_id = self._sanitize_id(containers[0][0])
            for i in range(1, min(len(containers), 5)):
                cid = self._sanitize_id(containers[i][0])
                lines.append(f'Rel({first_id}, {cid}, "Uses")')
                edges += 1

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines) + "\n", len(containers), edges

    # ------------------------------------------------------------------
    # C4 Component diagram (Epic 80.3)
    # ------------------------------------------------------------------

    def _generate_c4_component(
        self,
        project_root: Path,
        scope: str,
        output_format: str,
    ) -> DiagramResult:
        """Generate a C4 Component diagram for a specific package."""
        from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

        analyzer = ModuleMapAnalyzer()

        # Determine scope directory
        if scope and scope != "project":
            scope_dir = project_root / scope
            if not scope_dir.is_dir():
                scope_dir = project_root
        else:
            scope_dir = project_root

        module_map = analyzer.analyze(scope_dir, depth=3)

        # Extract components from module tree
        components: list[tuple[str, str, int]] = []  # (name, path, func_count)
        if module_map.module_tree:
            for sub in module_map.module_tree[:_MAX_DEPENDENCY_NODES]:
                func_count = sub.function_count or 0
                class_count = sub.class_count or 0
                desc = f"{func_count} functions, {class_count} classes"
                components.append((sub.name, desc, func_count + class_count))

        if not components:
            return DiagramResult(
                diagram_type="c4_component",
                format=output_format,
                content="",
                degraded=True,
            )

        container_name = module_map.project_name or scope_dir.name

        if output_format == "mermaid":
            content, nodes, edges = self._c4_component_mermaid(container_name, components)
        elif output_format == "d2":
            content, nodes, edges = self._c4_component_d2(container_name, components)
        else:
            content, nodes, edges = self._c4_component_plantuml(container_name, components)

        return DiagramResult(
            diagram_type="c4_component",
            format=output_format,
            content=content,
            node_count=nodes,
            edge_count=edges,
        )

    def _c4_component_mermaid(
        self,
        container_name: str,
        components: list[tuple[str, str, int]],
    ) -> tuple[str, int, int]:
        lines = ["C4Component"]
        lines.append(f'    title Component diagram for {container_name}')
        lines.append("")
        cid = self._sanitize_id(container_name)
        lines.append(f'    Container_Boundary({cid}, "{container_name}") {{')

        styled: list[tuple[str, str]] = []
        for cname, desc, _ in components[:_MAX_DEPENDENCY_NODES]:
            comp_id = self._sanitize_id(cname)
            lines.append(f'        Component({comp_id}, "{cname}", "Python", "{desc}")')
            styled.append((comp_id, self._classify_role(cname)))

        lines.append("    }")
        lines.append("")
        lines.extend(self._role_c4_updateelementstyle_lines(styled))
        lines.append("")
        return "\n".join(lines) + "\n", len(components), 0

    def _c4_component_plantuml(
        self,
        container_name: str,
        components: list[tuple[str, str, int]],
    ) -> tuple[str, int, int]:
        lines = ["@startuml"]
        lines.append("!include <C4/C4_Component>")
        lines.append("")
        lines.append(f"title Component diagram for {container_name}")
        lines.append("")
        cid = self._sanitize_id(container_name)
        lines.append(f'Container_Boundary({cid}, "{container_name}") {{')

        for cname, desc, _ in components[:_MAX_DEPENDENCY_NODES]:
            comp_id = self._sanitize_id(cname)
            lines.append(f'    Component({comp_id}, "{cname}", "Python", "{desc}")')

        lines.append("}")
        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines) + "\n", len(components), 0

    # ------------------------------------------------------------------
    # Sequence diagram (Epic 80.4)
    # ------------------------------------------------------------------

    def _generate_sequence(
        self,
        project_root: Path,
        output_format: str,
        depth: int,
        flow_spec: str,
    ) -> DiagramResult:
        """Generate a sequence diagram.

        When *flow_spec* is provided, it is parsed as JSON describing
        participants and messages.  Otherwise, an auto-detected flow is
        built from the project's import graph entry points.
        """
        if flow_spec:
            return self._sequence_from_spec(flow_spec, output_format)
        return self._sequence_from_imports(project_root, output_format, depth)

    # -- manual mode (flow_spec JSON) -----------------------------------

    def _sequence_from_spec(
        self,
        flow_spec: str,
        output_format: str,
    ) -> DiagramResult:
        """Build a sequence diagram from a user-provided JSON spec.

        Expected JSON schema::

            {
                "title": "optional title",
                "participants": ["Client", "Server", "Database"],
                "messages": [
                    {"from": "Client", "to": "Server", "label": "POST /api"},
                    {"from": "Server", "to": "Database", "label": "INSERT",
                     "type": "async"},
                    {"from": "Database", "to": "Server", "label": "result",
                     "type": "reply"},
                    {"from": "Server", "to": "Client", "label": "200 OK",
                     "type": "reply"}
                ],
                "notes": [
                    {"over": "Server", "text": "Validates JWT token"}
                ],
                "groups": [
                    {"type": "alt", "label": "success",
                     "start": 0, "end": 3}
                ]
            }
        """
        try:
            spec = json.loads(flow_spec)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("invalid_flow_spec", error=str(exc))
            return DiagramResult(
                diagram_type="sequence", format=output_format, content=""
            )

        participants: list[str] = spec.get("participants", [])
        messages: list[dict[str, str]] = spec.get("messages", [])
        title: str = spec.get("title", "")
        notes: list[dict[str, str]] = spec.get("notes", [])
        groups: list[dict[str, object]] = spec.get("groups", [])

        if not participants or not messages:
            logger.warning("empty_flow_spec")
            return DiagramResult(
                diagram_type="sequence", format=output_format, content=""
            )

        # Enforce limits
        participants = participants[:_MAX_SEQUENCE_PARTICIPANTS]
        messages = messages[:_MAX_SEQUENCE_MESSAGES]
        participant_set = frozenset(participants)

        # Filter messages to only reference known participants
        valid_messages = [
            m for m in messages
            if m.get("from") in participant_set and m.get("to") in participant_set
        ]

        if output_format == "mermaid":
            content = self._sequence_mermaid(
                title, participants, valid_messages, notes, groups
            )
        elif output_format == "d2":
            content = self._sequence_d2(
                title, participants, valid_messages, notes, groups
            )
        else:
            content = self._sequence_plantuml(
                title, participants, valid_messages, notes, groups
            )

        return DiagramResult(
            diagram_type="sequence",
            format=output_format,
            content=content,
            node_count=len(participants),
            edge_count=len(valid_messages),
        )

    # -- auto-detect mode (import graph) --------------------------------

    def _sequence_from_imports(
        self,
        project_root: Path,
        output_format: str,
        depth: int,
    ) -> DiagramResult:
        """Auto-generate a sequence diagram from the import graph.

        Walks from each entry-point module along import edges up to
        *depth* levels, producing a message for each import relationship.
        """
        from docs_mcp.analyzers.dependency import ImportGraphBuilder

        builder = ImportGraphBuilder()
        graph = builder.build(project_root)

        if not graph.edges:
            return DiagramResult(
                diagram_type="sequence",
                format=output_format,
                content="",
                degraded=True,
            )

        # Build adjacency list
        adjacency: dict[str, list[str]] = {}
        for edge in graph.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)

        # Walk from entry points (modules with no incoming edges)
        entry_points = graph.entry_points or list(adjacency.keys())[:3]
        effective_depth = min(depth, _MAX_SEQUENCE_DEPTH)

        # Collect (from, to) message pairs via BFS from entry points
        visited_edges: list[tuple[str, str]] = []
        visited_modules: set[str] = set()

        for ep in entry_points[:5]:
            self._walk_imports(
                ep, adjacency, effective_depth, 0, visited_modules, visited_edges
            )

        if not visited_edges:
            return DiagramResult(
                diagram_type="sequence",
                format=output_format,
                content="",
                degraded=True,
            )

        # Derive participants from visited edges, preserving order
        participants: list[str] = []
        seen: set[str] = set()
        for src, tgt in visited_edges:
            for mod in (src, tgt):
                if mod not in seen:
                    participants.append(mod)
                    seen.add(mod)

        participants = participants[:_MAX_SEQUENCE_PARTICIPANTS]
        participant_set = frozenset(participants)
        messages = [
            {"from": src, "to": tgt, "label": "imports"}
            for src, tgt in visited_edges
            if src in participant_set and tgt in participant_set
        ][:_MAX_SEQUENCE_MESSAGES]

        title = f"Import flow from {project_root.name}"

        if output_format == "mermaid":
            content = self._sequence_mermaid(title, participants, messages, [], [])
        elif output_format == "d2":
            content = self._sequence_d2(title, participants, messages, [], [])
        else:
            content = self._sequence_plantuml(title, participants, messages, [], [])

        return DiagramResult(
            diagram_type="sequence",
            format=output_format,
            content=content,
            node_count=len(participants),
            edge_count=len(messages),
        )

    def _walk_imports(
        self,
        module: str,
        adjacency: dict[str, list[str]],
        max_depth: int,
        current_depth: int,
        visited_modules: set[str],
        visited_edges: list[tuple[str, str]],
    ) -> None:
        """Recursively walk import edges collecting sequence messages."""
        if current_depth >= max_depth or module in visited_modules:
            return
        visited_modules.add(module)
        for target in adjacency.get(module, []):
            edge = (module, target)
            if edge not in visited_edges:
                visited_edges.append(edge)
                if len(visited_edges) >= _MAX_SEQUENCE_MESSAGES:
                    return
            self._walk_imports(
                target, adjacency, max_depth, current_depth + 1,
                visited_modules, visited_edges,
            )

    # -- Mermaid renderer -----------------------------------------------

    def _sequence_mermaid(
        self,
        title: str,
        participants: list[str],
        messages: list[dict[str, str]],
        notes: list[dict[str, str]],
        groups: list[dict[str, object]],
    ) -> str:
        """Render a Mermaid sequenceDiagram block."""
        lines = ["sequenceDiagram"]
        if title:
            lines.append(f"    title {title}")
        lines.append("")

        # Declare participants
        for p in participants:
            alias = self._sanitize_id(p)
            # Use short name (last segment) for display
            display = p.rsplit(".", 1)[-1] if "." in p else p
            lines.append(f"    participant {alias} as {display}")
        lines.append("")

        # Track which group indices are active
        group_starts: dict[int, dict[str, object]] = {
            int(str(g.get("start", -1))): g for g in groups
        }
        group_ends: set[int] = {
            int(str(g.get("end", -1))) for g in groups
        }

        # Render messages with interleaved notes and groups
        note_map: dict[str, str] = {
            str(n.get("over", "")): str(n.get("text", "")) for n in notes
        }
        for idx, msg in enumerate(messages):
            # Open group if one starts at this index
            if idx in group_starts:
                grp = group_starts[idx]
                gtype = str(grp.get("type", "alt"))
                glabel = str(grp.get("label", ""))
                lines.append(f"    {gtype} {glabel}")

            src = self._sanitize_id(msg["from"])
            tgt = self._sanitize_id(msg["to"])
            label = msg.get("label", "")
            msg_type = msg.get("type", "sync")

            if msg_type == "reply":
                lines.append(f"    {src}-->>+{tgt}: {label}")
            elif msg_type == "async":
                lines.append(f"    {src}->>+{tgt}: {label}")
            else:
                lines.append(f"    {src}->>>{tgt}: {label}")

            # Insert note if one references the target
            target_name = msg["to"]
            if target_name in note_map:
                note_alias = self._sanitize_id(target_name)
                lines.append(
                    f"    Note over {note_alias}: {note_map.pop(target_name)}"
                )

            # Close group if one ends at this index
            if idx in group_ends:
                lines.append("    end")

        lines.append("")
        return "\n".join(lines) + "\n"

    # -- PlantUML renderer ----------------------------------------------

    def _sequence_plantuml(
        self,
        title: str,
        participants: list[str],
        messages: list[dict[str, str]],
        notes: list[dict[str, str]],
        groups: list[dict[str, object]],
    ) -> str:
        """Render a PlantUML @startuml/@enduml sequence block."""
        lines = ["@startuml"]
        if title:
            lines.append(f"title {title}")
        lines.append("")

        # Declare participants
        for p in participants:
            alias = self._sanitize_id(p)
            display = p.rsplit(".", 1)[-1] if "." in p else p
            lines.append(f'participant "{display}" as {alias}')
        lines.append("")

        group_starts: dict[int, dict[str, object]] = {
            int(str(g.get("start", -1))): g for g in groups
        }
        group_ends: set[int] = {
            int(str(g.get("end", -1))) for g in groups
        }

        note_map: dict[str, str] = {
            str(n.get("over", "")): str(n.get("text", "")) for n in notes
        }

        for idx, msg in enumerate(messages):
            if idx in group_starts:
                grp = group_starts[idx]
                gtype = str(grp.get("type", "alt"))
                glabel = str(grp.get("label", ""))
                lines.append(f"{gtype} {glabel}")

            src = self._sanitize_id(msg["from"])
            tgt = self._sanitize_id(msg["to"])
            label = msg.get("label", "")
            msg_type = msg.get("type", "sync")

            if msg_type == "reply":
                lines.append(f"{src} --> {tgt}: {label}")
            elif msg_type == "async":
                lines.append(f"{src} ->> {tgt}: {label}")
            else:
                lines.append(f"{src} -> {tgt}: {label}")

            target_name = msg["to"]
            if target_name in note_map:
                note_alias = self._sanitize_id(target_name)
                lines.append(f'note over {note_alias}: {note_map.pop(target_name)}')

            if idx in group_ends:
                lines.append("end")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines) + "\n"

    # ==================================================================
    # D2 format renderers (Epic 81.1, 81.2, 81.4)
    # ==================================================================

    def _d2_theme_block(self) -> list[str]:
        """Return D2 directives for the active theme.

        Supports ``default``, ``sketch``, and ``terminal`` themes.
        """
        theme = getattr(self, "_d2_theme", "default")
        if theme == "sketch":
            return ["vars: {", "  d2-config: {", "    sketch: true", "  }", "}"]
        if theme == "terminal":
            return [
                "vars: {",
                "  d2-config: {",
                "    theme-id: 200",
                "  }",
                "}",
            ]
        return []

    # -- D2: dependency -------------------------------------------------

    def _dependency_to_d2(
        self,
        graph: ImportGraph,
        direction: str,
        show_external: bool,
    ) -> tuple[str, int, int]:
        """Render an import graph as a D2 diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        modules = list(graph.modules)
        truncated = len(modules) > _MAX_DEPENDENCY_NODES
        if truncated:
            modules = modules[:_MAX_DEPENDENCY_NODES]
        module_set = set(modules)

        packages: dict[str, list[str]] = {}
        for mod in modules:
            parts = mod.split("/")
            pkg = parts[0] if len(parts) > 1 else ""
            packages.setdefault(pkg, []).append(mod)

        d2_direction = "right" if direction == "LR" else "down"
        lines: list[str] = [f"direction: {d2_direction}"]
        lines.extend(self._d2_theme_block())
        lines.append("")

        node_count = 0
        for pkg, pkg_modules in sorted(packages.items()):
            if pkg:
                pkg_id = self._sanitize_id(pkg)
                lines.append(f"{pkg_id}: {pkg} {{")
                for mod in sorted(pkg_modules):
                    mod_id = self._sanitize_id(mod)
                    label = mod.split("/")[-1]
                    lines.append(f"  {mod_id}: {label}")
                    node_count += 1
                lines.append("}")
            else:
                for mod in sorted(pkg_modules):
                    mod_id = self._sanitize_id(mod)
                    label = mod.split("/")[-1]
                    lines.append(f"{mod_id}: {label}")
                    node_count += 1

        lines.append("")

        edge_count = 0
        for edge in graph.edges:
            if edge.source not in module_set or edge.target not in module_set:
                continue
            src_id = self._sanitize_id(edge.source)
            tgt_id = self._sanitize_id(edge.target)
            if edge.import_type in ("type_checking", "conditional", "lazy"):
                lines.append(f"{src_id} -> {tgt_id}: {{style.stroke-dash: 3}}")
            else:
                lines.append(f"{src_id} -> {tgt_id}")
            edge_count += 1

        if show_external:
            external_ids: set[str] = set()
            for mod_path, ext_list in graph.external_imports.items():
                if mod_path not in module_set:
                    continue
                src_id = self._sanitize_id(mod_path)
                for ext_name in ext_list:
                    ext_top = ext_name.split(".")[0]
                    ext_id = self._sanitize_id(ext_top)
                    if ext_id not in external_ids:
                        lines.append(f"{ext_id}: {ext_top} {{shape: cloud}}")
                        external_ids.add(ext_id)
                        node_count += 1
                    lines.append(
                        f"{src_id} -> {ext_id}: {{style.stroke-dash: 3}}"
                    )
                    edge_count += 1

        if truncated:
            lines.append(
                f"# Truncated: showing {_MAX_DEPENDENCY_NODES}"
                f" of {len(graph.modules)} modules"
            )

        content = "\n".join(lines) + "\n"
        return content, node_count, edge_count

    # -- D2: class hierarchy --------------------------------------------

    def _classes_to_d2(
        self,
        classes: list[tuple[str, ClassInfo]],
    ) -> tuple[str, int, int]:
        """Render classes as a D2 class diagram.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        classes = classes[:_MAX_CLASS_NODES]
        class_names = {cls.name for _, cls in classes}

        lines: list[str] = list(self._d2_theme_block())
        if lines:
            lines.append("")
        edge_count = 0

        for _module, cls in classes:
            cls_id = self._sanitize_id(cls.name)
            lines.append(f"{cls_id}: {cls.name} {{")
            lines.append("  shape: class")

            for var in cls.class_variables:
                annotation = var.annotation or ""
                if annotation:
                    lines.append(f"  +{var.name}: {annotation}")
                else:
                    lines.append(f"  +{var.name}")

            for method in cls.methods:
                prefix = "-" if method.name.startswith("_") else "+"
                ret = ""
                if method.return_annotation:
                    ret = f" {method.return_annotation}"
                lines.append(f"  {prefix}{method.name}(){ret}")

            lines.append("}")
            lines.append("")

        for _module, cls in classes:
            cls_id = self._sanitize_id(cls.name)
            for base in cls.bases:
                base_simple = base.split(".")[-1]
                if base_simple in class_names:
                    base_id = self._sanitize_id(base_simple)
                    lines.append(
                        f"{cls_id} -> {base_id}: {{style.stroke-dash: 3}}"
                    )
                    edge_count += 1

        content = "\n".join(lines) + "\n"
        return content, len(classes), edge_count

    # -- D2: module map -------------------------------------------------

    def _module_map_to_d2(
        self,
        module_map: ModuleMap,
        direction: str,
    ) -> tuple[str, int, int]:
        """Render a module map as a D2 diagram with nested containers.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        d2_direction = "right" if direction == "LR" else "down"
        lines: list[str] = [f"direction: {d2_direction}"]
        lines.extend(self._d2_theme_block())
        lines.append("")

        project_id = self._sanitize_id(module_map.project_name)
        lines.append(f"{project_id}: {module_map.project_name} {{")
        node_count = self._emit_module_nodes_d2(
            module_map.module_tree, lines, indent=2
        )
        lines.append("}")

        content = "\n".join(lines) + "\n"
        return content, node_count, 0

    def _emit_module_nodes_d2(
        self,
        nodes: list[ModuleNode],
        lines: list[str],
        indent: int,
    ) -> int:
        """Recursively emit D2 nodes for a module tree.

        Returns:
            The number of nodes emitted.
        """
        pad = " " * indent
        count = 0

        for node in nodes:
            node_id = self._sanitize_id(node.path or node.name)
            if node.is_package:
                label = f"{node.name}/"
                lines.append(f"{pad}{node_id}: {label} {{")
                count += self._emit_module_nodes_d2(
                    node.submodules, lines, indent + 2
                )
                lines.append(f"{pad}}}")
            else:
                label_parts: list[str] = [node.name]
                stats: list[str] = []
                if node.function_count:
                    stats.append(f"{node.function_count}F")
                if node.class_count:
                    stats.append(f"{node.class_count}C")
                if stats:
                    label_parts.append(f" ({', '.join(stats)})")
                label = "".join(label_parts)
                lines.append(f"{pad}{node_id}: {label}")
                count += 1

        return count

    # -- D2: ER diagram -------------------------------------------------

    def _models_to_d2_er(
        self,
        models: list[tuple[str, ClassInfo]],
    ) -> tuple[str, int, int]:
        """Render model classes as a D2 ER diagram using sql_table shapes.

        Returns:
            A tuple of ``(content, node_count, edge_count)``.
        """
        models = models[:_MAX_CLASS_NODES]
        model_names = {cls.name for _, cls in models}

        lines: list[str] = list(self._d2_theme_block())
        if lines:
            lines.append("")
        edge_count = 0

        for _module, cls in models:
            cls_id = self._sanitize_id(cls.name)
            lines.append(f"{cls_id}: {cls.name} {{")
            lines.append("  shape: sql_table")
            for var in cls.class_variables:
                er_type = self._map_python_type(var.annotation or "")
                lines.append(f"  {var.name}: {er_type}")
            lines.append("}")
            lines.append("")

        for _module, cls in models:
            cls_id = self._sanitize_id(cls.name)
            for var in cls.class_variables:
                annotation = var.annotation or ""
                for other_name in model_names:
                    if other_name == cls.name:
                        continue
                    if other_name in annotation:
                        other_id = self._sanitize_id(other_name)
                        lines.append(f"{cls_id} -> {other_id}: has")
                        edge_count += 1

        content = "\n".join(lines) + "\n"
        return content, len(models), edge_count

    # -- D2: C4 context -------------------------------------------------

    def _c4_context_d2(
        self,
        name: str,
        description: str,
        actors: list[tuple[str, str]],
    ) -> tuple[str, int, int]:
        """Render a C4 System Context as a D2 diagram."""
        lines: list[str] = list(self._d2_theme_block())
        if lines:
            lines.append("")

        node_count = 1 + len(actors)
        edge_count = len(actors)

        sys_id = self._sanitize_id(name)
        lines.append(f"{sys_id}: {name} {{")
        lines.append(f"  tooltip: {description}")
        lines.append("}")
        lines.append("")

        for actor_name, _actor_desc in actors:
            aid = self._sanitize_id(actor_name)
            if actor_name in ("Database",):
                lines.append(f"{aid}: {actor_name} {{shape: cylinder}}")
            elif actor_name in ("ExternalAPI",):
                lines.append(f"{aid}: {actor_name} {{shape: cloud}}")
            else:
                lines.append(f"{aid}: {actor_name} {{shape: person}}")

        lines.append("")
        for actor_name, _ in actors:
            aid = self._sanitize_id(actor_name)
            lines.append(f"{aid} -> {sys_id}: Uses")

        lines.append("")
        return "\n".join(lines) + "\n", node_count, edge_count

    # -- D2: C4 container -----------------------------------------------

    def _c4_container_d2(
        self,
        name: str,
        containers: list[tuple[str, str, str]],
    ) -> tuple[str, int, int]:
        """Render a C4 Container diagram as D2 with nested containers."""
        lines: list[str] = list(self._d2_theme_block())
        if lines:
            lines.append("")

        sys_id = self._sanitize_id(name)
        lines.append(f"{sys_id}: {name} {{")

        edges = 0
        for cname, tech, desc in containers:
            cid = self._sanitize_id(cname)
            lines.append(f"  {cid}: {cname} {{")
            lines.append(f"    tooltip: \"{tech} - {desc}\"")
            lines.append("  }")

        lines.append("}")
        lines.append("")

        if len(containers) > 1:
            first_id = self._sanitize_id(containers[0][0])
            for i in range(1, min(len(containers), 5)):
                cid = self._sanitize_id(containers[i][0])
                lines.append(f"{sys_id}.{first_id} -> {sys_id}.{cid}: Uses")
                edges += 1

        lines.append("")
        return "\n".join(lines) + "\n", len(containers), edges

    # -- D2: C4 component -----------------------------------------------

    def _c4_component_d2(
        self,
        container_name: str,
        components: list[tuple[str, str, int]],
    ) -> tuple[str, int, int]:
        """Render a C4 Component diagram as D2."""
        lines: list[str] = list(self._d2_theme_block())
        if lines:
            lines.append("")

        cid = self._sanitize_id(container_name)
        lines.append(f"{cid}: {container_name} {{")

        for cname, desc, _ in components[:_MAX_DEPENDENCY_NODES]:
            comp_id = self._sanitize_id(cname)
            lines.append(f"  {comp_id}: {cname} {{")
            lines.append(f"    tooltip: \"{desc}\"")
            lines.append("  }")

        lines.append("}")
        lines.append("")
        return "\n".join(lines) + "\n", len(components), 0

    # -- D2: sequence diagram -------------------------------------------

    def _sequence_d2(
        self,
        title: str,
        participants: list[str],
        messages: list[dict[str, str]],
        notes: list[dict[str, str]],
        groups: list[dict[str, object]],
    ) -> str:
        """Render a D2 sequence diagram."""
        lines: list[str] = list(self._d2_theme_block())
        if lines:
            lines.append("")

        lines.append("shape: sequence_diagram")
        if title:
            lines.append(f"# {title}")
        lines.append("")

        for p in participants:
            alias = self._sanitize_id(p)
            display = p.rsplit(".", 1)[-1] if "." in p else p
            lines.append(f"{alias}: {display}")
        lines.append("")

        note_map: dict[str, str] = {
            str(n.get("over", "")): str(n.get("text", "")) for n in notes
        }

        for msg in messages:
            src = self._sanitize_id(msg["from"])
            tgt = self._sanitize_id(msg["to"])
            label = msg.get("label", "")
            msg_type = msg.get("type", "sync")

            if msg_type == "reply":
                lines.append(
                    f"{src} -> {tgt}: {label} {{style.stroke-dash: 3}}"
                )
            elif msg_type == "async":
                lines.append(
                    f"{src} -> {tgt}: {label} {{style.stroke-dash: 5}}"
                )
            else:
                lines.append(f"{src} -> {tgt}: {label}")

            target_name = msg["to"]
            if target_name in note_map:
                note_alias = self._sanitize_id(target_name)
                lines.append(
                    f"{note_alias}.\"note\": {note_map.pop(target_name)}"
                )

        lines.append("")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Pattern card (archetype poster) — STORY-100.3
    # ------------------------------------------------------------------

    def _generate_pattern_card(
        self,
        project_root: Path,
        output_format: str,
    ) -> DiagramResult:
        """Generate a single-page archetype poster for the project.

        Classifies the project using :class:`PatternClassifier` and renders a
        compact Mermaid flowchart showing the archetype, top packages colored
        by semantic role, and a legend. Regardless of ``output_format``, the
        rendered content is Mermaid — pattern_card is intentionally
        README-embeddable.
        """
        try:
            from docs_mcp.analyzers.dependency import ImportGraphBuilder
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer
            from docs_mcp.analyzers.pattern import PatternClassifier

            module_map = ModuleMapAnalyzer().analyze(project_root, depth=3)
            graph = ImportGraphBuilder().build(project_root)
            result = PatternClassifier().classify(
                project_root, module_map=module_map, import_graph=graph
            )
        except Exception:
            logger.warning("pattern_card_build_failed", path=str(project_root))
            return DiagramResult(
                diagram_type="pattern_card",
                format=output_format,
                content="",
                degraded=True,
            )

        packages = self._select_pattern_packages(module_map, graph)
        content = self._render_pattern_card_mermaid(result, packages)
        return DiagramResult(
            diagram_type="pattern_card",
            format=output_format,
            content=content,
            node_count=len(packages),
            edge_count=content.count("-->"),
            degraded=not packages,
        )

    def _select_pattern_packages(
        self,
        module_map: ModuleMap,
        graph: ImportGraph,
    ) -> list[tuple[str, str]]:
        """Pick up to ``_MAX_PATTERN_NODES`` packages, each tagged by role."""
        names: list[str] = []
        seen: set[str] = set()
        for node in module_map.module_tree:
            if node.name and node.name not in seen:
                names.append(node.name)
                seen.add(node.name)
            for child in node.submodules:
                if child.name and child.name not in seen:
                    names.append(child.name)
                    seen.add(child.name)

        if graph.most_imported:
            rank: dict[str, int] = {}
            for idx, module in enumerate(graph.most_imported):
                first = module.split("/")[0]
                rank.setdefault(first, len(graph.most_imported) - idx)
            names.sort(key=lambda n: -rank.get(n, 0))

        names = names[:_MAX_PATTERN_NODES]
        return [(n, self._classify_role(n)) for n in names]

    @staticmethod
    def _role_c4_updateelementstyle_lines(
        elements: list[tuple[str, str]],
        indent: str = "    ",
    ) -> list[str]:
        """Emit C4-Mermaid UpdateElementStyle calls for each (id, role)."""
        out: list[str] = []
        for element_id, role in elements:
            color = _ROLE_COLORS[role]
            text = "#000" if role == "presentation" else "#fff"
            out.append(
                f'{indent}UpdateElementStyle({element_id}, '
                f'$bgColor="{color}", $fontColor="{text}", $borderColor="#333")'
            )
        return out

    @staticmethod
    def _role_classdef_mermaid_lines() -> list[str]:
        """Return the fixed four-role classDef lines for Mermaid renderers."""
        out: list[str] = []
        for role, color in _ROLE_COLORS.items():
            text = "#000" if role == "presentation" else "#fff"
            out.append(
                f"    classDef {role} fill:{color},stroke:#333,color:{text}"
            )
        return out

    def _role_for_top_component(self, path_or_name: str) -> str:
        """Classify the top-level component of a path/name into a role."""
        first = path_or_name.split("/", 1)[0].split(".", 1)[0]
        return self._classify_role(first)

    @staticmethod
    def _classify_role(name: str) -> str:
        """Classify a package name into one of four semantic roles."""
        normalized = name.lower()
        for role, kws in _ROLE_KEYWORDS.items():
            if normalized in kws:
                return role
        for role, kws in _ROLE_KEYWORDS.items():
            if any(kw in normalized for kw in kws):
                return role
        return "infra"

    def _render_pattern_card_mermaid(
        self,
        result: ArchetypeResult,
        packages: list[tuple[str, str]],
    ) -> str:
        """Render the pattern-card poster as Mermaid."""
        archetype = result.archetype.upper().replace("_", " ")
        confidence = f"{result.confidence:.2f}"
        evidence_note = ""
        if result.evidence:
            evidence_note = result.evidence[0].replace('"', "'")[:120]

        lines: list[str] = ["flowchart TD"]
        header_label = f"{archetype} (confidence {confidence})"
        if evidence_note:
            header_label += f"<br/>{evidence_note}"
        lines.append(f'    header["{header_label}"]')

        # Render packages grouped by role, iteration order fixed.
        role_nodes: dict[str, list[str]] = {r: [] for r in _ROLE_COLORS}
        for idx, (name, role) in enumerate(packages):
            node_id = f"p{idx}_{self._sanitize_id(name)}"
            role_nodes[role].append(node_id)
            lines.append(f'    {node_id}["{name}"]:::{role}')

        prev_anchor = "header"
        for role in ("presentation", "business", "data", "infra"):
            if role_nodes[role]:
                lines.append(f"    {prev_anchor} --> {role_nodes[role][0]}")
                prev_anchor = role_nodes[role][0]

        # Legend block (always present, regardless of which roles fired).
        lines.append("    subgraph legend[\"Legend\"]")
        for role in _ROLE_COLORS:
            lines.append(
                f'        L_{role}["{role.capitalize()}"]:::{role}'
            )
        lines.append("    end")

        for role, color in _ROLE_COLORS.items():
            text = "#000" if role == "presentation" else "#fff"
            lines.append(
                f"    classDef {role} fill:{color},stroke:#333,color:{text}"
            )

        return "\n".join(lines) + "\n"
