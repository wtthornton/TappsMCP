"""README generation with Jinja2 templates and section generators."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import ClassVar

import jinja2
import structlog
from pydantic import BaseModel

from docs_mcp.generators.metadata import MetadataExtractor, ProjectMetadata

logger = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates" / "readme"

_SCORE_THRESHOLD_HIGH = 80
_SCORE_THRESHOLD_MEDIUM = 60


class ReadmeSection(BaseModel):
    """A single section of a generated README."""

    name: str
    content: str
    source: str = "generated"


class ReadmeGenerator:
    """Generates README.md content from project metadata and analysis."""

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({"minimal", "standard", "comprehensive"})

    def __init__(self, style: str = "standard") -> None:
        if style not in self.VALID_STYLES:
            style = "standard"
        self._style = style
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=False,  # nosec B701 — Markdown output, not HTML
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @property
    def style(self) -> str:
        """Return the current generation style."""
        return self._style

    def generate(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Generate a complete README from project metadata and analysis.

        Args:
            project_root: Root directory of the project.
            metadata: Pre-extracted metadata. If None, extracts automatically.

        Returns:
            The rendered README content as a string.
        """
        project_root = project_root.resolve()

        if metadata is None:
            extractor = MetadataExtractor()
            metadata = extractor.extract(project_root)

        # Build template context
        project_name = metadata.name or project_root.name
        description = self._smart_description(
            metadata,
            project_root,
            project_name,
        )
        context: dict[str, str] = {
            "name": project_name,
            "description": description,
        }

        # Sections common to all styles
        context["installation"] = self._generate_installation(metadata, project_root)
        context["license"] = self._generate_license_section(metadata)

        # Standard and comprehensive add more sections
        if self._style in ("standard", "comprehensive"):
            context["badges"] = self._generate_badges(metadata)
            context["features"] = self._generate_features(project_root)
            context["usage"] = self._generate_usage(metadata)
            context["development"] = self._generate_development(metadata, project_root)

        # Comprehensive adds even more
        if self._style == "comprehensive":
            context["toc"] = self._generate_toc(context)
            context["architecture"] = self._generate_architecture(project_root)
            context["api_reference"] = self._generate_api_reference(project_root)
            context["contributing"] = self._generate_contributing()
            context["faq"] = ""  # Placeholder - user should fill in

        template = self._env.get_template(f"{self._style}.md.j2")
        return template.render(**context)

    @staticmethod
    def _smart_description(
        metadata: ProjectMetadata,
        project_root: Path,
        project_name: str,
    ) -> str:
        """Derive a project description using multiple fallback sources.

        Tries in order:
        1. ``metadata.description`` (from pyproject.toml/package.json)
        2. First paragraph of an existing README.md
        3. Package ``__init__.py`` docstring
        4. Generic fallback

        Args:
            metadata: Extracted project metadata.
            project_root: Root directory of the project.
            project_name: Display name for the project.

        Returns:
            A non-empty description string.
        """
        # 1. Metadata description (already extracted from config file)
        if metadata.description:
            return metadata.description

        # 2. First paragraph of existing README
        for readme_name in ("README.md", "README.rst", "README.txt", "README"):
            readme_path = project_root / readme_name
            if readme_path.exists():
                try:
                    text = readme_path.read_text(encoding="utf-8").strip()
                    # Skip title lines (# heading or === underline)
                    lines = text.split("\n")
                    para_lines: list[str] = []
                    past_title = False
                    for line in lines:
                        stripped = line.strip()
                        if not past_title:
                            if stripped.startswith("#") or stripped.startswith("="):
                                continue
                            if not stripped:
                                continue
                            past_title = True
                        if past_title:
                            if not stripped and para_lines:
                                break
                            if stripped:
                                para_lines.append(stripped)
                    if para_lines:
                        return " ".join(para_lines)
                except (OSError, ValueError) as exc:
                    logger.debug("readme_description_parse_failed", error=str(exc))

        # 3. Package __init__.py docstring
        for init_candidate in (
            project_root / "src" / project_name.replace("-", "_") / "__init__.py",
            project_root / project_name.replace("-", "_") / "__init__.py",
        ):
            if init_candidate.exists():
                try:
                    content = init_candidate.read_text(encoding="utf-8")
                    # Extract module docstring (triple-quoted first string)
                    for quote in ('"""', "'''"):
                        if quote in content:
                            start = content.index(quote) + 3
                            end = content.index(quote, start)
                            docstring = content[start:end].strip()
                            first_line = docstring.split("\n")[0].strip()
                            if first_line:
                                return first_line
                except (OSError, ValueError) as exc:
                    logger.debug("init_docstring_read_failed", error=str(exc))

        # 4. Generic fallback
        return f"A {project_name} project."

    def _generate_installation(
        self,
        metadata: ProjectMetadata,
        project_root: Path | None = None,
    ) -> str:
        """Generate installation instructions based on detected package manager."""
        lines: list[str] = []

        source = metadata.source_file.lower()
        name = metadata.name
        has_uv = (project_root is not None and (project_root / "uv.lock").exists()) or any(
            "uv" in d for d in metadata.dev_dependencies
        )

        if source == "pyproject.toml" or not source:
            lines.append("```bash")
            if has_uv:
                lines.append(f"uv sync  # or: pip install {name}")
            else:
                lines.append(f"pip install {name}")
            lines.append("```")
        elif source == "package.json":
            lines.append("```bash")
            lines.append(f"npm install {name}")
            lines.append("```")
        elif source == "cargo.toml":
            lines.append("```bash")
            lines.append(f"cargo add {name}")
            lines.append("```")

        return "\n".join(lines)

    def _generate_badges(
        self,
        metadata: ProjectMetadata,
        *,
        tapps_score: float | None = None,
    ) -> str:
        """Generate shield.io badges for the project.

        Args:
            metadata: Project metadata for version/license/python badges.
            tapps_score: Optional TappsMCP quality score (0-100) for badge.
        """
        badges: list[str] = []

        if metadata.python_requires:
            version_text = metadata.python_requires.replace(">=", "").replace("<=", "")
            version_text = version_text.replace(">", "").replace("<", "").split(",")[0].strip()
            encoded = urllib.parse.quote(f">={version_text}", safe="")
            badges.append(f"![Python](https://img.shields.io/badge/python-{encoded}-blue)")

        if metadata.license:
            encoded_license = urllib.parse.quote(metadata.license, safe="")
            badges.append(
                f"![License](https://img.shields.io/badge/license-{encoded_license}-green)"
            )

        if metadata.version:
            encoded_version = urllib.parse.quote(metadata.version, safe="")
            badges.append(
                f"![Version](https://img.shields.io/badge/version-{encoded_version}-blue)"
            )

        if tapps_score is not None:
            color = (
                "brightgreen"
                if tapps_score >= _SCORE_THRESHOLD_HIGH
                else "yellow"
                if tapps_score >= _SCORE_THRESHOLD_MEDIUM
                else "red"
            )
            badges.append(
                f"![Quality](https://img.shields.io/badge/quality-{tapps_score:.0f}%25-{color})"
            )

        return "  ".join(badges)

    def _generate_features(self, project_root: Path) -> str:
        """Generate a features section based on project structure analysis.

        Uses API surface analysis and import detection rather than
        simple directory existence checks.
        """
        features: list[str] = []

        # Detect features from project structure
        if (project_root / "pyproject.toml").exists():
            features.append("- Python project with modern packaging (pyproject.toml)")
        elif (project_root / "package.json").exists():
            features.append("- Node.js project")
        elif (project_root / "Cargo.toml").exists():
            features.append("- Rust project")

        if (project_root / "tests").is_dir() or (project_root / "test").is_dir():
            features.append("- Test suite included")

        if (project_root / ".github" / "workflows").is_dir():
            features.append("- CI/CD with GitHub Actions")

        if (project_root / "Dockerfile").exists() or (project_root / "docker-compose.yml").exists():
            features.append("- Docker support")

        if (project_root / "docs").is_dir():
            features.append("- Documentation included")

        # Try to get module info via the analyzer
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            result = analyzer.analyze(project_root, depth=2)
            if result.total_modules > 0:
                api_label = "public API" if result.public_api_count == 1 else "public APIs"
                features.append(
                    f"- {result.total_modules} modules with {result.public_api_count} {api_label}"
                )
            if result.entry_points:
                features.append(f"- CLI entry points: {', '.join(result.entry_points)}")
        except Exception:
            logger.debug("features_analysis_failed")

        # Detect framework usage from imports
        features.extend(self._detect_frameworks(project_root))

        return "\n".join(features) if features else ""

    @staticmethod
    def _detect_frameworks(project_root: Path) -> list[str]:
        """Detect framework usage by scanning imports in source files.

        Returns:
            List of feature bullet points for detected frameworks.
        """
        from docs_mcp.constants import SKIP_DIRS

        framework_markers: dict[str, str] = {
            "fastapi": "FastAPI web framework",
            "flask": "Flask web framework",
            "django": "Django web framework",
            "fastmcp": "FastMCP server framework",
            "click": "Click CLI framework",
            "typer": "Typer CLI framework",
            "pydantic": "Pydantic data validation",
            "sqlalchemy": "SQLAlchemy ORM",
            "pytest": "pytest testing framework",
        }

        detected: set[str] = set()
        try:
            # Scan a limited number of source files for imports
            count = 0
            for py_file in project_root.rglob("*.py"):
                # Skip excluded directories
                skip = False
                try:
                    rel = py_file.relative_to(project_root)
                    for part in rel.parts:
                        if part in SKIP_DIRS:
                            skip = True
                            break
                except ValueError:
                    skip = True
                if skip:
                    continue

                count += 1
                if count > 50:
                    break

                try:
                    content = py_file.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.debug("framework_file_read_failed", path=str(py_file), error=str(exc))
                    continue

                for module, _label in framework_markers.items():
                    if module not in detected and (
                        f"import {module}" in content or f"from {module}" in content
                    ):
                        detected.add(module)

        except OSError as exc:
            logger.warning("framework_detection_failed", error=str(exc))

        return [f"- {framework_markers[m]}" for m in sorted(detected)]

    def _generate_usage(self, metadata: ProjectMetadata) -> str:
        """Generate a basic usage section."""
        lines: list[str] = []

        if metadata.entry_points:
            for cmd, _module in metadata.entry_points.items():
                lines.append(f"### `{cmd}`")
                lines.append("")
                lines.append("```bash")
                lines.append(cmd)
                lines.append("```")
                lines.append("")
        elif metadata.name:
            source = metadata.source_file.lower()
            if source == "pyproject.toml" or not source:
                lines.append("```python")
                safe_name = metadata.name.replace("-", "_")
                lines.append(f"import {safe_name}")
                lines.append("```")
            elif source == "package.json":
                lines.append("```javascript")
                safe = metadata.name.replace("-", "_")
                lines.append(f'const {safe} = require("{metadata.name}");')
                lines.append("```")

        return "\n".join(lines)

    def _generate_development(
        self,
        metadata: ProjectMetadata,
        project_root: Path | None = None,
    ) -> str:
        """Generate development setup instructions."""
        lines: list[str] = []
        source = metadata.source_file.lower()

        # Detect git remote URL
        clone_url = "<repository-url>"
        if project_root is not None:
            import subprocess

            try:
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=project_root,
                )
                if result.returncode == 0 and result.stdout.strip():
                    clone_url = result.stdout.strip()
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug("git_remote_url_failed", error=str(exc))

        has_uv = (project_root is not None and (project_root / "uv.lock").exists()) or any(
            "uv" in d for d in metadata.dev_dependencies
        )

        if source == "pyproject.toml" or not source:
            lines.append("```bash")
            lines.append("# Clone the repository")
            lines.append(f"git clone {clone_url}")
            lines.append(f"cd {metadata.name or 'project'}")
            lines.append("")
            lines.append("# Install dependencies")
            if has_uv:
                lines.append("uv sync --all-packages")
            else:
                lines.append("pip install -e '.[dev]'")
            lines.append("")
            lines.append("# Run tests")
            if has_uv:
                lines.append("uv run pytest")
            else:
                lines.append("pytest")
            lines.append("```")
        elif source == "package.json":
            lines.append("```bash")
            lines.append("# Clone the repository")
            lines.append(f"git clone {clone_url}")
            lines.append(f"cd {metadata.name or 'project'}")
            lines.append("")
            lines.append("# Install dependencies")
            lines.append("npm install")
            lines.append("")
            lines.append("# Run tests")
            lines.append("npm test")
            lines.append("```")
        elif source == "cargo.toml":
            lines.append("```bash")
            lines.append("# Clone the repository")
            lines.append(f"git clone {clone_url}")
            lines.append(f"cd {metadata.name or 'project'}")
            lines.append("")
            lines.append("# Build")
            lines.append("cargo build")
            lines.append("")
            lines.append("# Run tests")
            lines.append("cargo test")
            lines.append("```")

        return "\n".join(lines)

    def _generate_license_section(self, metadata: ProjectMetadata) -> str:
        """Generate the license section text."""
        if metadata.license:
            return f"This project is licensed under the {metadata.license} license."
        return ""

    def _generate_toc(self, context: dict[str, str]) -> str:
        """Generate a table of contents from the context sections."""
        sections = [
            ("Features", "features"),
            ("Installation", "installation"),
            ("Usage", "usage"),
            ("Architecture", "architecture"),
            ("API Reference", "api_reference"),
            ("Development", "development"),
            ("Contributing", "contributing"),
            ("FAQ", "faq"),
            ("License", "license"),
        ]

        toc_lines: list[str] = []
        for display_name, key in sections:
            if context.get(key):
                anchor = display_name.lower().replace(" ", "-")
                toc_lines.append(f"- [{display_name}](#{anchor})")

        return "\n".join(toc_lines)

    def _generate_architecture(self, project_root: Path) -> str:
        """Generate an architecture overview based on project structure."""
        lines: list[str] = []

        pattern_block = self._generate_pattern_card(project_root)
        if pattern_block:
            lines.append(pattern_block)
            lines.append("")

        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            result = analyzer.analyze(project_root, depth=2)

            if result.module_tree:
                lines.append("### Project Structure")
                lines.append("")
                lines.append("```")
                for node in result.module_tree:
                    prefix = "+" if node.is_package else "-"
                    doc = f"  # {node.module_docstring}" if node.module_docstring else ""
                    suffix = "/" if node.is_package else ""
                    lines.append(f"{prefix} {node.name}{suffix}{doc}")
                    for sub in node.submodules:
                        sub_prefix = "  +" if sub.is_package else "  -"
                        sub_doc = f"  # {sub.module_docstring}" if sub.module_docstring else ""
                        lines.append(f"{sub_prefix} {sub.name}{sub_doc}")
                lines.append("```")
        except Exception:
            logger.debug("architecture_analysis_failed")

        return "\n".join(lines)

    def _generate_pattern_card(self, project_root: Path) -> str:
        """Render the architectural pattern_card as a Mermaid block.

        Returns an empty string if classification or rendering fails, so
        README generation degrades silently rather than breaking.
        """
        try:
            from docs_mcp.generators.diagrams import DiagramGenerator

            result = DiagramGenerator().generate(project_root, diagram_type="pattern_card")
            if not result.content or result.degraded:
                return ""
            return f"### Architectural Pattern\n\n```mermaid\n{result.content.rstrip()}\n```"
        except Exception:
            logger.debug("readme_pattern_card_failed")
            return ""

    def _generate_api_reference(self, project_root: Path) -> str:
        """Generate a placeholder API reference section."""
        return "See the [API documentation](docs/api.md) for detailed reference."

    def _generate_contributing(self) -> str:
        """Generate a basic contributing section."""
        lines = [
            "Contributions are welcome! Please follow these steps:",
            "",
            "1. Fork the repository",
            "2. Create a feature branch (`git checkout -b feature/my-feature`)",
            "3. Commit your changes (`git commit -am 'Add my feature'`)",
            "4. Push to the branch (`git push origin feature/my-feature`)",
            "5. Open a Pull Request",
        ]
        return "\n".join(lines)
