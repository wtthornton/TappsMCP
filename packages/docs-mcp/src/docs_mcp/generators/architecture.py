"""Architecture document generator — produces a comprehensive, visually rich
HTML architecture report for any Python project.

Combines module map analysis, dependency graph analysis, API surface analysis,
and project metadata into a single self-contained HTML document with embedded
SVG diagrams, CSS styling, and detailed prose descriptions.
"""

from __future__ import annotations

import html
import math
import re
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

import structlog
from pydantic import BaseModel

from docs_mcp.constants import SKIP_DIRS

if TYPE_CHECKING:
    from docs_mcp.analyzers.dependency import ImportGraph
    from docs_mcp.analyzers.models import ModuleMap, ModuleNode
    from docs_mcp.generators.metadata import ProjectMetadata

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

_MAX_COMPONENTS = 40
_MAX_DEPENDENCY_EDGES = 80
_MAX_CLASSES_LISTED = 50
_MAX_SCAN_FILES = 60
_MAX_SUBMODULES_SHOWN = 12
_CIRCULAR_LAYOUT_THRESHOLD = 10
_MAX_NAME_LEN_CIRCULAR = 14
_MAX_NAME_LEN_GRID = 16
_MAX_METHODS_SHOWN = 8
_MAX_API_CLASSES = 30
_MAX_API_PER_MODULE = 6
_MAX_FLOW_ITEM_LEN = 20
_MIN_LAYERS_FOR_FLOW = 2
_LARGE_PACKAGE_THRESHOLD = 15
_MODULARITY_HIGH = 5
_MODULARITY_MED = 3
_COUPLING_LOW = 8
_COUPLING_HIGH = 20
_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+")

# Directories to exclude from architecture analysis beyond SKIP_DIRS.
_ARCH_SKIP_DIRS: frozenset[str] = frozenset({
    "tests", "test", "integration", "scripts", "examples", "docs",
    "benchmarks", "docker-mcp", ".github", ".claude", ".tapps-mcp",
})

# Patterns that indicate a file/package is not a real source package.
_NOISE_PATTERNS: tuple[str, ...] = (
    "conftest", "test_", "sample", "example", "fixture",
)
_GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;500;600;700"
    "&family=Outfit:wght@400;500;600;700;800"
    "&display=swap"
)

# ---------------------------------------------------------------------------
# Color palette for component boxes
# ---------------------------------------------------------------------------

_PALETTE: list[tuple[str, str, str]] = [
    # (gradient_start, gradient_end, text_color) — HomeIQ Design System
    ("#14b8a6", "#2dd4bf", "#0a0a0f"),  # teal (primary accent)
    ("#d4a847", "#e8c060", "#0a0a0f"),  # gold (secondary accent)
    ("#0d9488", "#14b8a6", "#fafafa"),  # teal-dark
    ("#38bdf8", "#60a5fa", "#0a0a0f"),  # info blue
    ("#22c55e", "#34d399", "#0a0a0f"),  # success green
    ("#f59e0b", "#fbbf24", "#0a0a0f"),  # warning amber
    ("#8b5cf6", "#a78bfa", "#fafafa"),  # violet
    ("#06b6d4", "#22d3ee", "#0a0a0f"),  # cyan
    ("#ef4444", "#f87171", "#fafafa"),  # error red
    ("#ec4899", "#f472b6", "#fafafa"),  # pink
]


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class ArchitectureResult(BaseModel):
    """Result of architecture document generation."""

    content: str
    format: str = "html"
    package_count: int = 0
    module_count: int = 0
    edge_count: int = 0
    class_count: int = 0
    degraded: bool = False


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class ArchitectureGenerator:
    """Generates a comprehensive, self-contained HTML architecture report.

    The report includes:
    - Project purpose and overview (extracted from metadata and docstrings)
    - High-level architecture diagram (SVG)
    - Package/component breakdown with detailed descriptions
    - Dependency flow diagram (SVG)
    - Public API surface summary
    - Entry points and configuration
    """

    VALID_FORMATS: ClassVar[frozenset[str]] = frozenset({"html"})

    def generate(
        self,
        project_root: Path,
        *,
        output_format: str = "html",
        title: str = "",
        subtitle: str = "",
    ) -> ArchitectureResult:
        """Generate the architecture document.

        Args:
            project_root: Root directory of the project.
            output_format: Output format (currently only ``html``).
            title: Custom title override. Defaults to project name.
            subtitle: Custom subtitle / tagline.

        Returns:
            An :class:`ArchitectureResult` with the rendered content.
        """
        project_root = project_root.resolve()

        # 1. Gather metadata
        metadata = self._extract_metadata(project_root)
        proj_name = title or metadata.name or project_root.name
        proj_subtitle = subtitle or metadata.description or ""

        # 2. Build module map
        module_map = self._build_module_map(project_root)

        # 3. Build dependency graph
        dep_graph = self._build_dependency_graph(project_root)

        # 4. Collect API surface info
        api_info = self._collect_api_info(project_root, module_map)

        # 5. Collect filtered packages for accurate stats
        packages = self._collect_packages(module_map)
        filtered_pkg_count = len(packages)
        filtered_mod_count = sum(int(p.get("module_count", 0)) for p in packages)

        # 5b. For docs-heavy/non-Python projects with no packages found,
        # extract component info from markdown documentation.
        degraded = False
        if not packages and not api_info:
            doc_packages = self._extract_from_docs(project_root)
            if doc_packages:
                packages = doc_packages
                filtered_pkg_count = len(packages)
                filtered_mod_count = sum(int(p.get("module_count", 0)) for p in packages)
                degraded = True
                if not proj_subtitle:
                    proj_subtitle = "Architecture extracted from documentation"

        # 6. Render HTML (pass pre-collected packages to avoid re-collection)
        content = self._render_html(
            project_root=project_root,
            proj_name=proj_name,
            proj_subtitle=proj_subtitle,
            metadata=metadata,
            module_map=module_map,
            dep_graph=dep_graph,
            api_info=api_info,
            packages=packages,
        )

        edge_count = dep_graph.total_internal_imports if dep_graph else 0

        return ArchitectureResult(
            content=content,
            format="html",
            package_count=filtered_pkg_count,
            module_count=filtered_mod_count,
            edge_count=edge_count,
            class_count=sum(int(c.get("method_count", 0)) for c in api_info),
            degraded=degraded,
        )

    # ------------------------------------------------------------------
    # Data gathering
    # ------------------------------------------------------------------

    def _extract_metadata(self, project_root: Path) -> ProjectMetadata:
        """Extract project metadata from config files."""
        try:
            from docs_mcp.generators.metadata import MetadataExtractor

            return MetadataExtractor().extract(project_root)
        except Exception:
            from docs_mcp.generators.metadata import ProjectMetadata as PMeta

            return PMeta(name=project_root.name)

    def _build_module_map(self, project_root: Path) -> ModuleMap | None:
        """Build the hierarchical module map."""
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            return ModuleMapAnalyzer().analyze(project_root, depth=4)
        except Exception:
            logger.debug("architecture_module_map_failed")
            return None

    def _build_dependency_graph(self, project_root: Path) -> ImportGraph | None:
        """Build the import dependency graph."""
        try:
            from docs_mcp.analyzers.dependency import ImportGraphBuilder

            return ImportGraphBuilder().build(project_root)
        except Exception:
            logger.debug("architecture_dependency_graph_failed")
            return None

    def _collect_api_info(
        self,
        project_root: Path,
        module_map: ModuleMap | None,
    ) -> list[dict[str, Any]]:
        """Collect public API classes from the project."""
        try:
            from docs_mcp.extractors.python import PythonExtractor

            extractor = PythonExtractor()
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        source_dirs = self._resolve_source_dirs(project_root)
        file_count = 0

        skip_all = SKIP_DIRS | _ARCH_SKIP_DIRS
        for src_dir in source_dirs:
            for py_file in sorted(src_dir.rglob("*.py")):
                if any(part in skip_all for part in py_file.parts):
                    continue
                if self._is_noise_path(py_file):
                    continue
                if py_file.name.startswith("_") and py_file.name != "__init__.py":
                    continue
                if any(py_file.name.startswith(p) for p in _NOISE_PATTERNS):
                    continue
                if file_count >= _MAX_SCAN_FILES:
                    break
                file_count += 1

                try:
                    info = extractor.extract(py_file, project_root=project_root)
                except Exception:
                    logger.debug("extract_failed", path=str(py_file))
                    continue

                for cls in info.classes:
                    if cls.name.startswith("_"):
                        continue
                    public_methods = [
                        m.name for m in cls.methods if not m.name.startswith("_")
                    ]
                    results.append({
                        "name": cls.name,
                        "module": py_file.stem,
                        "path": str(py_file.relative_to(project_root)).replace(
                            "\\", "/",
                        ),
                        "bases": cls.bases,
                        "docstring": cls.docstring or "",
                        "method_count": len(cls.methods),
                        "public_methods": public_methods[:10],
                        "decorators": [d.name for d in cls.decorators],
                    })

                if len(results) >= _MAX_CLASSES_LISTED:
                    break

        return results

    def _extract_from_docs(self, project_root: Path) -> list[dict[str, Any]]:
        """Extract component info from markdown documentation files.

        Used as a fallback when no Python source packages are found.
        Parses top-level headings from markdown files in the project to
        identify components, and treats each docs directory or major
        document as a component.
        """
        import os

        skip_all = SKIP_DIRS | _ARCH_SKIP_DIRS
        packages: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Scan for markdown directories with architecture/component content
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [
                d for d in dirnames
                if d not in skip_all and not d.startswith(".")
            ]
            current = Path(dirpath)
            md_files = [f for f in filenames if f.lower().endswith((".md", ".rst"))]
            if not md_files:
                continue

            rel_dir = str(current.relative_to(project_root)).replace("\\", "/")
            if rel_dir == ".":
                # Treat root-level docs as individual components
                for md_file in sorted(md_files)[:_MAX_COMPONENTS]:
                    name = Path(md_file).stem
                    if name.lower() in ("readme", "license", "changelog") or name in seen:
                        continue
                    seen.add(name)
                    try:
                        content = (current / md_file).read_text(
                            encoding="utf-8", errors="replace"
                        )
                        docstring = self._extract_first_paragraph(content)
                    except OSError:
                        docstring = ""
                    packages.append({
                        "name": name,
                        "path": md_file,
                        "is_package": False,
                        "docstring": docstring,
                        "module_count": 1,
                        "function_count": 0,
                        "class_count": 0,
                        "submodules": [],
                    })
            else:
                # Directory with docs - treat as a component
                dir_name = current.name
                if dir_name in seen:
                    continue
                seen.add(dir_name)
                docstring = ""
                # Try to get description from README or index
                for idx_name in ("README.md", "index.md", "overview.md"):
                    idx_path = current / idx_name
                    if idx_path.exists():
                        try:
                            content = idx_path.read_text(encoding="utf-8", errors="replace")
                            docstring = self._extract_first_paragraph(content)
                        except OSError:
                            pass
                        break

                packages.append({
                    "name": dir_name,
                    "path": rel_dir,
                    "is_package": True,
                    "docstring": docstring,
                    "module_count": len(md_files),
                    "function_count": 0,
                    "class_count": 0,
                    "submodules": [Path(f).stem for f in sorted(md_files)[:_MAX_SUBMODULES_SHOWN]],
                })

            if len(packages) >= _MAX_COMPONENTS:
                break

        return packages

    @staticmethod
    def _extract_first_paragraph(content: str) -> str:
        """Extract the first non-heading paragraph from markdown content."""
        lines = content.splitlines()
        paragraph_lines: list[str] = []
        in_paragraph = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_paragraph:
                    break
                continue
            if stripped.startswith("#") or stripped.startswith("---") or stripped.startswith("==="):
                if in_paragraph:
                    break
                continue
            in_paragraph = True
            paragraph_lines.append(stripped)
            if len(paragraph_lines) >= 3:
                break
        return " ".join(paragraph_lines)[:200]

    def _resolve_source_dirs(self, project_root: Path) -> list[Path]:
        """Auto-detect source directories, skipping noise like tests/scripts."""
        skip_all = SKIP_DIRS | _ARCH_SKIP_DIRS
        results: list[Path] = []

        # Check for src/ layout first (standard Python packaging)
        src_dir = project_root / "src"
        if src_dir.is_dir():
            for d in sorted(src_dir.iterdir()):
                if (
                    d.is_dir()
                    and not d.name.startswith(".")
                    and d.name not in skip_all
                    and (d / "__init__.py").exists()
                ):
                    results.append(d)
            if results:
                return results

        # Check packages/ layout (monorepo with packages/*/src/*)
        pkgs_dir = project_root / "packages"
        if pkgs_dir.is_dir():
            for pkg_dir in sorted(pkgs_dir.iterdir()):
                if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
                    continue
                pkg_src = pkg_dir / "src"
                if pkg_src.is_dir():
                    for d in sorted(pkg_src.iterdir()):
                        if (
                            d.is_dir()
                            and not d.name.startswith(".")
                            and d.name not in skip_all
                            and (d / "__init__.py").exists()
                        ):
                            results.append(d)
            if results:
                return results

        # Fallback: top-level Python packages (skip noise dirs)
        for d in sorted(project_root.iterdir()):
            if (
                d.is_dir()
                and not d.name.startswith(".")
                and d.name not in skip_all
                and (d / "__init__.py").exists()
            ):
                results.append(d)

        return results or [project_root]

    @staticmethod
    def _is_noise_path(path: Path) -> bool:
        """Check if a path belongs to noise directories like .venv, tests, etc."""
        parts = {p.lower() for p in path.parts}
        noise = {"tests", "test", "scripts", "examples", ".venv",
                 ".venv-pyinstaller", "venv", "benchmarks"}
        return bool(parts & noise)

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def _render_html(
        self,
        *,
        project_root: Path,
        proj_name: str,
        proj_subtitle: str,
        metadata: ProjectMetadata,
        module_map: ModuleMap | None,
        dep_graph: ImportGraph | None,
        api_info: list[dict[str, Any]],
        packages: list[dict[str, Any]] | None = None,
    ) -> str:
        """Render the complete HTML architecture document."""
        safe_name = html.escape(proj_name)
        safe_subtitle = html.escape(proj_subtitle)

        # Use pre-collected packages or collect fresh
        if packages is None:
            packages = self._collect_packages(module_map)
        dep_edges = self._collect_edges(dep_graph, packages)

        sections: list[str] = []

        # Hero / title
        sections.append(self._render_hero(safe_name, safe_subtitle))

        # Executive summary (use filtered packages for accurate counts)
        sections.append(self._render_executive_summary(
            safe_name, safe_subtitle, metadata, module_map, dep_graph,
            api_info, packages,
        ))

        # Architecture overview SVG
        sections.append(self._render_architecture_diagram(safe_name, packages))

        # Data flow pipeline SVG
        sections.append(self._render_data_flow(packages))

        # Package deep-dive
        sections.append(self._render_package_details(packages, module_map))

        # Dependency flow SVG
        sections.append(self._render_dependency_flow(packages, dep_edges))

        # API surface (filtered + capped)
        if api_info:
            sections.append(self._render_api_surface(api_info))

        # Tech stack & configuration
        sections.append(self._render_tech_stack(metadata))

        # Architecture health & insights
        sections.append(self._render_health_insights(
            metadata, module_map, dep_graph, api_info, packages,
        ))

        # Footer with generation metadata (filtered counts)
        filtered_mod_count = sum(int(p.get("module_count", 0)) for p in packages)
        sections.append(self._render_footer(
            pkg_count=len(packages),
            mod_count=filtered_mod_count,
            cls_count=len(api_info),
        ))

        body = "\n".join(sections)
        return self._wrap_html(safe_name, body)

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _render_hero(self, name: str, subtitle: str) -> str:
        desc = f'<p class="hero-subtitle">{subtitle}</p>' if subtitle else ""
        return f"""
<section class="hero">
  <div class="hero-content">
    <h1 class="hero-title">{name}</h1>
    {desc}
    <p class="hero-meta">Architecture Report</p>
  </div>
</section>"""

    def _render_executive_summary(
        self,
        name: str,
        subtitle: str,
        metadata: ProjectMetadata,
        module_map: ModuleMap | None,
        dep_graph: ImportGraph | None,
        api_info: list[dict[str, Any]],
        packages: list[dict[str, Any]] | None = None,
    ) -> str:
        parts: list[str] = []
        parts.append('<section class="section" id="executive-summary">')
        parts.append('<h2 class="section-title">Executive Summary</h2>')

        # Purpose statement
        purpose = subtitle or metadata.description or "A software project."
        parts.append(f"""
<div class="purpose-block">
  <h3>Purpose &amp; Intent</h3>
  <p class="purpose-text">{html.escape(purpose)}</p>
</div>""")

        # Key stats — use filtered packages when available for accurate counts
        if packages is not None:
            pkg = len(packages)
            mod = sum(int(p.get("module_count", 0)) for p in packages)
        else:
            pkg = module_map.total_packages if module_map else 0
            mod = module_map.total_modules if module_map else 0
        api_count = module_map.public_api_count if module_map else 0
        deps = dep_graph.total_external_imports if dep_graph else 0
        cls_count = len(api_info)

        parts.append(f"""
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-number">{pkg}</div>
    <div class="stat-label">Packages</div>
  </div>
  <div class="stat-card">
    <div class="stat-number">{mod}</div>
    <div class="stat-label">Modules</div>
  </div>
  <div class="stat-card">
    <div class="stat-number">{cls_count}</div>
    <div class="stat-label">Public Classes</div>
  </div>
  <div class="stat-card">
    <div class="stat-number">{api_count}</div>
    <div class="stat-label">Public APIs</div>
  </div>
  <div class="stat-card">
    <div class="stat-number">{deps}</div>
    <div class="stat-label">External Deps</div>
  </div>
</div>""")

        # Metadata details
        if metadata.version or metadata.license or metadata.python_requires:
            parts.append('<div class="meta-details">')
            if metadata.version:
                parts.append(
                    f'<span class="meta-badge">v{html.escape(metadata.version)}</span>'
                )
            if metadata.python_requires:
                py_req = html.escape(metadata.python_requires)
                parts.append(
                    f'<span class="meta-badge">Python {py_req}</span>'
                )
            if metadata.license:
                parts.append(
                    f'<span class="meta-badge">{html.escape(metadata.license)}</span>'
                )
            parts.append("</div>")

        parts.append("</section>")
        return "\n".join(parts)

    def _render_architecture_diagram(
        self,
        name: str,
        packages: list[dict[str, Any]],
    ) -> str:
        """Render the high-level architecture SVG diagram."""
        if not packages:
            return ""

        parts: list[str] = []
        parts.append('<section class="section" id="architecture-diagram">')
        parts.append('<h2 class="section-title">High-Level Architecture</h2>')
        parts.append(
            "<p>The diagram below illustrates the major packages and components "
            "that comprise the system. Each box represents a distinct package or "
            "subsystem with its own responsibilities and boundaries.</p>"
        )

        svg = self._build_architecture_svg(name, packages)
        parts.append(f'<div class="diagram-container">{svg}</div>')
        parts.append("</section>")
        return "\n".join(parts)

    def _render_package_details(
        self,
        packages: list[dict[str, Any]],
        module_map: ModuleMap | None,
    ) -> str:
        """Render detailed descriptions of each package."""
        if not packages:
            return ""

        parts: list[str] = []
        parts.append('<section class="section" id="component-details">')
        parts.append('<h2 class="section-title">Component Deep-Dive</h2>')
        parts.append(
            "<p>Each component in the architecture serves a specific purpose, "
            "contributing to the overall system through well-defined responsibilities. "
            "Understanding these individual building blocks is essential for navigating "
            "the codebase, extending functionality, and maintaining the project over time.</p>"
        )

        for i, pkg in enumerate(packages):
            color_start, color_end, _ = _PALETTE[i % len(_PALETTE)]
            pkg_name = str(pkg["name"])
            safe_pkg_name = html.escape(pkg_name)
            docstring = str(pkg.get("docstring", ""))
            mod_count = int(pkg.get("module_count", 0))
            func_count = int(pkg.get("function_count", 0))
            cls_count = int(pkg.get("class_count", 0))
            submodules: list[str] = list(pkg.get("submodules", []))
            # Generate a value description
            value_text = self._generate_component_value(
                pkg_name, docstring, mod_count, func_count, cls_count,
            )

            parts.append(f"""
<div class="component-card">
  <div class="component-header" style="background: linear-gradient(
    135deg, {color_start}, {color_end});">
    <h3 class="component-name">{safe_pkg_name}</h3>
    <div class="component-stats">
      <span>{mod_count} modules</span>
      <span>{func_count} functions</span>
      <span>{cls_count} classes</span>
    </div>
  </div>
  <div class="component-body">
    <p class="component-description">{html.escape(value_text)}</p>""")

            if submodules:
                parts.append('    <div class="submodule-list">')
                parts.append("      <h4>Key Modules</h4>")
                parts.append("      <ul>")
                for sub in submodules[:_MAX_SUBMODULES_SHOWN]:
                    parts.append(f"        <li><code>{html.escape(sub)}</code></li>")
                if len(submodules) > _MAX_SUBMODULES_SHOWN:
                    extra = len(submodules) - _MAX_SUBMODULES_SHOWN
                    parts.append(
                        f"        <li><em>... and {extra} more</em></li>"
                    )
                parts.append("      </ul>")
                parts.append("    </div>")

            parts.append("  </div>")
            parts.append("</div>")

        parts.append("</section>")
        return "\n".join(parts)

    def _render_dependency_flow(
        self,
        packages: list[dict[str, Any]],
        edges: list[tuple[int, int]],
    ) -> str:
        """Render the dependency flow SVG diagram."""
        if not packages or not edges:
            return ""

        parts: list[str] = []
        parts.append('<section class="section" id="dependency-flow">')
        parts.append('<h2 class="section-title">Dependency Flow</h2>')
        parts.append(
            "<p>The dependency flow diagram reveals how information and control flow "
            "through the system. Arrows indicate import relationships between packages, "
            "showing which components depend on which. This visualization is crucial for "
            "understanding coupling, identifying potential circular dependencies, and "
            "planning refactoring efforts.</p>"
        )

        svg = self._build_dependency_svg(packages, edges)
        parts.append(f'<div class="diagram-container">{svg}</div>')
        parts.append("</section>")
        return "\n".join(parts)

    def _render_api_surface(self, api_info: list[dict[str, Any]]) -> str:
        """Render the public API surface section (capped and filtered)."""
        parts: list[str] = []
        parts.append('<section class="section" id="api-surface">')
        parts.append('<h2 class="section-title">Public API Surface</h2>')
        parts.append(
            "<p>The public API surface defines the contract between this project "
            "and its consumers. Classes listed below represent publicly accessible "
            "interfaces that external code may depend upon. This is a curated "
            f"selection of the {len(api_info)} public classes discovered.</p>"
        )

        # Group by module/path, skip noise paths
        by_module: dict[str, list[dict[str, Any]]] = {}
        for cls in api_info:
            mod = str(cls.get("path", cls.get("module", "unknown")))
            if any(noise in mod.lower() for noise in (
                "test", ".venv", "conftest", "sample", "fixture",
            )):
                continue
            by_module.setdefault(mod, []).append(cls)

        total_shown = 0
        for mod_path, classes in sorted(by_module.items()):
            if total_shown >= _MAX_API_CLASSES:
                break
            parts.append('<div class="api-module">')
            safe_path = html.escape(mod_path)
            parts.append(f'  <h4 class="api-module-path">{safe_path}</h4>')

            for cls in classes[:_MAX_API_PER_MODULE]:
                if total_shown >= _MAX_API_CLASSES:
                    break
                total_shown += 1
                cls_name = str(cls["name"])
                docstring = str(cls.get("docstring", ""))
                bases = list(cls.get("bases", []))
                methods = list(cls.get("public_methods", []))
                if bases:
                    joined = html.escape(", ".join(str(b) for b in bases))
                    base_text = (
                        f' <span class="api-bases">extends {joined}</span>'
                    )
                else:
                    base_text = ""
                first_line = docstring.split("\n", maxsplit=1)[0]
                doc_summary = html.escape(first_line) if docstring else ""

                parts.append(f"""
  <div class="api-class">
    <div class="api-class-header">
      <code class="api-class-name">{html.escape(cls_name)}</code>{base_text}
    </div>""")
                if doc_summary:
                    parts.append(f'    <p class="api-doc">{doc_summary}</p>')
                if methods:
                    methods_str = ", ".join(
                        f"<code>{html.escape(str(m))}</code>"
                        for m in methods[:_MAX_METHODS_SHOWN]
                    )
                    if len(methods) > _MAX_METHODS_SHOWN:
                        extra = len(methods) - _MAX_METHODS_SHOWN
                        methods_str += f" <em>+{extra} more</em>"
                    parts.append(
                        f'    <div class="api-methods">Methods: {methods_str}</div>'
                    )
                parts.append("  </div>")

            remaining = len(classes) - min(len(classes), _MAX_API_PER_MODULE)
            if remaining > 0:
                parts.append(
                    f'  <p class="api-doc"><em>+{remaining} more classes</em></p>'
                )
            parts.append("</div>")

        omitted = len(api_info) - total_shown
        if omitted > 0:
            parts.append(
                f'<p style="color:var(--text-muted);font-size:0.75rem;">'
                f"Showing {total_shown} of {len(api_info)} public classes. "
                f"{omitted} additional classes omitted for brevity.</p>"
            )

        parts.append("</section>")
        return "\n".join(parts)

    def _render_tech_stack(self, metadata: ProjectMetadata) -> str:
        """Render the technology stack section."""
        if not metadata.dependencies and not metadata.dev_dependencies:
            return ""

        parts: list[str] = []
        parts.append('<section class="section" id="tech-stack">')
        parts.append('<h2 class="section-title">Technology Stack</h2>')
        parts.append(
            "<p>The technology stack represents the foundation upon which this project is "
            "built. Each dependency has been selected to address specific technical "
            "requirements, from core framework capabilities to development tooling. "
            "Understanding these dependencies helps developers set up their environment "
            "and appreciate the design choices made.</p>"
        )

        if metadata.dependencies:
            parts.append('<div class="dep-group">')
            parts.append("  <h4>Runtime Dependencies</h4>")
            parts.append('  <div class="dep-tags">')
            for dep in sorted(metadata.dependencies):
                # Strip version specifiers for display
                match = _DEP_NAME_RE.match(dep)
                dep_name = match.group(0) if match else dep.strip()
                if dep_name:
                    parts.append(f'    <span class="dep-tag">{html.escape(dep_name)}</span>')
            parts.append("  </div>")
            parts.append("</div>")

        if metadata.dev_dependencies:
            parts.append('<div class="dep-group">')
            parts.append("  <h4>Development Dependencies</h4>")
            parts.append('  <div class="dep-tags">')
            for dep in sorted(set(metadata.dev_dependencies)):
                match = _DEP_NAME_RE.match(dep)
                dep_name = match.group(0) if match else dep.strip()
                if dep_name:
                    parts.append(
                        f'    <span class="dep-tag dep-dev">{html.escape(dep_name)}</span>'
                    )
            parts.append("  </div>")
            parts.append("</div>")

        parts.append("</section>")
        return "\n".join(parts)

    def _render_data_flow(self, packages: list[dict[str, Any]]) -> str:
        """Render a data flow / pipeline diagram showing how components interact."""
        if len(packages) < _MIN_LAYERS_FOR_FLOW:
            return ""

        parts: list[str] = []
        parts.append('<section class="section" id="data-flow">')
        parts.append('<h2 class="section-title">Data Flow Pipeline</h2>')
        parts.append(
            "<p>This diagram illustrates how data and control flow through the "
            "system at runtime. Each stage represents a layer in the processing "
            "pipeline, showing how input is transformed as it passes through "
            "successive components toward the final output.</p>"
        )

        svg = self._build_flow_pipeline_svg(packages)
        parts.append(f'<div class="diagram-container">{svg}</div>')
        parts.append("</section>")
        return "\n".join(parts)

    def _render_health_insights(
        self,
        metadata: ProjectMetadata,
        module_map: ModuleMap | None,
        dep_graph: ImportGraph | None,
        api_info: list[dict[str, Any]],
        packages: list[dict[str, Any]],
    ) -> str:
        """Render architecture health indicators for technical leadership."""
        parts: list[str] = []
        parts.append('<section class="section" id="health-insights">')
        parts.append('<h2 class="section-title">Architecture Health</h2>')
        parts.append(
            "<p>Key indicators for technical leadership assessing system "
            "maturity, maintainability risk, and architectural fitness.</p>"
        )

        # Compute metrics (use filtered package data, not raw module_map totals)
        pkg_count = len(packages)
        mod_count = sum(int(p.get("module_count", 0)) for p in packages)
        cls_count = len(api_info)
        dep_count = len(metadata.dependencies) if metadata.dependencies else 0
        avg_mod = round(mod_count / pkg_count, 1) if pkg_count else 0

        # Large packages (complexity risk)
        large_pkgs = [
            p for p in packages
            if int(p.get("module_count", 0)) > _LARGE_PACKAGE_THRESHOLD
        ]
        # Top function-heavy packages
        top_func = sorted(
            packages, key=lambda p: int(p.get("function_count", 0)),
            reverse=True,
        )[:5]

        # Health cards
        parts.append('<div class="stats-grid">')

        # Modularity score
        modularity = "High" if pkg_count >= _MODULARITY_HIGH else (
            "Medium" if pkg_count >= _MODULARITY_MED else "Low"
        )
        mod_color = (
            "var(--accent-primary)" if modularity == "High"
            else "var(--accent-secondary)"
        )
        parts.append(f"""
<div class="stat-card">
  <div class="stat-number" style="color:{mod_color}">{modularity}</div>
  <div class="stat-label">Modularity</div>
</div>""")

        parts.append(f"""
<div class="stat-card">
  <div class="stat-number">{avg_mod}</div>
  <div class="stat-label">Avg Modules/Package</div>
</div>""")

        coupling = "Low" if dep_count < _COUPLING_LOW else (
            "Medium" if dep_count < _COUPLING_HIGH else "High"
        )
        coup_color = (
            "var(--accent-primary)" if coupling == "Low"
            else "#ef4444" if coupling == "High"
            else "var(--accent-secondary)"
        )
        parts.append(f"""
<div class="stat-card">
  <div class="stat-number" style="color:{coup_color}">{coupling}</div>
  <div class="stat-label">External Coupling</div>
</div>""")

        api_density = round(cls_count / mod_count * 100, 1) if mod_count else 0
        parts.append(f"""
<div class="stat-card">
  <div class="stat-number">{api_density}%</div>
  <div class="stat-label">API Density</div>
</div>""")

        parts.append("</div>")

        # Risk areas
        if large_pkgs:
            parts.append('<div class="purpose-block">')
            parts.append(
                '<h3>Complexity Hotspots</h3>'
                "<p class=\"purpose-text\">The following packages have more "
                "than 15 modules, suggesting potential candidates for "
                "decomposition or boundary refinement:</p>"
            )
            parts.append('<div class="dep-tags" style="margin-top:12px">')
            for pkg in large_pkgs:
                name = html.escape(str(pkg["name"]))
                mc = pkg.get("module_count", 0)
                parts.append(
                    f'<span class="dep-tag">{name} ({mc} modules)</span>'
                )
            parts.append("</div></div>")

        # Top contributors by function count
        if top_func:
            parts.append('<div class="purpose-block">')
            parts.append(
                '<h3>Highest Functionality Concentration</h3>'
                "<p class=\"purpose-text\">"
                "Packages with the most functions represent the core "
                "business logic. These are the most critical to test "
                "thoroughly and document carefully:</p>"
            )
            parts.append('<div class="dep-tags" style="margin-top:12px">')
            for pkg in top_func:
                name = html.escape(str(pkg["name"]))
                fc = pkg.get("function_count", 0)
                if fc > 0:
                    parts.append(
                        f'<span class="dep-tag">{name} ({fc} fn)</span>'
                    )
            parts.append("</div></div>")

        # Recommendations
        parts.append('<div class="purpose-block">')
        parts.append('<h3>Recommendations</h3>')
        recs: list[str] = []
        if large_pkgs:
            recs.append(
                "Consider breaking down large packages into smaller, "
                "more focused modules to reduce cognitive load."
            )
        if dep_count > _LARGE_PACKAGE_THRESHOLD:
            recs.append(
                "High external dependency count increases supply chain "
                "risk. Audit dependencies for overlap and necessity."
            )
        if not metadata.license:
            recs.append(
                "No license detected. Add a license to clarify usage rights."
            )
        if not recs:
            recs.append(
                "Architecture appears well-structured. Continue monitoring "
                "package boundaries as the codebase evolves."
            )
        for rec in recs:
            parts.append(f"<p class=\"purpose-text\">{html.escape(rec)}</p>")
        parts.append("</div>")

        parts.append("</section>")
        return "\n".join(parts)

    def _render_footer(
        self,
        pkg_count: int = 0,
        mod_count: int = 0,
        cls_count: int = 0,
    ) -> str:
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        return f"""
<footer class="footer">
  <p>Generated by <strong>DocsMCP</strong> &mdash; Architecture Report</p>
  <p style="margin-top:6px">
    {pkg_count} packages &middot; {mod_count} modules &middot;
    {cls_count} public classes &middot; {html.escape(now)}
  </p>
</footer>"""

    # ------------------------------------------------------------------
    # Package collection helpers
    # ------------------------------------------------------------------

    def _collect_packages(self, module_map: ModuleMap | None) -> list[dict[str, Any]]:
        """Extract top-level package info, filtering out noise."""
        if module_map is None:
            return []

        skip_all = SKIP_DIRS | _ARCH_SKIP_DIRS
        packages: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for node in module_map.module_tree:
            # Skip noise directories
            if node.name in skip_all or node.name.startswith("."):
                continue
            if any(node.name.startswith(p) for p in _NOISE_PATTERNS):
                continue
            # Skip single-file scripts (not packages, no submodules)
            if not node.is_package and len(node.submodules) == 0:
                continue
            # Deduplicate by name (module map may list same name from
            # different paths, e.g. tests/ appearing 3 times)
            if node.name in seen_names:
                continue
            seen_names.add(node.name)
            pkg = self._node_to_package_info(node)
            packages.append(pkg)
            if len(packages) >= _MAX_COMPONENTS:
                break

        return packages

    def _node_to_package_info(self, node: ModuleNode) -> dict[str, Any]:
        """Convert a ModuleNode to a package info dict."""
        submodule_names: list[str] = []
        total_functions = node.function_count
        total_classes = node.class_count
        mod_count = 0

        for sub in node.submodules:
            submodule_names.append(sub.name)
            total_functions += sub.function_count
            total_classes += sub.class_count
            mod_count += 1
            # One level deeper
            for subsub in sub.submodules:
                total_functions += subsub.function_count
                total_classes += subsub.class_count
                mod_count += 1

        return {
            "name": node.name,
            "path": node.path,
            "is_package": node.is_package,
            "docstring": node.module_docstring or "",
            "module_count": mod_count or 1,
            "function_count": total_functions,
            "class_count": total_classes,
            "submodules": submodule_names,
        }

    def _collect_edges(
        self,
        dep_graph: ImportGraph | None,
        packages: list[dict[str, Any]],
    ) -> list[tuple[int, int]]:
        """Map dependency graph edges to package-level index pairs."""
        if dep_graph is None or not packages:
            return []

        pkg_names = [str(p["name"]) for p in packages]
        pkg_lookup: dict[str, int] = {name: i for i, name in enumerate(pkg_names)}

        seen: set[tuple[int, int]] = set()
        edges: list[tuple[int, int]] = []

        for edge in dep_graph.edges:
            src_pkg = self._path_to_package(edge.source, pkg_names)
            tgt_pkg = self._path_to_package(edge.target, pkg_names)
            if src_pkg is None or tgt_pkg is None:
                continue
            src_idx = pkg_lookup.get(src_pkg)
            tgt_idx = pkg_lookup.get(tgt_pkg)
            if src_idx is None or tgt_idx is None or src_idx == tgt_idx:
                continue
            pair = (src_idx, tgt_idx)
            if pair not in seen:
                seen.add(pair)
                edges.append(pair)
                if len(edges) >= _MAX_DEPENDENCY_EDGES:
                    break

        return edges

    @staticmethod
    def _path_to_package(rel_path: str, pkg_names: list[str]) -> str | None:
        """Extract the top-level package name from a relative path."""
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if part in pkg_names:
                return part
        # Try matching first significant directory
        for part in parts:
            if part and not part.startswith("_") and part != "src":
                for name in pkg_names:
                    if part == name or part.replace("_", "-") == name:
                        return name
        return None

    # ------------------------------------------------------------------
    # SVG diagram builders
    # ------------------------------------------------------------------

    def _build_architecture_svg(
        self,
        name: str,
        packages: list[dict[str, Any]],
    ) -> str:
        """Build the high-level architecture SVG with styled boxes."""
        count = len(packages)
        if count == 0:
            return ""

        # Layout: arrange packages in a grid
        cols = min(count, 4)
        rows = math.ceil(count / cols)

        box_w = 220
        box_h = 100
        gap_x = 40
        gap_y = 40
        pad = 60
        title_h = 70

        svg_w = cols * box_w + (cols - 1) * gap_x + 2 * pad
        svg_h = title_h + rows * box_h + (rows - 1) * gap_y + 2 * pad

        lines: list[str] = []
        lines.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" '
            f'class="arch-svg">'
        )

        # Defs: gradients, shadows, filters
        lines.append("  <defs>")
        lines.append(
            '    <filter id="shadow" x="-10%" y="-10%" width="130%" height="130%">'
        )
        lines.append(
            '      <feDropShadow dx="2" dy="4" stdDeviation="6" flood-opacity="0.15"/>'
        )
        lines.append("    </filter>")
        lines.append(
            '    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">'
        )
        lines.append(
            '      <feGaussianBlur stdDeviation="4" result="coloredBlur"/>'
        )
        lines.append("      <feMerge>")
        lines.append('        <feMergeNode in="coloredBlur"/>')
        lines.append('        <feMergeNode in="SourceGraphic"/>')
        lines.append("      </feMerge>")
        lines.append("    </filter>")

        for i, _pkg in enumerate(packages):
            g_start, g_end, _ = _PALETTE[i % len(_PALETTE)]
            lines.append(
                f'    <linearGradient id="grad{i}" x1="0%" y1="0%" x2="100%" y2="100%">'
            )
            lines.append(f'      <stop offset="0%" stop-color="{g_start}"/>')
            lines.append(f'      <stop offset="100%" stop-color="{g_end}"/>')
            lines.append("    </linearGradient>")

        lines.append("  </defs>")

        # Background
        lines.append(
            f'  <rect width="{svg_w}" height="{svg_h}" rx="16" '
            f'fill="#0a0a0f" />'
        )

        # Title
        lines.append(
            f'  <text x="{svg_w / 2}" y="45" text-anchor="middle" '
            f'fill="#fafafa" font-size="22" font-weight="700" '
            f'font-family="Outfit, Inter, system-ui, sans-serif">'
            f"{name} — Architecture Overview</text>"
        )

        # Package boxes
        for i, pkg in enumerate(packages):
            col = i % cols
            row = i // cols
            x = pad + col * (box_w + gap_x)
            y = title_h + pad + row * (box_h + gap_y)
            _, _, text_color = _PALETTE[i % len(_PALETTE)]
            pkg_name = html.escape(str(pkg["name"]))
            mod_count = pkg.get("module_count", 0)

            lines.append(
                f'  <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" '
                f'rx="12" fill="url(#grad{i})" filter="url(#shadow)" />'
            )
            lines.append(
                f'  <text x="{x + box_w / 2}" y="{y + 40}" text-anchor="middle" '
                f'fill="{text_color}" font-size="16" font-weight="700" '
                f'font-family="Outfit, Inter, system-ui, sans-serif">{pkg_name}</text>'
            )
            lines.append(
                f'  <text x="{x + box_w / 2}" y="{y + 65}" text-anchor="middle" '
                f'fill="{text_color}" font-size="11" opacity="0.8" '
                f'font-family="Outfit, Inter, system-ui, sans-serif">{mod_count} modules</text>'
            )

        lines.append("</svg>")
        return "\n".join(lines)

    def _build_flow_pipeline_svg(
        self,
        packages: list[dict[str, Any]],
    ) -> str:
        """Build a horizontal pipeline flow SVG showing data passing through layers."""
        # Group packages into logical layers by heuristic
        layers = self._group_into_layers(packages)
        if len(layers) < _MIN_LAYERS_FOR_FLOW:
            return ""

        layer_w = 160
        layer_h_per_item = 36
        gap_x = 80
        pad = 40
        title_h = 50
        arrow_len = gap_x - 10

        max_items = max(len(items) for items in layers.values())
        layer_count = len(layers)

        svg_w = pad * 2 + layer_count * layer_w + (layer_count - 1) * gap_x
        svg_h = title_h + pad * 2 + max_items * layer_h_per_item + 40

        lines: list[str] = []
        lines.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {svg_w} {svg_h}" class="flow-svg">'
        )

        # Defs
        lines.append("  <defs>")
        lines.append(
            '    <marker id="flowArrow" markerWidth="8" markerHeight="6" '
            'refX="7" refY="3" orient="auto">'
        )
        lines.append(
            '      <polygon points="0 0, 8 3, 0 6" fill="#14b8a6"/>'
        )
        lines.append("    </marker>")
        lines.append("  </defs>")

        # Background
        lines.append(
            f'  <rect width="{svg_w}" height="{svg_h}" '
            f'rx="8" fill="#0a0a0f"/>'
        )

        # Title
        font = "Outfit, Inter, system-ui, sans-serif"
        lines.append(
            f'  <text x="{svg_w / 2}" y="35" text-anchor="middle" '
            f'fill="#fafafa" font-size="18" font-weight="700" '
            f'font-family="{font}">Data Flow Pipeline</text>'
        )

        layer_names = list(layers.keys())
        layer_centers: list[float] = []

        for li, layer_name in enumerate(layer_names):
            items = layers[layer_name]
            x = pad + li * (layer_w + gap_x)
            y_start = title_h + pad
            layer_center_y = y_start + len(items) * layer_h_per_item / 2
            layer_centers.append(layer_center_y)

            # Layer label
            col_start, _, _ = _PALETTE[li % len(_PALETTE)]
            lines.append(
                f'  <text x="{x + layer_w / 2}" y="{y_start - 8}" '
                f'text-anchor="middle" fill="{col_start}" '
                f'font-size="13" font-weight="700" '
                f'font-family="{font}">{html.escape(layer_name)}</text>'
            )

            # Layer box background
            box_h = len(items) * layer_h_per_item + 16
            lines.append(
                f'  <rect x="{x}" y="{y_start}" width="{layer_w}" '
                f'height="{box_h}" rx="6" '
                f'fill="rgba(18,18,26,0.85)" '
                f'stroke="{col_start}" stroke-width="1" opacity="0.8"/>'
            )

            # Items
            for ii, item in enumerate(items):
                iy = y_start + 12 + ii * layer_h_per_item
                safe_item = html.escape(item)
                if len(safe_item) > _MAX_FLOW_ITEM_LEN:
                    safe_item = safe_item[:18] + ".."
                lines.append(
                    f'  <text x="{x + layer_w / 2}" y="{iy + 14}" '
                    f'text-anchor="middle" fill="#d4d4d8" '
                    f'font-size="11" font-weight="500" '
                    f'font-family="{font}">{safe_item}</text>'
                )

            # Arrow to next layer
            if li < layer_count - 1:
                ax = x + layer_w + 5
                ay = layer_center_y
                lines.append(
                    f'  <line x1="{ax}" y1="{ay}" '
                    f'x2="{ax + arrow_len}" y2="{ay}" '
                    f'stroke="#14b8a6" stroke-width="2" '
                    f'marker-end="url(#flowArrow)" opacity="0.7"/>'
                )

        lines.append("</svg>")
        return "\n".join(lines)

    @staticmethod
    def _group_into_layers(
        packages: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Heuristically group packages into pipeline layers."""
        layers: dict[str, list[str]] = {
            "Input / Config": [],
            "Core Logic": [],
            "Processing": [],
            "Output / API": [],
        }

        for pkg in packages:
            name = str(pkg["name"]).lower()
            if any(k in name for k in ("config", "setting", "common", "util")):
                layers["Input / Config"].append(str(pkg["name"]))
            elif any(k in name for k in (
                "server", "cli", "api", "pipeline", "distribution",
            )):
                layers["Output / API"].append(str(pkg["name"]))
            elif any(k in name for k in (
                "scor", "gate", "valid", "check", "analyz", "extract",
            )):
                layers["Processing"].append(str(pkg["name"]))
            else:
                layers["Core Logic"].append(str(pkg["name"]))

        # Remove empty layers
        return {k: v for k, v in layers.items() if v}

    def _build_dependency_svg(
        self,
        packages: list[dict[str, Any]],
        edges: list[tuple[int, int]],
    ) -> str:
        """Build a dependency flow SVG with curved arrows."""
        count = len(packages)
        if count == 0:
            return ""

        # Layout: circular for <=10, grid for more
        if count <= _CIRCULAR_LAYOUT_THRESHOLD:
            return self._build_circular_dep_svg(packages, edges)
        return self._build_grid_dep_svg(packages, edges)

    def _build_circular_dep_svg(
        self,
        packages: list[dict[str, Any]],
        edges: list[tuple[int, int]],
    ) -> str:
        """Render dependencies in a circular layout."""
        count = len(packages)
        cx, cy = 400, 350
        radius = 250
        node_r = 50
        svg_w, svg_h = 800, 700

        lines: list[str] = []
        lines.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" '
            f'class="dep-svg">'
        )

        # Defs
        lines.append("  <defs>")
        lines.append(
            '    <filter id="dshadow" x="-15%" y="-15%" width="130%" height="130%">'
        )
        lines.append(
            '      <feDropShadow dx="1" dy="3" stdDeviation="4" flood-opacity="0.2"/>'
        )
        lines.append("    </filter>")
        lines.append('    <marker id="arrowhead" markerWidth="10" markerHeight="7" '
                      'refX="9" refY="3.5" orient="auto">')
        lines.append('      <polygon points="0 0, 10 3.5, 0 7" fill="#a1a1aa"/>')
        lines.append("    </marker>")

        for i in range(count):
            g_start, g_end, _ = _PALETTE[i % len(_PALETTE)]
            lines.append(
                f'    <linearGradient id="dgrad{i}" x1="0%" y1="0%" x2="100%" y2="100%">'
            )
            lines.append(f'      <stop offset="0%" stop-color="{g_start}"/>')
            lines.append(f'      <stop offset="100%" stop-color="{g_end}"/>')
            lines.append("    </linearGradient>")

        lines.append("  </defs>")

        # Background
        lines.append(
            f'  <rect width="{svg_w}" height="{svg_h}" rx="16" fill="#0a0a0f"/>'
        )

        # Title
        lines.append(
            f'  <text x="{cx}" y="35" text-anchor="middle" fill="#fafafa" '
            f'font-size="18" font-weight="700" '
            f'font-family="Outfit, Inter, system-ui, sans-serif">Dependency Flow</text>'
        )

        # Compute node positions
        positions: list[tuple[float, float]] = []
        for i in range(count):
            angle = 2 * math.pi * i / count - math.pi / 2
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            positions.append((px, py))

        # Draw edges (curved)
        for src_idx, tgt_idx in edges:
            if src_idx >= count or tgt_idx >= count:
                continue
            sx, sy = positions[src_idx]
            tx, ty = positions[tgt_idx]

            # Bezier control point toward center
            ctrl_x = cx + (sx + tx - 2 * cx) * 0.3
            ctrl_y = cy + (sy + ty - 2 * cy) * 0.3

            lines.append(
                f'  <path d="M {sx:.0f} {sy:.0f} Q {ctrl_x:.0f} {ctrl_y:.0f} {tx:.0f} {ty:.0f}" '
                f'fill="none" stroke="rgba(63,63,90,0.5)" stroke-width="2" '
                f'stroke-dasharray="6,4" marker-end="url(#arrowhead)" opacity="0.7"/>'
            )

        # Draw nodes
        for i, (px, py) in enumerate(positions):
            _, _, text_color = _PALETTE[i % len(_PALETTE)]
            pkg_name = html.escape(str(packages[i]["name"]))
            # Truncate long names
            if len(pkg_name) <= _MAX_NAME_LEN_CIRCULAR:
                display_name = pkg_name
            else:
                display_name = pkg_name[:12] + ".."

            lines.append(
                f'  <circle cx="{px:.0f}" cy="{py:.0f}" r="{node_r}" '
                f'fill="url(#dgrad{i})" filter="url(#dshadow)"/>'
            )
            lines.append(
                f'  <text x="{px:.0f}" y="{py + 5:.0f}" text-anchor="middle" '
                f'fill="{text_color}" font-size="12" font-weight="600" '
                f'font-family="Outfit, Inter, system-ui, sans-serif">{display_name}</text>'
            )

        lines.append("</svg>")
        return "\n".join(lines)

    def _build_grid_dep_svg(
        self,
        packages: list[dict[str, Any]],
        edges: list[tuple[int, int]],
    ) -> str:
        """Render dependencies in a grid layout for larger projects."""
        count = len(packages)
        cols = min(count, 5)
        rows = math.ceil(count / cols)

        box_w, box_h = 140, 60
        gap_x, gap_y = 50, 70
        pad = 60
        title_h = 50

        svg_w = cols * box_w + (cols - 1) * gap_x + 2 * pad
        svg_h = title_h + rows * box_h + (rows - 1) * gap_y + 2 * pad

        lines: list[str] = []
        lines.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" '
            f'class="dep-svg">'
        )

        lines.append("  <defs>")
        lines.append('    <marker id="garrow" markerWidth="8" markerHeight="6" '
                      'refX="7" refY="3" orient="auto">')
        lines.append('      <polygon points="0 0, 8 3, 0 6" fill="#a1a1aa"/>')
        lines.append("    </marker>")
        for i in range(count):
            g_start, g_end, _ = _PALETTE[i % len(_PALETTE)]
            lines.append(
                f'    <linearGradient id="gg{i}" x1="0%" y1="0%" x2="100%" y2="100%">'
            )
            lines.append(f'      <stop offset="0%" stop-color="{g_start}"/>')
            lines.append(f'      <stop offset="100%" stop-color="{g_end}"/>')
            lines.append("    </linearGradient>")
        lines.append("  </defs>")

        lines.append(f'  <rect width="{svg_w}" height="{svg_h}" rx="12" fill="#0a0a0f"/>')
        lines.append(
            f'  <text x="{svg_w / 2}" y="35" text-anchor="middle" fill="#fafafa" '
            f'font-size="18" font-weight="700" '
            f'font-family="Outfit, Inter, system-ui, sans-serif">Dependency Flow</text>'
        )

        # Compute positions
        positions: list[tuple[float, float]] = []
        for i in range(count):
            col = i % cols
            row = i // cols
            x = pad + col * (box_w + gap_x) + box_w / 2
            y = title_h + pad + row * (box_h + gap_y) + box_h / 2
            positions.append((x, y))

        # Edges
        for src_idx, tgt_idx in edges:
            if src_idx >= count or tgt_idx >= count:
                continue
            sx, sy = positions[src_idx]
            tx, ty = positions[tgt_idx]
            mid_x = (sx + tx) / 2
            mid_y = (sy + ty) / 2 - 20
            lines.append(
                f'  <path d="M {sx:.0f} {sy:.0f} Q {mid_x:.0f} {mid_y:.0f} {tx:.0f} {ty:.0f}" '
                f'fill="none" stroke="rgba(63,63,90,0.5)" stroke-width="1.5" '
                f'stroke-dasharray="5,3" marker-end="url(#garrow)" opacity="0.6"/>'
            )

        # Nodes
        for i in range(count):
            col = i % cols
            row = i // cols
            x = pad + col * (box_w + gap_x)
            y = title_h + pad + row * (box_h + gap_y)
            _, _, text_color = _PALETTE[i % len(_PALETTE)]
            pkg_name = html.escape(str(packages[i]["name"]))
            display = pkg_name if len(pkg_name) <= _MAX_NAME_LEN_GRID else pkg_name[:14] + ".."

            lines.append(
                f'  <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" '
                f'rx="10" fill="url(#gg{i})"/>'
            )
            font = "Outfit, Inter, system-ui, sans-serif"
            lines.append(
                f'  <text x="{x + box_w / 2}" y="{y + box_h / 2 + 5}" '
                f'text-anchor="middle" fill="{text_color}" font-size="13" '
                f'font-weight="600" font-family="{font}">'
                f"{display}</text>"
            )

        lines.append("</svg>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Content generation helpers
    # ------------------------------------------------------------------

    def _generate_component_value(
        self,
        name: str,
        docstring: str,
        mod_count: int,
        func_count: int,
        cls_count: int,
    ) -> str:
        """Generate descriptive text about a component's purpose and value."""
        parts: list[str] = []

        if docstring:
            # Use the first sentence of the docstring as the lead
            first_sentence = docstring.strip().split("\n")[0].rstrip(".")
            parts.append(f"The {name} package {first_sentence.lower()}.")
        else:
            parts.append(
                f"The {name} package provides a cohesive set of functionality "
                f"that serves as a building block within the larger system."
            )

        if mod_count > 1:
            parts.append(
                f"It is composed of {mod_count} modules that work together "
                f"to deliver its capabilities."
            )

        if func_count > 0 and cls_count > 0:
            parts.append(
                f"The package exposes {func_count} functions and "
                f"{cls_count} classes, offering both procedural and "
                f"object-oriented interfaces to its consumers."
            )
        elif func_count > 0:
            parts.append(
                f"With {func_count} functions, it provides a functional "
                f"interface designed for straightforward integration."
            )
        elif cls_count > 0:
            parts.append(
                f"Through its {cls_count} classes, it establishes "
                f"well-defined abstractions that encapsulate complex behavior."
            )

        parts.append(
            "This component adds value by encapsulating domain-specific logic "
            "behind clean interfaces, reducing coupling between other parts "
            "of the system and enabling independent evolution of its internals."
        )

        return " ".join(parts)

    # ------------------------------------------------------------------
    # HTML wrapper
    # ------------------------------------------------------------------

    def _wrap_html(self, title: str, body: str) -> str:
        """Wrap the body content in a complete HTML document with CSS."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - Architecture Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_GOOGLE_FONTS_URL}" rel="stylesheet">
<style>
{_CSS}
</style>
</head>
<body>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Embedded CSS
# ---------------------------------------------------------------------------

_CSS = """
/* HomeIQ Design System — Architecture Report */
:root {{
  --bg-primary: #0a0a0f;
  --bg-secondary: #12121a;
  --bg-tertiary: #1e1e2a;
  --card-bg: rgba(18, 18, 26, 0.95);
  --card-bg-alt: rgba(30, 30, 42, 0.95);
  --card-border: rgba(63, 63, 90, 0.5);
  --accent-primary: #14b8a6;
  --accent-secondary: #d4a847;
  --accent-glow: rgba(20, 184, 166, 0.12);
  --text-primary: #fafafa;
  --text-secondary: #d4d4d8;
  --text-tertiary: #a1a1aa;
  --text-muted: #71717a;
  --focus-ring: rgba(20, 184, 166, 0.5);
  --shadow-card: 0 4px 6px -1px rgba(0,0,0,0.3), 0 0 0 1px rgba(63,63,90,0.3);
  --shadow-hover: 0 4px 12px -2px rgba(0,0,0,0.25);
  --radius-md: 0.25rem;
  --radius-lg: 0.375rem;
  --radius-xl: 0.5rem;
  --motion-fast: 150ms;
  --motion-normal: 250ms;
  --ease-enter: cubic-bezier(0.4, 0, 0.2, 1);
  --font-display: 'Outfit', 'Inter', system-ui, sans-serif;
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', ui-monospace, monospace;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: var(--font-sans);
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.45;
  font-size: 0.875rem;
  font-feature-settings: 'kern' 1, 'liga' 1, 'calt' 1, 'cv11' 1;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}}

/* Scrollbar */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 4px; }}

/* Focus */
:focus-visible {{
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}}
:focus:not(:focus-visible) {{ outline: none; }}

/* Animations */
@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(10px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes fadeInScale {{
  from {{ opacity: 0; transform: scale(0.95); }}
  to {{ opacity: 1; transform: scale(1); }}
}}
@keyframes pulseGlow {{
  0%, 100% {{ box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.15); }}
  50% {{ box-shadow: 0 0 20px 4px rgba(20, 184, 166, 0.08); }}
}}

/* Hero */
.hero {{
  background: linear-gradient(135deg, #0a0a0f 0%, #12121a 30%, #1e1e2a 70%, #0d3d38 100%);
  padding: 80px 40px;
  text-align: center;
  position: relative;
  overflow: hidden;
}}
.hero::before {{
  content: '';
  position: absolute;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background: radial-gradient(circle at 30% 50%, rgba(20,184,166,0.1) 0%, transparent 50%),
              radial-gradient(circle at 70% 80%, rgba(212,168,71,0.06) 0%, transparent 50%);
  animation: pulseGlow 8s ease-in-out infinite;
}}
.hero-content {{ position: relative; z-index: 1; max-width: 800px; margin: 0 auto; }}
.hero-title {{
  font-family: var(--font-display);
  font-size: 2.25rem; font-weight: 700;
  letter-spacing: -0.025em; margin-bottom: 12px;
  color: var(--text-primary);
}}
.hero-subtitle {{
  font-size: 1rem; color: var(--text-secondary);
  margin-bottom: 16px; line-height: 1.6;
}}
.hero-meta {{
  font-size: 0.75rem; color: var(--accent-primary);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 600;
}}

/* Sections */
.section {{
  max-width: 1100px;
  margin: 0 auto;
  padding: 48px 40px;
  animation: fadeIn 0.4s var(--ease-enter) both;
}}
.section-title {{
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.025em;
  margin-bottom: 16px;
  color: var(--text-primary);
  position: relative;
  padding-bottom: 12px;
}}
.section-title::after {{
  content: '';
  position: absolute;
  bottom: 0; left: 0;
  width: 48px; height: 3px;
  background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
  border-radius: 2px;
}}
.section > p {{
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.6;
  margin-bottom: 24px;
  max-width: 900px;
}}

/* Purpose block */
.purpose-block {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-left: 3px solid var(--accent-primary);
  border-radius: var(--radius-lg);
  padding: 24px 28px;
  margin-bottom: 32px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
}}
.purpose-block h3 {{
  font-family: var(--font-display);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--accent-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 10px;
}}
.purpose-text {{
  font-size: 1rem;
  color: var(--text-secondary);
  line-height: 1.6;
}}

/* Stats grid */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}}
.stat-card {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  text-align: center;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  transition: transform var(--motion-fast) var(--ease-enter),
              box-shadow var(--motion-fast) var(--ease-enter);
  animation: fadeInScale 0.4s var(--ease-enter) both;
}}
.stat-card:nth-child(1) {{ animation-delay: 0.05s; }}
.stat-card:nth-child(2) {{ animation-delay: 0.1s; }}
.stat-card:nth-child(3) {{ animation-delay: 0.15s; }}
.stat-card:nth-child(4) {{ animation-delay: 0.2s; }}
.stat-card:nth-child(5) {{ animation-delay: 0.25s; }}
.stat-card:hover {{
  transform: translateY(-4px);
  box-shadow: var(--shadow-hover);
}}
.stat-number {{
  font-family: var(--font-mono);
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.015em;
}}
.stat-label {{
  font-size: 0.6875rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 500;
  margin-top: 4px;
}}

/* Meta badges */
.meta-details {{
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}}
.meta-badge {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-radius: var(--radius-md);
  padding: 4px 12px;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-tertiary);
}}

/* Diagram container */
.diagram-container {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  margin: 24px 0;
  overflow-x: auto;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
}}
.diagram-container svg {{
  width: 100%;
  height: auto;
  display: block;
}}

/* Component cards */
.component-card {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: 16px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  transition: transform var(--motion-fast) var(--ease-enter),
              box-shadow var(--motion-fast) var(--ease-enter);
  animation: fadeIn 0.4s var(--ease-enter) both;
}}
.component-card:hover {{
  transform: translateY(-4px);
  box-shadow: var(--shadow-hover);
}}
.component-header {{
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}}
.component-name {{
  font-family: var(--font-display);
  font-size: 1.125rem;
  font-weight: 700;
  color: white;
  margin: 0;
}}
.component-stats {{
  display: flex;
  gap: 12px;
  font-size: 0.6875rem;
  font-weight: 500;
  color: rgba(255,255,255,0.75);
  font-family: var(--font-mono);
}}
.component-body {{
  padding: 20px;
}}
.component-description {{
  color: var(--text-secondary);
  line-height: 1.6;
  font-size: 0.875rem;
}}
.submodule-list {{
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--card-border);
}}
.submodule-list h4 {{
  font-size: 0.6875rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
  margin-bottom: 8px;
}}
.submodule-list ul {{
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}}
.submodule-list li {{
  background: var(--bg-primary);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-md);
  padding: 3px 10px;
  font-size: 0.75rem;
}}
.submodule-list li code {{
  color: var(--accent-primary);
  font-family: var(--font-mono);
  font-size: 0.7em;
}}

/* API surface */
.api-module {{
  margin-bottom: 20px;
}}
.api-module-path {{
  font-size: 0.8125rem;
  color: var(--accent-primary);
  font-family: var(--font-mono);
  padding: 6px 0;
  border-bottom: 1px solid var(--card-border);
  margin-bottom: 10px;
}}
.api-class {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  margin-bottom: 8px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}
.api-class-header {{
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}}
.api-class-name {{
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--accent-primary);
  font-family: var(--font-mono);
}}
.api-bases {{
  font-size: 0.6875rem;
  color: var(--text-muted);
}}
.api-doc {{
  color: var(--text-secondary);
  font-size: 0.8125rem;
  margin-bottom: 6px;
}}
.api-methods {{
  font-size: 0.75rem;
  color: var(--text-muted);
}}
.api-methods code {{
  color: var(--accent-primary);
  font-family: var(--font-mono);
  font-size: 0.7em;
}}

/* Tech stack */
.dep-group {{
  margin-bottom: 20px;
}}
.dep-group h4 {{
  font-size: 0.6875rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
  margin-bottom: 10px;
}}
.dep-tags {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}}
.dep-tag {{
  background: linear-gradient(135deg, var(--card-bg), var(--card-bg-alt));
  border: 1px solid var(--card-border);
  border-radius: var(--radius-md);
  padding: 4px 12px;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-primary);
  transition: border-color var(--motion-fast) var(--ease-enter),
              transform var(--motion-fast) var(--ease-enter);
}}
.dep-tag:hover {{
  border-color: var(--accent-primary);
  transform: translateY(-2px);
}}
.dep-tag.dep-dev {{
  border-style: dashed;
  color: var(--text-tertiary);
}}

/* Footer */
.footer {{
  text-align: center;
  padding: 32px;
  color: var(--text-muted);
  font-size: 0.75rem;
  border-top: 1px solid var(--card-border);
  margin-top: 32px;
}}
.footer strong {{
  color: var(--accent-primary);
}}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }}
}}

/* High contrast */
@media (prefers-contrast: high) {{
  .component-card, .stat-card, .api-class {{ border: 2px solid currentColor; }}
}}

/* Print */
@media print {{
  body {{ background: white; color: black; }}
  .hero {{ background: #f0f0f0; color: black; }}
  .hero-title, .hero-subtitle, .hero-meta {{ color: black; }}
  .stat-number {{ color: black; -webkit-text-fill-color: black; }}
}}

/* Responsive */
@media (max-width: 768px) {{
  .hero {{ padding: 48px 20px; }}
  .hero-title {{ font-size: 1.5rem; }}
  .section {{ padding: 32px 20px; }}
  .component-header {{ flex-direction: column; gap: 6px; }}
  .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
"""
