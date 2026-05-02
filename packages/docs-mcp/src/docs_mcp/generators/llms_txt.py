"""llms.txt generator for machine-readable project documentation.

Generates llms.txt files following the emerging standard for AI-readable
project summaries. Supports compact (llms.txt) and detailed (llms-full.txt)
output modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import structlog
from pydantic import BaseModel

from docs_mcp.generators.metadata import MetadataExtractor, ProjectMetadata

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_MAX_KEY_FILES = 30
_MAX_ENTRY_POINTS = 20
_MAX_DEPENDENCIES = 40

# Path segments that indicate vendored / generated content. Files under any
# of these are never reported as project entry points (TAP-1277).
_VENDORED_PATH_SEGMENTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        ".env",
        "env",
        "site-packages",
        "node_modules",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
    }
)


def _is_vendored(path: Path, project_root: Path) -> bool:
    """Return True if *path* lives under a vendored / build / cache directory."""
    try:
        rel = path.relative_to(project_root)
    except ValueError:
        rel = path
    for part in rel.parts:
        if part in _VENDORED_PATH_SEGMENTS or part.startswith(".venv"):
            return True
    return False


class LlmsTxtSection(BaseModel):
    """A single section in the llms.txt output."""

    heading: str
    content: str


class LlmsTxtResult(BaseModel):
    """Result of llms.txt generation."""

    content: str
    mode: str  # "compact" or "full"
    section_count: int
    project_name: str


class LlmsTxtGenerator:
    """Generates llms.txt files from project analysis data.

    Synthesises metadata, module structure, entry points, and documentation
    inventory into a structured markdown document optimised for consumption
    by AI coding assistants.
    """

    VALID_MODES: ClassVar[frozenset[str]] = frozenset({"compact", "full"})

    def __init__(self, mode: str = "compact") -> None:
        if mode not in self.VALID_MODES:
            mode = "compact"
        self._mode = mode

    @property
    def mode(self) -> str:
        """Return the current generation mode."""
        return self._mode

    def generate(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
        module_map: object | None = None,
    ) -> LlmsTxtResult:
        """Generate llms.txt content from project analysis.

        Args:
            project_root: Root directory of the project.
            metadata: Pre-extracted metadata. If None, extracts automatically.
            module_map: Optional ModuleMap from module_map analyzer.

        Returns:
            LlmsTxtResult with the generated content.
        """
        project_root = project_root.resolve()

        if metadata is None:
            extractor = MetadataExtractor()
            metadata = extractor.extract_with_workspace(project_root)

        sections: list[LlmsTxtSection] = []

        # 1. Title block
        project_name = metadata.name or project_root.name
        sections.append(self._title_section(project_name, metadata))

        # 2. Tech stack
        sections.append(self._tech_stack_section(project_root, metadata))

        # 3. Entry points
        sections.append(self._entry_points_section(project_root, metadata))

        # 4. Key files
        sections.append(self._key_files_section(project_root))

        # 5. Documentation map
        sections.append(self._documentation_map_section(project_root))

        # 6. API summary (full mode only)
        if self._mode == "full":
            sections.append(self._api_summary_section(project_root, module_map))

        # 7. Project structure (full mode only)
        if self._mode == "full":
            sections.append(self._project_structure_section(project_root))

        # Filter out empty sections
        sections = [s for s in sections if s.content.strip()]

        content = self._render(sections)

        return LlmsTxtResult(
            content=content,
            mode=self._mode,
            section_count=len(sections),
            project_name=project_name,
        )

    def _title_section(
        self,
        project_name: str,
        metadata: ProjectMetadata,
    ) -> LlmsTxtSection:
        """Generate the title/overview section."""
        lines = [f"# {project_name}"]
        if metadata.description:
            lines.append("")
            lines.append(f"> {metadata.description}")
        if metadata.version:
            lines.append("")
            lines.append(f"- Version: {metadata.version}")
        if metadata.license:
            lines.append(f"- License: {metadata.license}")
        if metadata.homepage:
            lines.append(f"- Homepage: {metadata.homepage}")
        elif metadata.repository:
            lines.append(f"- Repository: {metadata.repository}")
        return LlmsTxtSection(heading="Title", content="\n".join(lines))

    def _tech_stack_section(
        self,
        project_root: Path,
        metadata: ProjectMetadata,
    ) -> LlmsTxtSection:
        """Detect and list the technology stack."""
        techs: list[str] = []

        # Language detection
        if metadata.python_requires:
            techs.append(f"Python {metadata.python_requires}")
        elif (project_root / "pyproject.toml").exists():
            techs.append("Python")
        if (project_root / "package.json").exists():
            techs.append("Node.js")
        if (project_root / "Cargo.toml").exists():
            techs.append("Rust")
        if (project_root / "go.mod").exists():
            techs.append("Go")

        # Framework detection from dependencies
        dep_str = " ".join(metadata.dependencies).lower()
        if "fastapi" in dep_str:
            techs.append("FastAPI")
        if "django" in dep_str:
            techs.append("Django")
        if "flask" in dep_str:
            techs.append("Flask")
        if "pydantic" in dep_str:
            techs.append("Pydantic")
        if "sqlalchemy" in dep_str:
            techs.append("SQLAlchemy")
        if "react" in dep_str:
            techs.append("React")

        # Build/tooling detection
        if (project_root / "uv.lock").exists():
            techs.append("uv (package manager)")
        elif (project_root / "poetry.lock").exists():
            techs.append("Poetry")
        if (project_root / "Dockerfile").exists():
            techs.append("Docker")
        if (project_root / ".github" / "workflows").is_dir():
            techs.append("GitHub Actions")

        if not techs:
            return LlmsTxtSection(heading="Tech Stack", content="")

        lines = ["## Tech Stack", ""]
        for tech in techs:
            lines.append(f"- {tech}")
        return LlmsTxtSection(heading="Tech Stack", content="\n".join(lines))

    def _entry_points_section(
        self,
        project_root: Path,
        metadata: ProjectMetadata,
    ) -> LlmsTxtSection:
        """List project entry points.

        Source priority:

        1. ``[project.scripts]`` entries from the root ``pyproject.toml``
           (already in ``metadata.entry_points``).
        2. ``[project.scripts]`` entries from each ``packages/*`` member of
           a uv workspace, so a monorepo surfaces every CLI it ships rather
           than only the root's.
        3. Package ``__main__.py`` and ``cli.py`` modules under
           ``packages/*/src/*``, which are the canonical Python entry-point
           shapes for workspace packages.
        4. Fallback to common script filenames at the project root.

        Vendored paths (``.venv``, ``site-packages``, ``node_modules``, etc.)
        are excluded so site-packages CLIs like ``markdown_it`` / ``mypy``
        never appear (TAP-1277).
        """
        entries: list[str] = []
        seen: set[str] = set()

        def _add(line: str) -> None:
            if line not in seen:
                seen.add(line)
                entries.append(line)

        # 1. Root pyproject [project.scripts]
        for name, target in metadata.entry_points.items():
            _add(f"- `{name}` -> `{target}`")

        # 2. Workspace-member [project.scripts]
        packages_dir = project_root / "packages"
        if packages_dir.is_dir():
            for pkg_dir in sorted(packages_dir.iterdir()):
                if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
                    continue
                pkg_pyproject = pkg_dir / "pyproject.toml"
                if not pkg_pyproject.is_file():
                    continue
                for name, target in _read_pyproject_scripts(pkg_pyproject).items():
                    _add(f"- `{name}` -> `{target}`")

        # 3. Workspace package modules (__main__.py, cli.py, server.py)
        if packages_dir.is_dir():
            for ep_name in ("__main__.py", "cli.py", "server.py"):
                for f in sorted(packages_dir.rglob(f"src/*/{ep_name}")):
                    if _is_vendored(f, project_root):
                        continue
                    rel = str(f.relative_to(project_root)).replace("\\", "/")
                    _add(f"- `{rel}`")

        # 4. Fallback: common script filenames at project root only
        for ep_file in ("main.py", "app.py", "cli.py", "manage.py", "__main__.py"):
            candidate = project_root / ep_file
            if candidate.is_file():
                _add(f"- `{ep_file}`")

        if not entries:
            return LlmsTxtSection(heading="Entry Points", content="")

        lines = ["## Entry Points", ""]
        lines.extend(entries[:_MAX_ENTRY_POINTS])
        return LlmsTxtSection(heading="Entry Points", content="\n".join(lines))

    def _key_files_section(self, project_root: Path) -> LlmsTxtSection:
        """List key project files that AI assistants should know about."""
        key_patterns = [
            "README.md",
            "CLAUDE.md",
            "AGENTS.md",
            "CONTRIBUTING.md",
            "CHANGELOG.md",
            "LICENSE",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            ".env.example",
            "setup.cfg",
            "setup.py",
        ]
        found: list[str] = []
        for pattern in key_patterns:
            path = project_root / pattern
            if path.exists():
                found.append(f"- `{pattern}`")

        # Also check for common config files
        config_globs = ["*.toml", "*.yaml", "*.yml"]
        for glob_pat in config_globs:
            for f in sorted(project_root.glob(glob_pat)):
                if f.is_file() and f.name not in key_patterns:
                    entry = f"- `{f.name}`"
                    if entry not in found:
                        found.append(entry)

        if not found:
            return LlmsTxtSection(heading="Key Files", content="")

        lines = ["## Key Files", ""]
        lines.extend(found[:_MAX_KEY_FILES])
        return LlmsTxtSection(heading="Key Files", content="\n".join(lines))

    def _documentation_map_section(self, project_root: Path) -> LlmsTxtSection:
        """Map existing documentation files."""
        doc_dirs = ["docs", "doc", "documentation"]
        doc_files: list[str] = []

        # Root-level docs
        for f in sorted(project_root.iterdir()):
            if f.is_file() and f.suffix.lower() in (".md", ".rst", ".txt"):
                if f.name.lower() not in ("license", "license.md", "license.txt"):
                    doc_files.append(f"- `{f.name}`")

        # Documentation directories
        for doc_dir_name in doc_dirs:
            doc_dir = project_root / doc_dir_name
            if doc_dir.is_dir():
                for f in sorted(doc_dir.rglob("*")):
                    if f.is_file() and f.suffix.lower() in (".md", ".rst"):
                        rel = str(f.relative_to(project_root)).replace("\\", "/")
                        doc_files.append(f"- `{rel}`")

        if not doc_files:
            return LlmsTxtSection(heading="Documentation Map", content="")

        lines = ["## Documentation Map", ""]
        lines.extend(doc_files[:_MAX_KEY_FILES])
        if len(doc_files) > _MAX_KEY_FILES:
            lines.append(f"- ... and {len(doc_files) - _MAX_KEY_FILES} more")
        return LlmsTxtSection(heading="Documentation Map", content="\n".join(lines))

    def _api_summary_section(
        self,
        project_root: Path,
        module_map: object | None,
    ) -> LlmsTxtSection:
        """Summarise the public API surface (full mode only)."""
        if module_map is None:
            return LlmsTxtSection(heading="API Summary", content="")

        # Duck-type access to ModuleMap fields
        lines = ["## API Summary", ""]
        try:
            total_modules = getattr(module_map, "total_modules", 0)
            total_packages = getattr(module_map, "total_packages", 0)
            public_api_count = getattr(module_map, "public_api_count", 0)
            lines.append(f"- Packages: {total_packages}")
            lines.append(f"- Modules: {total_modules}")
            lines.append(f"- Public API symbols: {public_api_count}")
        except Exception:
            logger.debug("llms_txt_api_summary_failed")
            return LlmsTxtSection(heading="API Summary", content="")

        return LlmsTxtSection(heading="API Summary", content="\n".join(lines))

    def _project_structure_section(self, project_root: Path) -> LlmsTxtSection:
        """Show top-level project structure (full mode only)."""
        skip = {
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "node_modules",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "build",
            ".eggs",
            "site-packages",
        }
        lines = ["## Project Structure", "", "```"]
        entries: list[str] = []
        for item in sorted(project_root.iterdir()):
            if item.name.startswith(".") and item.is_dir():
                continue
            if item.name in skip:
                continue
            suffix = "/" if item.is_dir() else ""
            entries.append(f"{item.name}{suffix}")
        lines.extend(entries[:30])
        if len(entries) > 30:
            lines.append(f"... and {len(entries) - 30} more")
        lines.append("```")
        return LlmsTxtSection(heading="Project Structure", content="\n".join(lines))

    def _render(self, sections: list[LlmsTxtSection]) -> str:
        """Render sections into final llms.txt content."""
        parts: list[str] = []
        for section in sections:
            parts.append(section.content)
        return "\n\n".join(parts) + "\n"


def _read_pyproject_scripts(path: Path) -> dict[str, str]:
    """Return ``[project.scripts]`` from a pyproject.toml, or ``{}`` on failure.

    Standalone helper so callers don't depend on MetadataExtractor's full
    parser when they only need the script entries.
    """
    import tomllib

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    project = data.get("project", {})
    if not isinstance(project, dict):
        return {}
    scripts = project.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}
    return {str(k): str(v) for k, v in scripts.items()}
