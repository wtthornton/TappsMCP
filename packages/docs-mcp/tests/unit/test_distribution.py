"""Tests for DocsMCP distribution, packaging, and CLI."""

from __future__ import annotations

import importlib
from pathlib import Path

from click.testing import CliRunner

from docs_mcp.cli import cli


class TestPackageMetadata:
    """Verify package metadata is correct."""

    def test_version_defined(self) -> None:
        from docs_mcp import __version__

        assert __version__
        assert isinstance(__version__, str)
        # Should be semver-like
        parts = __version__.split(".")
        assert len(parts) >= 2

    def test_package_importable(self) -> None:
        import docs_mcp

        assert hasattr(docs_mcp, "__version__")

    def test_main_module_importable(self) -> None:
        mod = importlib.import_module("docs_mcp.__main__")
        assert mod is not None
        assert hasattr(mod, "cli")

    def test_cli_module_importable(self) -> None:
        mod = importlib.import_module("docs_mcp.cli")
        assert hasattr(mod, "cli")

    def test_server_module_importable(self) -> None:
        mod = importlib.import_module("docs_mcp.server")
        assert hasattr(mod, "mcp")
        assert hasattr(mod, "run_server")


class TestCLICommands:
    """Verify all CLI commands work via CliRunner."""

    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_version_command(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "docsmcp" in result.output.lower()
        assert "0.1.0" in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DocsMCP" in result.output
        assert "serve" in result.output
        assert "doctor" in result.output
        assert "version" in result.output

    def test_serve_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--transport" in result.output
        assert "stdio" in result.output
        assert "http" in result.output

    def test_doctor_runs(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "DocsMCP" in result.output
        assert "Done" in result.output

    def test_doctor_checks_dependencies(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "mcp SDK" in result.output
        assert "jinja2" in result.output
        assert "gitpython" in result.output

    def test_scan_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0

    def test_generate_not_implemented(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["generate"])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output


class TestDockerfile:
    """Verify Dockerfile exists and has expected content."""

    def test_dockerfile_exists(self) -> None:
        dockerfile = Path(__file__).parents[2] / "Dockerfile"
        assert dockerfile.exists(), f"Dockerfile not found at {dockerfile}"

    def test_dockerfile_has_multistage(self) -> None:
        dockerfile = Path(__file__).parents[2] / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "AS builder" in content
        assert "FROM python:3.12-slim" in content

    def test_dockerfile_has_entrypoint(self) -> None:
        dockerfile = Path(__file__).parents[2] / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "ENTRYPOINT" in content
        assert "docs_mcp" in content

    def test_dockerfile_has_labels(self) -> None:
        dockerfile = Path(__file__).parents[2] / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "DocsMCP" in content
        assert "org.opencontainers.image.title" in content

    def test_dockerfile_non_root_user(self) -> None:
        dockerfile = Path(__file__).parents[2] / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "useradd" in content
        assert "USER" in content

    def test_dockerfile_has_healthcheck(self) -> None:
        dockerfile = Path(__file__).parents[2] / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "HEALTHCHECK" in content


class TestInstallationDocs:
    """Verify installation documentation exists and has expected content."""

    def test_installation_md_exists(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        installation = docs_dir / "INSTALLATION.md"
        assert installation.exists()

    def test_installation_has_claude_config(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        content = (docs_dir / "INSTALLATION.md").read_text(encoding="utf-8")
        assert "claude" in content.lower()
        assert "mcpServers" in content

    def test_installation_has_cursor_config(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        content = (docs_dir / "INSTALLATION.md").read_text(encoding="utf-8")
        assert "cursor" in content.lower()

    def test_installation_has_docker_section(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        content = (docs_dir / "INSTALLATION.md").read_text(encoding="utf-8")
        assert "docker" in content.lower()
        assert "docker run" in content.lower() or "docker build" in content.lower()

    def test_installation_has_pip_instructions(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        content = (docs_dir / "INSTALLATION.md").read_text(encoding="utf-8")
        assert "pip install" in content

    def test_installation_has_uv_instructions(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        content = (docs_dir / "INSTALLATION.md").read_text(encoding="utf-8")
        assert "uv add" in content

    def test_readme_exists(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        readme = docs_dir / "README.md"
        assert readme.exists()

    def test_readme_has_overview(self) -> None:
        docs_dir = Path(__file__).parents[2] / "docs"
        content = (docs_dir / "README.md").read_text(encoding="utf-8")
        assert "DocsMCP" in content
        assert "MCP server" in content


class TestPyprojectToml:
    """Verify pyproject.toml has required packaging fields."""

    def _read_pyproject(self) -> str:
        pyproject = Path(__file__).parents[2] / "pyproject.toml"
        return pyproject.read_text(encoding="utf-8")

    def test_has_project_urls(self) -> None:
        content = self._read_pyproject()
        assert "[project.urls]" in content
        assert "Homepage" in content
        assert "Repository" in content

    def test_has_console_script(self) -> None:
        content = self._read_pyproject()
        assert "[project.scripts]" in content
        assert "docsmcp" in content

    def test_has_build_system(self) -> None:
        content = self._read_pyproject()
        assert "[build-system]" in content
        assert "hatchling" in content

    def test_has_classifiers(self) -> None:
        content = self._read_pyproject()
        assert "Topic :: Documentation" in content

    def test_has_readme(self) -> None:
        content = self._read_pyproject()
        assert 'readme = "docs/README.md"' in content

    def test_python_requires(self) -> None:
        content = self._read_pyproject()
        assert 'requires-python = ">=3.12"' in content

    def test_has_required_dependencies(self) -> None:
        content = self._read_pyproject()
        for dep in ["mcp", "click", "jinja2", "gitpython", "pydantic", "structlog", "pyyaml"]:
            assert dep in content, f"Missing dependency: {dep}"
