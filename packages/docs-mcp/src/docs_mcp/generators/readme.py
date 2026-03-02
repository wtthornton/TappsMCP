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
            autoescape=False,  # noqa: S701 — Markdown output, not HTML
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
        context: dict[str, str] = {
            "name": metadata.name or project_root.name,
            "description": metadata.description or (
                f"A {metadata.name or project_root.name} project."
            ),
        }

        # Sections common to all styles
        context["installation"] = self._generate_installation(metadata)
        context["license"] = self._generate_license_section(metadata)

        # Standard and comprehensive add more sections
        if self._style in ("standard", "comprehensive"):
            context["badges"] = self._generate_badges(metadata)
            context["features"] = self._generate_features(project_root)
            context["usage"] = self._generate_usage(metadata)
            context["development"] = self._generate_development(metadata)

        # Comprehensive adds even more
        if self._style == "comprehensive":
            context["toc"] = self._generate_toc(context)
            context["architecture"] = self._generate_architecture(project_root)
            context["api_reference"] = self._generate_api_reference(project_root)
            context["contributing"] = self._generate_contributing()
            context["faq"] = ""  # Placeholder - user should fill in

        template = self._env.get_template(f"{self._style}.md.j2")
        return template.render(**context)

    def _generate_installation(self, metadata: ProjectMetadata) -> str:
        """Generate installation instructions based on detected package manager."""
        lines: list[str] = []

        source = metadata.source_file.lower()
        name = metadata.name

        if source == "pyproject.toml" or not source:
            lines.append("```bash")
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

    def _generate_badges(self, metadata: ProjectMetadata) -> str:
        """Generate shield.io badges for the project."""
        badges: list[str] = []

        if metadata.python_requires:
            version_text = metadata.python_requires.replace(">=", "").replace("<=", "")
            version_text = version_text.replace(">", "").replace("<", "").split(",")[0].strip()
            encoded = urllib.parse.quote(f">={version_text}", safe="")
            badges.append(
                f"![Python](https://img.shields.io/badge/python-{encoded}-blue)"
            )

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

        return "  ".join(badges)

    def _generate_features(self, project_root: Path) -> str:
        """Generate a features section based on project structure analysis."""
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
                features.append(
                    f"- {result.total_modules} modules with "
                    f"{result.public_api_count} public APIs"
                )
            if result.entry_points:
                features.append(
                    f"- CLI entry points: {', '.join(result.entry_points)}"
                )
        except Exception:
            logger.debug("features_analysis_failed")

        return "\n".join(features) if features else ""

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

    def _generate_development(self, metadata: ProjectMetadata) -> str:
        """Generate development setup instructions."""
        lines: list[str] = []
        source = metadata.source_file.lower()

        if source == "pyproject.toml" or not source:
            lines.append("```bash")
            lines.append("# Clone the repository")
            lines.append("git clone <repository-url>")
            lines.append(f"cd {metadata.name or 'project'}")
            lines.append("")
            lines.append("# Install dependencies")
            lines.append("pip install -e '.[dev]'")
            lines.append("")
            lines.append("# Run tests")
            lines.append("pytest")
            lines.append("```")
        elif source == "package.json":
            lines.append("```bash")
            lines.append("# Clone the repository")
            lines.append("git clone <repository-url>")
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
            lines.append("git clone <repository-url>")
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
