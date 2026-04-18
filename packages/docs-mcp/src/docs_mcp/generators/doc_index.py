"""Documentation index generator (Epic 85.2).

Scans a project for documentation files and generates a structured
index/map with categories, descriptions, and freshness indicators.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import ClassVar

import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Directories to skip when scanning.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".env",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        ".tapps-mcp",
    }
)

# Extensions considered documentation.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt", ".adoc"})


class DocEntry(BaseModel):
    """A single documentation file entry."""

    path: str
    title: str
    category: str
    description: str = ""
    last_modified: str = ""
    word_count: int = 0


class DocIndexResult(BaseModel):
    """Result of documentation index generation."""

    content: str
    entries: list[DocEntry]
    total_files: int
    categories: dict[str, int]


class DocIndexGenerator:
    """Generates a documentation index/map for a project.

    Scans for documentation files, extracts titles and descriptions,
    categorizes them, and produces a structured markdown index.
    """

    # Filename patterns -> category mapping
    _CATEGORY_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "Getting Started": ["readme", "getting-started", "quickstart", "setup", "install"],
        "Architecture": ["architecture", "design", "adr", "c4", "diagram"],
        "API Reference": ["api", "reference", "endpoint"],
        "Guides": [
            "guide",
            "tutorial",
            "howto",
            "how-to",
            "walkthrough",
            "onboarding",
            "contributing",
        ],
        "Configuration": ["config", "settings", "env", "environment"],
        "Operations": [
            "deploy",
            "docker",
            "ci",
            "cd",
            "pipeline",
            "monitoring",
            "runbook",
            "ops",
        ],
        "Planning": ["epic", "story", "prd", "roadmap", "plan", "rfc", "proposal"],
        "Release": ["changelog", "release", "migration", "upgrade"],
    }

    def generate(
        self,
        project_root: Path,
        *,
        doc_dirs: list[str] | None = None,
        output_path: str | None = None,
    ) -> DocIndexResult:
        """Generate a documentation index.

        Args:
            project_root: Root directory of the project.
            doc_dirs: Optional list of directories to scan.
                When empty, scans the entire project.
            output_path: Project-root-relative path where the generated index
                will be written. When set, link targets in the rendered markdown
                are made relative to the index's parent directory so markdown
                viewers resolve them correctly. When None, targets remain
                project-root-relative (legacy behavior).

        Returns:
            DocIndexResult with the markdown index.
        """
        if not project_root.is_dir():
            return DocIndexResult(content="", entries=[], total_files=0, categories={})

        # Collect doc files
        entries: list[DocEntry] = []
        if doc_dirs:
            for d in doc_dirs:
                dir_path = project_root / d
                if dir_path.is_dir():
                    entries.extend(self._scan_dir(project_root, dir_path))
        else:
            entries.extend(self._scan_dir(project_root, project_root))

        # Also pick up root-level docs
        if not doc_dirs:
            for f in project_root.iterdir():
                if f.is_file() and f.suffix.lower() in _DOC_EXTENSIONS:
                    entry = self._make_entry(project_root, f)
                    if entry and not any(e.path == entry.path for e in entries):
                        entries.append(entry)

        entries.sort(key=lambda e: (e.category, e.path))

        # Build category counts
        categories: dict[str, int] = {}
        for entry in entries:
            categories[entry.category] = categories.get(entry.category, 0) + 1

        content = self._render_markdown(
            entries,
            categories,
            project_root.name,
            output_path=output_path,
        )

        return DocIndexResult(
            content=content,
            entries=entries,
            total_files=len(entries),
            categories=categories,
        )

    def _scan_dir(self, project_root: Path, scan_dir: Path) -> list[DocEntry]:
        """Recursively scan a directory for doc files."""
        entries: list[DocEntry] = []
        try:
            for item in sorted(scan_dir.iterdir()):
                if item.is_dir():
                    if item.name in _SKIP_DIRS or item.name.startswith("."):
                        continue
                    entries.extend(self._scan_dir(project_root, item))
                elif item.is_file() and item.suffix.lower() in _DOC_EXTENSIONS:
                    entry = self._make_entry(project_root, item)
                    if entry:
                        entries.append(entry)
        except PermissionError:
            logger.debug("permission_denied", path=str(scan_dir))
        return entries

    def _make_entry(self, project_root: Path, file_path: Path) -> DocEntry | None:
        """Create a DocEntry from a file."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return None

        rel_path = str(file_path.relative_to(project_root)).replace("\\", "/")
        title = self._extract_title(content, file_path.stem)
        description = self._extract_description(content)
        category = self._categorize(rel_path, content)
        word_count = len(content.split())

        # Last modified
        try:
            mtime = file_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
        except OSError:
            last_modified = ""

        return DocEntry(
            path=rel_path,
            title=title,
            category=category,
            description=description,
            last_modified=last_modified,
            word_count=word_count,
        )

    def _extract_title(self, content: str, fallback: str) -> str:
        """Extract title from first H1 heading or use fallback."""
        for line in content.split("\n")[:20]:
            line = line.strip()
            if line.startswith("# ") and not line.startswith("##"):
                return line[2:].strip()
        return fallback.replace("-", " ").replace("_", " ").title()

    def _extract_description(self, content: str) -> str:
        """Extract first non-heading, non-empty paragraph as description."""
        lines = content.split("\n")
        in_frontmatter = False
        for line in lines[:30]:
            stripped = line.strip()
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            if not stripped or stripped.startswith("#") or stripped.startswith(">"):
                continue
            if stripped.startswith("```"):
                break
            # Return first real paragraph, truncated
            if len(stripped) > 120:
                return stripped[:117] + "..."
            return stripped
        return ""

    def _categorize(self, rel_path: str, content: str) -> str:
        """Categorize a doc file based on path and content."""
        path_lower = rel_path.lower()
        for category, patterns in self._CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if pattern in path_lower:
                    return category
        # Fallback: check content headings
        for line in content.split("\n")[:10]:
            line_lower = line.lower().strip()
            for category, patterns in self._CATEGORY_PATTERNS.items():
                for pattern in patterns:
                    if pattern in line_lower:
                        return category
        return "Other"

    def _render_markdown(
        self,
        entries: list[DocEntry],
        categories: dict[str, int],
        project_name: str,
        *,
        output_path: str | None = None,
    ) -> str:
        """Render the index as markdown."""
        # Base directory used to make link targets relative. When an output
        # path is supplied (e.g. "docs/INDEX.md"), links are resolved relative
        # to its parent ("docs/") so markdown viewers don't produce doubled
        # paths like "docs/docs/guides/foo.md".
        link_base = PurePath(output_path).parent.as_posix() if output_path else ""

        lines: list[str] = []
        lines.append(f"# {project_name} — Documentation Index")
        lines.append("")
        lines.append(f"**{len(entries)} documents** across **{len(categories)} categories**")
        lines.append("")

        # Summary table
        if categories:
            lines.append("## Overview")
            lines.append("")
            lines.append("| Category | Count |")
            lines.append("|---|---|")
            for cat in sorted(categories):
                lines.append(f"| {cat} | {categories[cat]} |")
            lines.append("")

        # Group by category
        current_category = ""
        for entry in entries:
            if entry.category != current_category:
                current_category = entry.category
                lines.append(f"## {current_category}")
                lines.append("")

            link_target = _relativize_link(entry.path, link_base)
            desc = f" — {entry.description}" if entry.description else ""
            modified = f" *(updated {entry.last_modified})*" if entry.last_modified else ""
            lines.append(f"- [{entry.title}]({link_target}){desc}{modified}")

        lines.append("")
        return "\n".join(lines)


def _relativize_link(entry_path: str, link_base: str) -> str:
    """Return entry_path rewritten relative to link_base (posix-style).

    entry_path is always project-root-relative. link_base is either an empty
    string (legacy: keep project-root-relative) or a project-root-relative
    directory like "docs". The result uses forward slashes regardless of the
    host OS so the emitted markdown is portable.
    """
    if not link_base or link_base == ".":
        return entry_path
    rel = os.path.relpath(entry_path, start=link_base)
    return PurePath(rel).as_posix()
