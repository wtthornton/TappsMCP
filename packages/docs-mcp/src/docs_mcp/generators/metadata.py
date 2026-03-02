"""Project metadata extraction from pyproject.toml, package.json, and Cargo.toml."""

from __future__ import annotations

import json
import tomllib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class ProjectMetadata(BaseModel):
    """Extracted project metadata from configuration files."""

    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    author_email: str = ""
    license: str = ""
    python_requires: str = ""
    homepage: str = ""
    repository: str = ""
    keywords: list[str] = []
    dependencies: list[str] = []
    dev_dependencies: list[str] = []
    entry_points: dict[str, str] = {}
    source_file: str = ""


class MetadataExtractor:
    """Extracts project metadata from various configuration file formats."""

    def extract(self, project_root: Path) -> ProjectMetadata:
        """Extract metadata from the project root directory.

        Tries parsers in order: pyproject.toml, package.json, Cargo.toml.
        Falls back to directory name if nothing is found.
        """
        project_root = project_root.resolve()

        # Try pyproject.toml first (PEP 621)
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            result = self._parse_pyproject(pyproject)
            if result.name:
                return result

        # Try package.json (Node.js)
        package_json = project_root / "package.json"
        if package_json.exists():
            result = self._parse_package_json(package_json)
            if result.name:
                return result

        # Try Cargo.toml (Rust)
        cargo_toml = project_root / "Cargo.toml"
        if cargo_toml.exists():
            result = self._parse_cargo_toml(cargo_toml)
            if result.name:
                return result

        # Fallback to directory name
        return ProjectMetadata(name=project_root.name)

    def _parse_pyproject(self, path: Path) -> ProjectMetadata:
        """Parse PEP 621 metadata from pyproject.toml."""
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("pyproject_parse_failed", path=str(path), reason=str(exc))
            return ProjectMetadata(source_file=str(path.name))

        project = data.get("project", {})
        if not isinstance(project, dict):
            return ProjectMetadata(source_file=str(path.name))

        # Extract author info
        author = ""
        author_email = ""
        authors = project.get("authors", [])
        if isinstance(authors, list) and authors:
            first = authors[0]
            if isinstance(first, dict):
                author = first.get("name", "")
                author_email = first.get("email", "")

        # Extract license
        license_val = project.get("license", "")
        if isinstance(license_val, dict):
            license_val = license_val.get("text", license_val.get("file", ""))
        if not isinstance(license_val, str):
            license_val = str(license_val)

        # Extract URLs
        urls = project.get("urls", {})
        if not isinstance(urls, dict):
            urls = {}
        homepage = urls.get("Homepage", urls.get("homepage", ""))
        repository = urls.get("Repository", urls.get("repository", urls.get("Source", "")))

        # Extract dependencies
        deps = project.get("dependencies", [])
        if not isinstance(deps, list):
            deps = []

        # Extract dev/optional dependencies
        dev_deps: list[str] = []
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group_deps in optional.values():
                if isinstance(group_deps, list):
                    dev_deps.extend(str(d) for d in group_deps)

        # Extract entry points / scripts
        entry_points: dict[str, str] = {}
        scripts = project.get("scripts", {})
        if isinstance(scripts, dict):
            entry_points = {str(k): str(v) for k, v in scripts.items()}

        # Extract keywords
        keywords = project.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

        return ProjectMetadata(
            name=str(project.get("name", "")),
            version=str(project.get("version", "")),
            description=str(project.get("description", "")),
            author=str(author),
            author_email=str(author_email),
            license=str(license_val),
            python_requires=str(project.get("requires-python", "")),
            homepage=str(homepage),
            repository=str(repository),
            keywords=[str(k) for k in keywords],
            dependencies=[str(d) for d in deps],
            dev_dependencies=dev_deps,
            entry_points=entry_points,
            source_file="pyproject.toml",
        )

    def _parse_package_json(self, path: Path) -> ProjectMetadata:
        """Parse metadata from package.json (Node.js)."""
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("package_json_parse_failed", path=str(path), reason=str(exc))
            return ProjectMetadata(source_file="package.json")

        if not isinstance(data, dict):
            return ProjectMetadata(source_file="package.json")

        # Extract author
        author = ""
        author_email = ""
        author_raw = data.get("author", "")
        if isinstance(author_raw, dict):
            author = author_raw.get("name", "")
            author_email = author_raw.get("email", "")
        elif isinstance(author_raw, str):
            author = author_raw

        # Extract license
        license_val = data.get("license", "")
        if isinstance(license_val, dict):
            license_val = license_val.get("type", "")
        if not isinstance(license_val, str):
            license_val = str(license_val)

        # Extract URLs
        homepage = str(data.get("homepage", ""))
        repository = data.get("repository", "")
        if isinstance(repository, dict):
            repository = repository.get("url", "")
        if not isinstance(repository, str):
            repository = str(repository)

        # Extract dependencies
        deps = data.get("dependencies", {})
        dep_list = list(deps.keys()) if isinstance(deps, dict) else []

        dev_deps_raw = data.get("devDependencies", {})
        dev_dep_list = list(dev_deps_raw.keys()) if isinstance(dev_deps_raw, dict) else []

        # Extract entry points from bin
        entry_points: dict[str, str] = {}
        bin_val = data.get("bin", {})
        if isinstance(bin_val, dict):
            entry_points = {str(k): str(v) for k, v in bin_val.items()}
        elif isinstance(bin_val, str):
            name = str(data.get("name", ""))
            if name:
                entry_points[name] = bin_val

        # Extract keywords
        keywords = data.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

        return ProjectMetadata(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            description=str(data.get("description", "")),
            author=str(author),
            author_email=str(author_email),
            license=license_val,
            homepage=homepage,
            repository=repository,
            keywords=[str(k) for k in keywords],
            dependencies=dep_list,
            dev_dependencies=dev_dep_list,
            entry_points=entry_points,
            source_file="package.json",
        )

    def _parse_cargo_toml(self, path: Path) -> ProjectMetadata:
        """Parse metadata from Cargo.toml (Rust)."""
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("cargo_toml_parse_failed", path=str(path), reason=str(exc))
            return ProjectMetadata(source_file="Cargo.toml")

        package = data.get("package", {})
        if not isinstance(package, dict):
            return ProjectMetadata(source_file="Cargo.toml")

        # Extract author info
        author = ""
        author_email = ""
        authors = package.get("authors", [])
        if isinstance(authors, list) and authors:
            first = str(authors[0])
            # Cargo authors often use "Name <email>" format
            if "<" in first and ">" in first:
                idx = first.index("<")
                author = first[:idx].strip()
                author_email = first[idx + 1 : first.index(">")].strip()
            else:
                author = first

        # Extract license
        license_val = str(package.get("license", ""))

        # Extract URLs
        homepage = str(package.get("homepage", ""))
        repository = str(package.get("repository", ""))

        # Extract dependencies
        deps = data.get("dependencies", {})
        dep_list = list(deps.keys()) if isinstance(deps, dict) else []

        dev_deps_raw = data.get("dev-dependencies", {})
        dev_dep_list = list(dev_deps_raw.keys()) if isinstance(dev_deps_raw, dict) else []

        # Extract keywords
        keywords = package.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

        # Extract entry points from [[bin]] sections
        entry_points: dict[str, str] = {}
        bins = data.get("bin", [])
        if isinstance(bins, list):
            for b in bins:
                if isinstance(b, dict) and "name" in b:
                    entry_points[str(b["name"])] = str(b.get("path", ""))

        return ProjectMetadata(
            name=str(package.get("name", "")),
            version=str(package.get("version", "")),
            description=str(package.get("description", "")),
            author=author,
            author_email=author_email,
            license=license_val,
            homepage=homepage,
            repository=repository,
            keywords=[str(k) for k in keywords],
            dependencies=dep_list,
            dev_dependencies=dev_dep_list,
            entry_points=entry_points,
            source_file="Cargo.toml",
        )
