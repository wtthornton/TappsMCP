"""Onboarding and contributing guide generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from docs_mcp.generators.metadata import ProjectMetadata

logger = structlog.get_logger(__name__)


class OnboardingGuideGenerator:
    """Generates a getting-started / onboarding guide for a project.

    Detects project metadata (language, package manager, entry points)
    and produces a structured markdown guide with installation, structure,
    and usage sections.
    """

    def generate(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Generate an onboarding guide for the project.

        Args:
            project_root: Root directory of the project.
            metadata: Pre-extracted project metadata. If None, extracts
                automatically via MetadataExtractor.

        Returns:
            Rendered onboarding guide as a markdown string.
            Returns an empty string on unrecoverable errors.
        """
        try:
            return self._generate_impl(project_root, metadata=metadata)
        except Exception as exc:
            logger.debug("onboarding_guide_failed", reason=str(exc))
            return ""

    def _generate_impl(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Internal implementation for onboarding guide generation.

        Args:
            project_root: Root directory of the project.
            metadata: Pre-extracted project metadata or None.

        Returns:
            Rendered onboarding guide as a markdown string.
        """
        from docs_mcp.generators.metadata import MetadataExtractor

        project_root = project_root.resolve()

        if metadata is None:
            extractor = MetadataExtractor()
            metadata = extractor.extract(project_root)

        project_name = metadata.name or project_root.name
        source = metadata.source_file.lower()

        sections: list[str] = []

        # Title
        sections.append(f"# Getting Started with {project_name}")
        sections.append("")

        # Prerequisites
        sections.append("## Prerequisites")
        sections.append("")
        sections.extend(self._prerequisites(metadata, source))
        sections.append("")

        # Installation
        sections.append("## Installation")
        sections.append("")
        sections.extend(self._installation(metadata, source, project_name, project_root))
        sections.append("")

        # Project Structure
        structure = self._project_structure(project_root)
        if structure:
            sections.append("## Project Structure")
            sections.append("")
            sections.extend(structure)
            sections.append("")

        # Key Concepts (auto-generated from API surface)
        sections.append("## Key Concepts")
        sections.append("")
        key_concepts = self._key_concepts(project_root)
        if key_concepts:
            sections.extend(key_concepts)
        else:
            sections.append(
                "<!-- Add key concepts and domain terminology here -->"
            )
        sections.append("")

        # Running the Project
        sections.append("## Running the Project")
        sections.append("")
        sections.extend(self._running(metadata, source, project_name))
        sections.append("")

        # Running Tests
        sections.append("## Running Tests")
        sections.append("")
        sections.extend(
            self._testing(metadata, source, project_root)
        )
        sections.append("")

        # Next Steps
        sections.append("## Next Steps")
        sections.append("")
        sections.extend(self._next_steps(project_root))
        sections.append("")

        return "\n".join(sections)

    @staticmethod
    def _prerequisites(
        metadata: ProjectMetadata,
        source: str,
    ) -> list[str]:
        """Generate prerequisites section lines.

        Args:
            metadata: Extracted project metadata.
            source: Lowercase source file name.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = []

        if source == "pyproject.toml" or not source:
            version = metadata.python_requires or "3.8+"
            lines.append(f"- Python {version}")
            # Detect package manager from dependencies or common patterns
            if any("uv" in d for d in metadata.dev_dependencies):
                lines.append("- [uv](https://docs.astral.sh/uv/) (recommended)")
            else:
                lines.append("- pip (or your preferred Python package manager)")
        elif source == "package.json":
            lines.append("- Node.js (LTS recommended)")
            lines.append("- npm or yarn")
        elif source == "cargo.toml":
            lines.append("- Rust toolchain (install via [rustup](https://rustup.rs/))")
            lines.append("- Cargo (included with Rust)")

        if not lines:
            lines.append("- See project documentation for requirements")

        return lines

    @staticmethod
    def _installation(
        metadata: ProjectMetadata,
        source: str,
        project_name: str,
        project_root: Path | None = None,
    ) -> list[str]:
        """Generate installation section lines.

        Args:
            metadata: Extracted project metadata.
            source: Lowercase source file name.
            project_name: Display name for the project.
            project_root: Project root directory (for uv.lock detection).

        Returns:
            List of markdown lines.
        """
        has_uv = (
            project_root is not None and (project_root / "uv.lock").exists()
        ) or any("uv" in d for d in metadata.dev_dependencies)

        # Detect git remote URL
        clone_url = "<repository-url>"
        if project_root is not None:
            import subprocess

            try:
                result = subprocess.run(  # noqa: S603
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=project_root,
                )
                if result.returncode == 0 and result.stdout.strip():
                    clone_url = result.stdout.strip()
            except Exception:
                pass

        lines: list[str] = ["```bash"]

        if source == "pyproject.toml" or not source:
            if has_uv:
                lines.append(f"uv sync  # or: pip install {project_name}")
            else:
                lines.append(f"pip install {project_name}")
        elif source == "package.json":
            lines.append(f"npm install {project_name}")
        elif source == "cargo.toml":
            lines.append(f"cargo add {project_name}")

        lines.append("```")

        # Development install
        lines.append("")
        lines.append("For development:")
        lines.append("")
        lines.append("```bash")
        lines.append(f"git clone {clone_url}")
        lines.append(f"cd {project_name}")

        if source == "pyproject.toml" or not source:
            if has_uv:
                lines.append("uv sync --all-packages")
            else:
                lines.append("pip install -e '.[dev]'")
        elif source == "package.json":
            lines.append("npm install")
        elif source == "cargo.toml":
            lines.append("cargo build")

        lines.append("```")
        return lines

    @staticmethod
    def _project_structure(project_root: Path) -> list[str]:
        """Generate project structure section using ModuleMapAnalyzer.

        Args:
            project_root: Root directory of the project.

        Returns:
            List of markdown lines, or empty list if analysis fails.
        """
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            result = analyzer.analyze(project_root, depth=2)

            if not result.module_tree:
                return []

            lines: list[str] = ["```"]
            for node in result.module_tree:
                prefix = "+" if node.is_package else "-"
                # Truncate docstring to first line to avoid breaking tree layout
                first_line = (
                    node.module_docstring.split("\n")[0].strip()
                    if node.module_docstring
                    else ""
                )
                doc = f"  # {first_line}" if first_line else ""
                suffix = "/" if node.is_package else ""
                lines.append(f"{prefix} {node.name}{suffix}{doc}")
                for sub in node.submodules:
                    sub_prefix = "  +" if sub.is_package else "  -"
                    sub_first_line = (
                        sub.module_docstring.split("\n")[0].strip()
                        if sub.module_docstring
                        else ""
                    )
                    sub_doc = f"  # {sub_first_line}" if sub_first_line else ""
                    lines.append(f"{sub_prefix} {sub.name}{sub_doc}")
            lines.append("```")
            return lines
        except Exception:
            logger.debug("project_structure_analysis_failed")
            return []

    @staticmethod
    def _key_concepts(project_root: Path) -> list[str]:
        """Extract key concepts from primary classes and their docstrings.

        Scans the project's Python files for public classes and returns
        a bullet list of class names with their summary docstrings.

        Args:
            project_root: Root directory of the project.

        Returns:
            List of markdown lines, or empty list if analysis fails.
        """
        try:
            from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer
            from docs_mcp.constants import SKIP_DIRS

            analyzer = APISurfaceAnalyzer()
            all_classes: list[tuple[str, str]] = []

            count = 0
            for py_file in sorted(project_root.rglob("*.py")):
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
                if count > 30:
                    break

                try:
                    result = analyzer.analyze(py_file, project_root=project_root)
                    for cls in result.classes:
                        doc = cls.docstring_summary or ""
                        all_classes.append((cls.name, doc))
                except Exception:
                    continue

            if not all_classes:
                return []

            lines: list[str] = []
            for name, doc in all_classes[:10]:
                if doc:
                    lines.append(f"- **{name}** - {doc}")
                else:
                    lines.append(f"- **{name}**")

            return lines
        except Exception:
            logger.debug("key_concepts_extraction_failed")
            return []

    @staticmethod
    def _running(
        metadata: ProjectMetadata,
        source: str,
        project_name: str,
    ) -> list[str]:
        """Generate running-the-project section lines.

        Args:
            metadata: Extracted project metadata.
            source: Lowercase source file name.
            project_name: Display name for the project.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = []

        if metadata.entry_points:
            for cmd, _module in metadata.entry_points.items():
                lines.append(f"### `{cmd}`")
                lines.append("")
                lines.append("```bash")
                lines.append(cmd)
                lines.append("```")
                lines.append("")
        elif source == "pyproject.toml" or not source:
            safe_name = project_name.replace("-", "_")
            lines.append("```bash")
            lines.append(f"python -m {safe_name}")
            lines.append("```")
        elif source == "package.json":
            lines.append("```bash")
            lines.append("npm start")
            lines.append("```")
        elif source == "cargo.toml":
            lines.append("```bash")
            lines.append("cargo run")
            lines.append("```")

        return lines

    @staticmethod
    def _testing(
        metadata: ProjectMetadata,
        source: str,
        project_root: Path,
    ) -> list[str]:
        """Generate testing section lines.

        Args:
            metadata: Extracted project metadata.
            source: Lowercase source file name.
            project_root: Root directory of the project.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = ["```bash"]

        all_deps = " ".join(
            metadata.dependencies + metadata.dev_dependencies
        ).lower()

        if source == "pyproject.toml" or not source:
            if "pytest" in all_deps or (project_root / "tests").is_dir():
                lines.append("pytest")
            else:
                lines.append("python -m unittest discover")
        elif source == "package.json":
            if "jest" in all_deps:
                lines.append("npx jest")
            elif "vitest" in all_deps:
                lines.append("npx vitest")
            else:
                lines.append("npm test")
        elif source == "cargo.toml":
            lines.append("cargo test")

        lines.append("```")
        return lines

    @staticmethod
    def _next_steps(project_root: Path) -> list[str]:
        """Generate next-steps section with links to related docs.

        Args:
            project_root: Root directory of the project.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = []

        if (project_root / "CONTRIBUTING.md").exists():
            lines.append(
                "- Read the [Contributing Guide](CONTRIBUTING.md) "
                "to learn how to contribute"
            )

        if (project_root / "docs").is_dir():
            lines.append(
                "- Browse the [documentation](docs/) for detailed guides"
            )

        if (project_root / "docs" / "api.md").exists():
            lines.append(
                "- Check the [API Reference](docs/api.md) for detailed API docs"
            )

        if (project_root / "CHANGELOG.md").exists():
            lines.append(
                "- See the [Changelog](CHANGELOG.md) for recent changes"
            )

        if not lines:
            lines.append("- Explore the codebase and documentation")
            lines.append("- Open an issue if you find a bug or have a question")

        return lines


def _detect_tool_config(project_root: Path) -> set[str]:
    """Detect tools configured in pyproject.toml ``[tool.*]`` sections.

    Returns a set of tool names found (e.g. ``{"ruff", "mypy", "pytest"}``).
    """
    import tomllib

    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return set()

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        tool_section = data.get("tool", {})
        if isinstance(tool_section, dict):
            return set(tool_section.keys())
    except Exception:
        pass
    return set()


class ContributingGuideGenerator:
    """Generates a CONTRIBUTING.md guide for a project.

    Detects project metadata (language, package manager, linters)
    and produces a structured contributing guide with setup, standards,
    and workflow sections.
    """

    def generate(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Generate a contributing guide for the project.

        Args:
            project_root: Root directory of the project.
            metadata: Pre-extracted project metadata. If None, extracts
                automatically via MetadataExtractor.

        Returns:
            Rendered contributing guide as a markdown string.
            Returns an empty string on unrecoverable errors.
        """
        try:
            return self._generate_impl(project_root, metadata=metadata)
        except Exception as exc:
            logger.debug("contributing_guide_failed", reason=str(exc))
            return ""

    def _generate_impl(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Internal implementation for contributing guide generation.

        Args:
            project_root: Root directory of the project.
            metadata: Pre-extracted project metadata or None.

        Returns:
            Rendered contributing guide as a markdown string.
        """
        from docs_mcp.generators.metadata import MetadataExtractor

        project_root = project_root.resolve()

        if metadata is None:
            extractor = MetadataExtractor()
            metadata = extractor.extract(project_root)

        project_name = metadata.name or project_root.name
        source = metadata.source_file.lower()
        all_deps = " ".join(
            metadata.dependencies + metadata.dev_dependencies
        ).lower()

        sections: list[str] = []

        # Title
        sections.append(f"# Contributing to {project_name}")
        sections.append("")

        sections.append(
            f"Thank you for your interest in contributing to {project_name}! "
            "This guide will help you get started."
        )
        sections.append("")

        # Code of Conduct
        if (project_root / "CODE_OF_CONDUCT.md").exists():
            sections.append("## Code of Conduct")
            sections.append("")
            sections.append(
                "This project has a "
                "[Code of Conduct](CODE_OF_CONDUCT.md). "
                "By participating, you are expected to uphold it."
            )
            sections.append("")

        # Getting Started
        sections.append("## Getting Started")
        sections.append("")
        sections.append("1. Fork the repository on GitHub")
        sections.append("2. Clone your fork locally:")
        sections.append("")
        sections.append("```bash")
        repo_url = metadata.repository or "<your-fork-url>"
        sections.append(f"git clone {repo_url}")
        sections.append(f"cd {project_name}")
        sections.append("```")
        sections.append("")

        # Development Setup
        sections.append("## Development Setup")
        sections.append("")
        sections.extend(
            self._dev_setup(metadata, source, project_name)
        )
        sections.append("")

        # Coding Standards
        sections.append("## Coding Standards")
        sections.append("")
        sections.extend(
            self._coding_standards(all_deps, source, project_root)
        )
        sections.append("")

        # Testing
        sections.append("## Testing")
        sections.append("")
        sections.extend(
            self._testing_section(metadata, source, project_root, all_deps)
        )
        sections.append("")

        # Submitting Changes
        sections.append("## Submitting Changes")
        sections.append("")
        sections.extend(self._submit_workflow())
        sections.append("")

        # Reporting Issues
        sections.append("## Reporting Issues")
        sections.append("")
        sections.extend(self._issue_guidance(project_root))
        sections.append("")

        return "\n".join(sections)

    @staticmethod
    def _dev_setup(
        metadata: ProjectMetadata,
        source: str,
        project_name: str,
    ) -> list[str]:
        """Generate development setup section lines.

        Args:
            metadata: Extracted project metadata.
            source: Lowercase source file name.
            project_name: Display name for the project.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = ["```bash"]

        if source == "pyproject.toml" or not source:
            all_deps_str = " ".join(
                metadata.dependencies + metadata.dev_dependencies
            ).lower()
            if "uv" in all_deps_str:
                lines.append("# Install with uv")
                lines.append("uv sync --all-packages")
            else:
                lines.append("# Create a virtual environment")
                lines.append("python -m venv .venv")
                lines.append("source .venv/bin/activate  # or .venv\\Scripts\\activate on Windows")
                lines.append("")
                lines.append("# Install in development mode")
                lines.append("pip install -e '.[dev]'")
        elif source == "package.json":
            lines.append("# Install dependencies")
            lines.append("npm install")
        elif source == "cargo.toml":
            lines.append("# Build the project")
            lines.append("cargo build")

        lines.append("```")
        return lines

    @staticmethod
    def _coding_standards(
        all_deps: str,
        source: str,
        project_root: Path | None = None,
    ) -> list[str]:
        """Generate coding standards section lines.

        Detects linter/formatter config from dependencies and
        ``pyproject.toml`` tool sections.

        Args:
            all_deps: Lowercase concatenation of all dependency names.
            source: Lowercase source file name.
            project_root: Root directory for config file detection.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = []

        # Also check pyproject.toml [tool.*] sections for linter config
        tool_config: set[str] = set()
        if project_root is not None:
            tool_config = _detect_tool_config(project_root)

        if source == "pyproject.toml" or not source:
            if "ruff" in all_deps or "ruff" in tool_config:
                lines.append("This project uses [ruff](https://docs.astral.sh/ruff/) "
                             "for linting and formatting:")
                lines.append("")
                lines.append("```bash")
                lines.append("ruff check .")
                lines.append("ruff format --check .")
                lines.append("```")
            elif "black" in all_deps and "flake8" in all_deps:
                lines.append("This project uses black for formatting and flake8 for linting:")
                lines.append("")
                lines.append("```bash")
                lines.append("black --check .")
                lines.append("flake8 .")
                lines.append("```")
            elif "black" in all_deps:
                lines.append("This project uses [black](https://black.readthedocs.io/) "
                             "for code formatting:")
                lines.append("")
                lines.append("```bash")
                lines.append("black --check .")
                lines.append("```")
            else:
                lines.append("Please ensure your code follows the project's style conventions.")

            if "mypy" in all_deps or "mypy" in tool_config:
                lines.append("")
                lines.append("Type checking is enforced with mypy:")
                lines.append("")
                lines.append("```bash")
                lines.append("mypy .")
                lines.append("```")

        elif source == "package.json":
            if "eslint" in all_deps:
                lines.append("This project uses ESLint for linting:")
                lines.append("")
                lines.append("```bash")
                lines.append("npx eslint .")
                lines.append("```")
            if "prettier" in all_deps:
                lines.append("")
                lines.append("Formatting is enforced with Prettier:")
                lines.append("")
                lines.append("```bash")
                lines.append("npx prettier --check .")
                lines.append("```")
            if "eslint" not in all_deps and "prettier" not in all_deps:
                lines.append("Please ensure your code follows the project's style conventions.")

        elif source == "cargo.toml":
            lines.append("Please format your code with `cargo fmt` "
                         "and check for warnings with `cargo clippy`:")
            lines.append("")
            lines.append("```bash")
            lines.append("cargo fmt --check")
            lines.append("cargo clippy -- -D warnings")
            lines.append("```")

        if not lines:
            lines.append("Please ensure your code follows the project's style conventions.")

        return lines

    @staticmethod
    def _testing_section(
        metadata: ProjectMetadata,
        source: str,
        project_root: Path,
        all_deps: str,
    ) -> list[str]:
        """Generate testing section lines.

        Args:
            metadata: Extracted project metadata.
            source: Lowercase source file name.
            project_root: Root directory of the project.
            all_deps: Lowercase concatenation of all dependency names.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = [
            "Please ensure all tests pass before submitting a pull request.",
            "",
            "```bash",
        ]

        if source == "pyproject.toml" or not source:
            if "pytest" in all_deps or (project_root / "tests").is_dir():
                lines.append("pytest -v")
            else:
                lines.append("python -m unittest discover")
        elif source == "package.json":
            if "jest" in all_deps:
                lines.append("npx jest")
            elif "vitest" in all_deps:
                lines.append("npx vitest")
            else:
                lines.append("npm test")
        elif source == "cargo.toml":
            lines.append("cargo test")

        lines.append("```")
        lines.append("")
        lines.append("When adding new features, please include appropriate tests.")

        # Reference CI workflows if present
        if project_root is not None:
            ci_dir = project_root / ".github" / "workflows"
            if ci_dir.is_dir():
                try:
                    workflows = sorted(ci_dir.glob("*.yml")) + sorted(
                        ci_dir.glob("*.yaml")
                    )
                    if workflows:
                        names = [w.stem for w in workflows[:3]]
                        lines.append("")
                        lines.append(
                            "CI runs automatically on pull requests "
                            f"(workflows: {', '.join(names)})."
                        )
                except Exception:
                    pass

        return lines

    @staticmethod
    def _submit_workflow() -> list[str]:
        """Generate the pull request submission workflow.

        Returns:
            List of markdown lines.
        """
        return [
            "1. Create a feature branch from `main`:",
            "",
            "   ```bash",
            "   git checkout -b feature/my-feature",
            "   ```",
            "",
            "2. Make your changes and commit with a descriptive message:",
            "",
            "   ```bash",
            "   git add .",
            '   git commit -m "feat: add my new feature"',
            "   ```",
            "",
            "3. Push your branch to your fork:",
            "",
            "   ```bash",
            "   git push origin feature/my-feature",
            "   ```",
            "",
            "4. Open a Pull Request against the `main` branch",
            "5. Describe your changes and link any related issues",
            "6. Wait for review and address any feedback",
        ]

    @staticmethod
    def _issue_guidance(project_root: Path) -> list[str]:
        """Generate issue reporting guidance.

        Args:
            project_root: Root directory of the project.

        Returns:
            List of markdown lines.
        """
        lines: list[str] = [
            "When reporting issues, please include:",
            "",
            "- A clear and descriptive title",
            "- Steps to reproduce the problem",
            "- Expected behavior vs actual behavior",
            "- Your environment (OS, language version, etc.)",
        ]

        templates_dir = project_root / ".github" / "ISSUE_TEMPLATE"
        if templates_dir.is_dir():
            lines.append("")
            lines.append(
                "Please use the provided "
                "[issue templates](.github/ISSUE_TEMPLATE/) "
                "when applicable."
            )

        return lines
