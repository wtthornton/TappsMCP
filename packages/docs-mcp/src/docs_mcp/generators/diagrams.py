"""Diagram generation for Python project structures.

Generates Mermaid and PlantUML diagrams from project analysis results,
including dependency graphs, class hierarchies, module maps, and ER diagrams.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import structlog
from pydantic import BaseModel

from docs_mcp.constants import SKIP_DIRS

if TYPE_CHECKING:
    from docs_mcp.analyzers.dependency import ImportGraph
    from docs_mcp.analyzers.models import ModuleMap, ModuleNode
    from docs_mcp.extractors.models import ClassInfo

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)  # type: ignore[assignment]

# Maximum number of nodes before truncation in dependency/module diagrams.
_MAX_DEPENDENCY_NODES = 50
# Maximum number of classes rendered in class/ER diagrams.
_MAX_CLASS_NODES = 30
# Maximum number of files to scan when extracting classes project-wide.
_MAX_SCAN_FILES = 30
# Minimum classes/modules before a quality warning is emitted.
_MIN_RESULTS_THRESHOLD = 3

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

    Supports four diagram types (dependency, class_hierarchy, module_map,
    er_diagram) in two output formats (mermaid, plantuml).
    """

    VALID_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "dependency",
            "class_hierarchy",
            "module_map",
            "er_diagram",
        }
    )
    VALID_FORMATS: ClassVar[frozenset[str]] = frozenset({"mermaid", "plantuml"})

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
    ) -> DiagramResult:
        """Generate a diagram for a project.

        Args:
            project_root: Root directory of the project.
            diagram_type: One of ``dependency``, ``class_hierarchy``,
                ``module_map``, or ``er_diagram``.
            output_format: Output format -- ``mermaid`` or ``plantuml``.
            scope: Scope of the diagram; ``project`` for the whole project
                or a file path for a single file (class/ER diagrams).
            depth: Depth limit for module map / dependency diagrams.
            direction: Graph direction (``TD``, ``LR``, etc.).
            show_external: Whether to include external dependencies.

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
                    lines.append(f'        {mod_id}["{label}"]')
                    emitted_ids.add(mod_id)
                    node_count += 1
                lines.append("    end")
            else:
                for mod in sorted(pkg_modules):
                    mod_id = self._sanitize_id(mod)
                    label = mod.split("/")[-1]
                    lines.append(f'    {mod_id}["{label}"]')
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
        for src_dir in source_dirs:
            for py_file in sorted(src_dir.rglob("*.py")):
                if self._should_skip_path(py_file):
                    skipped_count += 1
                    continue
                if file_count >= _MAX_SCAN_FILES:
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

        for _module, cls in classes:
            cls_id = self._sanitize_id(cls.name)
            lines.append(f"    class {cls_id} {{")

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
            module_map.module_tree, lines, indent=8
        )
        lines.append("    end")

        content = "\n".join(lines) + "\n"
        # Module maps have no edges -- they show structure only.
        return content, node_count, 0

    def _emit_module_nodes_mermaid(
        self,
        nodes: list[ModuleNode],
        lines: list[str],
        indent: int,
    ) -> int:
        """Recursively emit Mermaid nodes for a module tree.

        Returns:
            The number of nodes emitted.
        """

        pad = " " * indent
        count = 0

        for node in nodes:
            node_id = self._sanitize_id(node.path or node.name)
            if node.is_package:
                label = f"{node.name}/"
                lines.append(f'{pad}subgraph {node_id}["{label}"]')
                count += self._emit_module_nodes_mermaid(
                    node.submodules, lines, indent + 4
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
                lines.append(f'{pad}{node_id}["{label}"]')
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
