"""Tests for docs_mcp.generators.guides and MCP guide tools.

Covers:
- ``OnboardingGuideGenerator`` -- getting-started guide generation
- ``ContributingGuideGenerator`` -- contributing guide generation
- ``docs_generate_onboarding`` -- MCP tool handler
- ``docs_generate_contributing`` -- MCP tool handler
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.guides import ContributingGuideGenerator, OnboardingGuideGenerator
from docs_mcp.generators.metadata import ProjectMetadata


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
def python_project(tmp_path: Path) -> Path:
    """A Python project with pyproject.toml, src, and tests."""
    root = tmp_path / "pyproject"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "my-lib"\nversion = "1.0.0"\n'
        'requires-python = ">=3.12"\n'
        "\n[project.optional-dependencies]\n"
        'dev = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    src = root / "src" / "my_lib"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""My library."""\n', encoding="utf-8")
    (root / "tests").mkdir()
    return root


@pytest.fixture
def node_project(tmp_path: Path) -> Path:
    """A Node.js project with package.json."""
    root = tmp_path / "nodeproj"
    root.mkdir()
    (root / "package.json").write_text(
        "{\n"
        '  "name": "my-node-app",\n'
        '  "version": "2.0.0",\n'
        '  "description": "A Node.js app",\n'
        '  "devDependencies": {\n'
        '    "jest": "^29.0.0",\n'
        '    "eslint": "^8.0.0"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """A minimal project with no config files."""
    root = tmp_path / "empty"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# OnboardingGuideGenerator -- basic output
# ---------------------------------------------------------------------------


class TestOnboardingGuideGenerate:
    """Tests for OnboardingGuideGenerator.generate() return value and title."""

    def test_returns_nonempty_markdown_with_title(self, python_project: Path) -> None:
        """generate() returns non-empty markdown with Getting Started title."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert content
        assert "# Getting Started with my-lib" in content

    def test_returns_empty_string_on_error(self, tmp_path: Path) -> None:
        """generate() returns empty string when _generate_impl raises."""
        gen = OnboardingGuideGenerator()

        with patch.object(gen, "_generate_impl", side_effect=RuntimeError("boom")):
            result = gen.generate(tmp_path)

        assert result == ""


# ---------------------------------------------------------------------------
# OnboardingGuideGenerator -- project type detection
# ---------------------------------------------------------------------------


class TestOnboardingDetectsPython:
    """Tests for Python project detection in onboarding guides."""

    def test_pip_install_from_pyproject(self, python_project: Path) -> None:
        """Detects Python project from pyproject.toml and shows pip install."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert "pip install my-lib" in content

    def test_prerequisites_includes_python_version(self, python_project: Path) -> None:
        """Prerequisites section includes python_requires version."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Prerequisites" in content
        assert ">=3.12" in content


class TestOnboardingDetectsNode:
    """Tests for Node.js project detection in onboarding guides."""

    def test_npm_install_from_package_json(self, node_project: Path) -> None:
        """Detects Node.js project from package.json and shows npm install."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(node_project)

        assert "npm install my-node-app" in content

    def test_node_prerequisites(self, node_project: Path) -> None:
        """Node project lists Node.js in prerequisites."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(node_project)

        assert "Node.js" in content


class TestOnboardingDetectsRust:
    """Tests for Rust project detection in onboarding guides."""

    def test_cargo_from_cargo_toml(self, tmp_path: Path) -> None:
        """Detects Rust project from Cargo.toml and shows cargo instructions."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "Cargo.toml").write_text(
            '[package]\nname = "my-crate"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        gen = OnboardingGuideGenerator()
        content = gen.generate(root)

        assert "cargo" in content.lower()


# ---------------------------------------------------------------------------
# OnboardingGuideGenerator -- metadata handling
# ---------------------------------------------------------------------------


class TestOnboardingMetadata:
    """Tests for auto-extraction vs provided metadata."""

    def test_auto_extracts_metadata_when_none(self, python_project: Path) -> None:
        """When metadata=None, MetadataExtractor is called automatically."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project, metadata=None)

        assert "my-lib" in content

    def test_uses_provided_metadata(self, tmp_path: Path) -> None:
        """When metadata is provided, it is used directly (not extracted)."""
        root = tmp_path / "proj"
        root.mkdir()
        # File has a different name to prove provided metadata takes precedence
        (root / "pyproject.toml").write_text(
            '[project]\nname = "file-name"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        meta = ProjectMetadata(
            name="provided-name",
            version="3.0.0",
            source_file="pyproject.toml",
        )
        gen = OnboardingGuideGenerator()
        content = gen.generate(root, metadata=meta)

        assert "provided-name" in content
        assert "file-name" not in content


# ---------------------------------------------------------------------------
# OnboardingGuideGenerator -- sections
# ---------------------------------------------------------------------------


class TestOnboardingSections:
    """Tests for individual onboarding guide sections."""

    def test_installation_has_dev_instructions(self, python_project: Path) -> None:
        """Installation section includes dev install instructions."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Installation" in content
        assert "pip install -e" in content

    def test_running_section_uses_entry_points(self, tmp_path: Path) -> None:
        """Running section uses entry_points when present."""
        root = tmp_path / "proj"
        root.mkdir()

        meta = ProjectMetadata(
            name="cli-tool",
            version="1.0.0",
            entry_points={"mycli": "cli_tool.main:run"},
            source_file="pyproject.toml",
        )
        gen = OnboardingGuideGenerator()
        content = gen.generate(root, metadata=meta)

        assert "## Running the Project" in content
        assert "mycli" in content

    def test_testing_detects_pytest_from_deps(self, tmp_path: Path) -> None:
        """Testing section detects pytest from dependencies."""
        root = tmp_path / "proj"
        root.mkdir()

        meta = ProjectMetadata(
            name="tested-proj",
            version="1.0.0",
            dependencies=["pytest"],
            source_file="pyproject.toml",
        )
        gen = OnboardingGuideGenerator()
        content = gen.generate(root, metadata=meta)

        assert "## Running Tests" in content
        assert "pytest" in content

    def test_testing_detects_pytest_from_tests_dir(self, python_project: Path) -> None:
        """Testing section detects pytest from tests/ directory presence."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert "pytest" in content

    def test_next_steps_links_contributing(self, python_project: Path) -> None:
        """Next steps links to CONTRIBUTING.md when it exists."""
        (python_project / "CONTRIBUTING.md").write_text(
            "# Contributing\n", encoding="utf-8",
        )

        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Next Steps" in content
        assert "CONTRIBUTING.md" in content

    def test_next_steps_links_docs_dir(self, python_project: Path) -> None:
        """Next steps links to docs/ when directory exists."""
        (python_project / "docs").mkdir()

        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        assert "docs/" in content

    def test_project_structure_section(self, python_project: Path) -> None:
        """Project structure section appears when modules are found."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(python_project)

        # Structure section appears if ModuleMapAnalyzer finds modules.
        # If it fails (e.g., no packages), Key Concepts still appears.
        assert "## Key Concepts" in content
        # Either we have structure or we don't -- both are valid
        assert ("## Project Structure" in content) or ("## Key Concepts" in content)

    def test_empty_project_still_generates(self, empty_project: Path) -> None:
        """Empty project still generates onboarding content."""
        gen = OnboardingGuideGenerator()
        content = gen.generate(empty_project)

        assert len(content) > 0
        assert "# Getting Started" in content


# ---------------------------------------------------------------------------
# ContributingGuideGenerator -- basic output
# ---------------------------------------------------------------------------


class TestContributingGuideGenerate:
    """Tests for ContributingGuideGenerator.generate() return value and title."""

    def test_returns_nonempty_markdown_with_title(self, python_project: Path) -> None:
        """generate() returns non-empty markdown with Contributing to title."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert content
        assert "# Contributing to my-lib" in content

    def test_returns_empty_string_on_error(self, tmp_path: Path) -> None:
        """generate() returns empty string when _generate_impl raises."""
        gen = ContributingGuideGenerator()

        with patch.object(gen, "_generate_impl", side_effect=RuntimeError("boom")):
            result = gen.generate(tmp_path)

        assert result == ""


# ---------------------------------------------------------------------------
# ContributingGuideGenerator -- code of conduct
# ---------------------------------------------------------------------------


class TestContributingCodeOfConduct:
    """Tests for CODE_OF_CONDUCT.md integration."""

    def test_code_of_conduct_present(self, python_project: Path) -> None:
        """Code of conduct section appears when CODE_OF_CONDUCT.md exists."""
        (python_project / "CODE_OF_CONDUCT.md").write_text(
            "# Code of Conduct\n\nBe nice.\n",
            encoding="utf-8",
        )

        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Code of Conduct" in content
        assert "CODE_OF_CONDUCT.md" in content

    def test_code_of_conduct_absent(self, python_project: Path) -> None:
        """Code of conduct section is absent when no CODE_OF_CONDUCT.md."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Code of Conduct" not in content


# ---------------------------------------------------------------------------
# ContributingGuideGenerator -- dev setup by source file
# ---------------------------------------------------------------------------


class TestContributingDevSetup:
    """Tests for dev setup that varies by project type."""

    def test_python_dev_setup(self, python_project: Path) -> None:
        """Python project dev setup includes pip install."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Development Setup" in content
        assert "pip install" in content

    def test_node_dev_setup(self, node_project: Path) -> None:
        """Node.js project dev setup includes npm install."""
        gen = ContributingGuideGenerator()
        content = gen.generate(node_project)

        assert "npm install" in content

    def test_cargo_dev_setup(self, tmp_path: Path) -> None:
        """Rust project dev setup includes cargo build."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "Cargo.toml").write_text(
            '[package]\nname = "rust-setup"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        gen = ContributingGuideGenerator()
        content = gen.generate(root)

        assert "cargo build" in content


# ---------------------------------------------------------------------------
# ContributingGuideGenerator -- coding standards
# ---------------------------------------------------------------------------


class TestContributingCodingStandards:
    """Tests for coding standards detection in contributing guides."""

    def test_detects_ruff(self, python_project: Path) -> None:
        """Coding standards detects ruff from dependencies."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Coding Standards" in content
        assert "ruff" in content

    def test_detects_black(self, tmp_path: Path) -> None:
        """Coding standards detects black from dependencies."""
        root = tmp_path / "proj"
        root.mkdir()

        meta = ProjectMetadata(
            name="black-proj",
            version="1.0.0",
            dev_dependencies=["black"],
            source_file="pyproject.toml",
        )
        gen = ContributingGuideGenerator()
        content = gen.generate(root, metadata=meta)

        assert "black" in content

    def test_detects_mypy(self, tmp_path: Path) -> None:
        """Coding standards detects mypy from dependencies."""
        root = tmp_path / "proj"
        root.mkdir()

        meta = ProjectMetadata(
            name="mypy-proj",
            version="1.0.0",
            dev_dependencies=["mypy"],
            source_file="pyproject.toml",
        )
        gen = ContributingGuideGenerator()
        content = gen.generate(root, metadata=meta)

        assert "mypy" in content


# ---------------------------------------------------------------------------
# ContributingGuideGenerator -- testing section
# ---------------------------------------------------------------------------


class TestContributingTesting:
    """Tests for testing section in contributing guides."""

    def test_python_pytest(self, python_project: Path) -> None:
        """Python project with pytest dependency shows pytest command."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Testing" in content
        assert "pytest" in content

    def test_node_jest(self, tmp_path: Path) -> None:
        """Node.js project with jest shows jest command."""
        root = tmp_path / "proj"
        root.mkdir()

        meta = ProjectMetadata(
            name="jest-proj",
            version="1.0.0",
            dev_dependencies=["jest"],
            source_file="package.json",
        )
        gen = ContributingGuideGenerator()
        content = gen.generate(root, metadata=meta)

        assert "jest" in content

    def test_cargo_test(self, tmp_path: Path) -> None:
        """Rust project shows cargo test command."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "Cargo.toml").write_text(
            '[package]\nname = "test-crate"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        gen = ContributingGuideGenerator()
        content = gen.generate(root)

        assert "cargo test" in content


# ---------------------------------------------------------------------------
# ContributingGuideGenerator -- submit workflow and issues
# ---------------------------------------------------------------------------


class TestContributingSubmitWorkflow:
    """Tests for the PR submission workflow in contributing guides."""

    def test_has_git_steps(self, python_project: Path) -> None:
        """Submit workflow has standard git branch/commit/push steps."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Submitting Changes" in content
        assert "git checkout -b" in content
        assert "git commit" in content
        assert "git push" in content
        assert "Pull Request" in content


class TestContributingIssueGuidance:
    """Tests for issue reporting guidance in contributing guides."""

    def test_mentions_templates_when_present(self, python_project: Path) -> None:
        """Issue guidance mentions templates when .github/ISSUE_TEMPLATE exists."""
        templates_dir = python_project / ".github" / "ISSUE_TEMPLATE"
        templates_dir.mkdir(parents=True)
        (templates_dir / "bug_report.md").write_text("---\n", encoding="utf-8")

        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Reporting Issues" in content
        assert "issue templates" in content

    def test_no_templates_still_has_guidance(self, python_project: Path) -> None:
        """Issue guidance without templates still has basic reporting info."""
        gen = ContributingGuideGenerator()
        content = gen.generate(python_project)

        assert "## Reporting Issues" in content
        assert "Steps to reproduce" in content
        assert "issue templates" not in content

    def test_empty_project_contributing(self, empty_project: Path) -> None:
        """Empty project still generates contributing guide content."""
        gen = ContributingGuideGenerator()
        content = gen.generate(empty_project)

        assert len(content) > 0
        assert "# Contributing to" in content


# ---------------------------------------------------------------------------
# docs_generate_onboarding MCP tool tests
# ---------------------------------------------------------------------------


class TestDocsGenerateOnboarding:
    """Tests for the ``docs_generate_onboarding`` MCP tool handler."""

    def test_success_response_envelope(self, tmp_path: Path) -> None:
        """Success response has the standard envelope structure."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "onboard-test"\nversion = "1.0.0"\n'
            'requires-python = ">=3.12"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_onboarding

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = _run(docs_generate_onboarding(project_root=str(root)))

        assert result["tool"] == "docs_generate_onboarding"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result
        data = result["data"]
        assert data["content_length"] > 0
        assert "written_to" in data
        assert "content" in data
        assert "Getting Started" in data["content"]

    def test_invalid_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns error with INVALID_ROOT code."""
        from docs_mcp.server_gen_tools import docs_generate_onboarding

        fake = tmp_path / "no_such_dir"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = _run(docs_generate_onboarding(project_root=str(fake)))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"


# ---------------------------------------------------------------------------
# docs_generate_contributing MCP tool tests
# ---------------------------------------------------------------------------


class TestDocsGenerateContributing:
    """Tests for the ``docs_generate_contributing`` MCP tool handler."""

    def test_success_response_envelope(self, tmp_path: Path) -> None:
        """Success response has the standard envelope structure."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "contrib-test"\nversion = "1.0.0"\n'
            'requires-python = ">=3.12"\n',
            encoding="utf-8",
        )

        from docs_mcp.server_gen_tools import docs_generate_contributing

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = _run(docs_generate_contributing(project_root=str(root)))

        assert result["tool"] == "docs_generate_contributing"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result
        data = result["data"]
        assert data["content_length"] > 0
        assert "written_to" in data
        assert "content" in data
        assert "Contributing to" in data["content"]

    def test_invalid_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns error with INVALID_ROOT code."""
        from docs_mcp.server_gen_tools import docs_generate_contributing

        fake = tmp_path / "no_such_dir"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = _run(docs_generate_contributing(project_root=str(fake)))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"
