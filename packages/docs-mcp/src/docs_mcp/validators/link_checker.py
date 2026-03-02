"""Internal link validator for documentation files."""

from __future__ import annotations

import os
import re
from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# Regex for markdown links: [text](target)
# Captures link text (group 1) and target (group 2).
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Documentation file extensions to scan.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# Directories to skip.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".env", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs",
})


class BrokenLink(BaseModel):
    """A single broken link finding."""

    source_file: str
    line: int
    link_text: str
    link_target: str
    reason: str  # "file_not_found", "anchor_not_found", "invalid_path"


class LinkReport(BaseModel):
    """Aggregated link check results."""

    total_links: int = 0
    valid_links: int = 0
    broken_links: list[BrokenLink] = []


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if dirname in _SKIP_DIRS:
        return True
    return dirname.endswith(".egg-info")


def _is_external_link(target: str) -> bool:
    """Check if a link target is an external URL."""
    return target.startswith(("http://", "https://", "mailto:", "ftp://", "//"))


def _is_anchor_only(target: str) -> bool:
    """Check if a link target is an anchor-only reference (e.g., #section)."""
    return target.startswith("#")


def _extract_headings(content: str) -> set[str]:
    """Extract markdown heading anchors from content.

    Converts headings to GitHub-style anchor slugs:
    - Lowercase
    - Replace spaces with hyphens
    - Remove non-alphanumeric characters (except hyphens)
    """
    anchors: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Remove leading # characters and whitespace
            heading_text = stripped.lstrip("#").strip()
            # Convert to slug
            slug = heading_text.lower()
            slug = re.sub(r"[^\w\s-]", "", slug)
            slug = re.sub(r"\s+", "-", slug)
            slug = slug.strip("-")
            if slug:
                anchors.add(slug)
    return anchors


def _find_doc_files(
    project_root: Path,
    files: list[str] | None = None,
) -> list[Path]:
    """Find documentation files to check."""
    if files:
        result: list[Path] = []
        for f in files:
            fp = Path(f)
            if not fp.is_absolute():
                fp = project_root / fp
            if fp.exists() and fp.suffix.lower() in _DOC_EXTENSIONS:
                result.append(fp)
        return result

    # Scan entire project
    doc_files: list[Path] = []
    if not project_root.is_dir():
        return doc_files

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        current = Path(dirpath)
        for fname in filenames:
            fpath = current / fname
            if fpath.suffix.lower() in _DOC_EXTENSIONS:
                doc_files.append(fpath)

    return doc_files


def _check_file_links(
    file_path: Path,
    project_root: Path,
    content: str,
) -> tuple[int, int, list[BrokenLink]]:
    """Check all markdown links in a single file.

    Returns:
        Tuple of (total_links, valid_links, broken_links).
    """
    total = 0
    valid = 0
    broken: list[BrokenLink] = []

    rel_source = str(file_path.relative_to(project_root)).replace("\\", "/")
    file_dir = file_path.parent

    # Pre-extract headings from this file for same-file anchor checks
    local_anchors = _extract_headings(content)

    for line_num, line in enumerate(content.splitlines(), start=1):
        for match in _MARKDOWN_LINK_RE.finditer(line):
            link_text = match.group(1)
            link_target = match.group(2).strip()

            # Skip empty links and external URLs
            if not link_target:
                continue
            if _is_external_link(link_target):
                continue

            total += 1

            # Same-file anchor reference
            if _is_anchor_only(link_target):
                anchor = link_target[1:]  # strip leading #
                if anchor in local_anchors:
                    valid += 1
                else:
                    broken.append(BrokenLink(
                        source_file=rel_source,
                        line=line_num,
                        link_text=link_text,
                        link_target=link_target,
                        reason="anchor_not_found",
                    ))
                continue

            # Split file path and optional anchor
            if "#" in link_target:
                file_part, anchor_part = link_target.split("#", 1)
            else:
                file_part = link_target
                anchor_part = None

            # Resolve the target path relative to the source file's directory
            if not file_part:
                # Just an anchor but with a file prefix like "file.md#anchor"
                # This case is handled above; file_part is empty means anchor-only
                valid += 1
                continue

            try:
                target_path = (file_dir / file_part).resolve()
            except (OSError, ValueError):
                broken.append(BrokenLink(
                    source_file=rel_source,
                    line=line_num,
                    link_text=link_text,
                    link_target=link_target,
                    reason="invalid_path",
                ))
                continue

            if not target_path.exists():
                broken.append(BrokenLink(
                    source_file=rel_source,
                    line=line_num,
                    link_text=link_text,
                    link_target=link_target,
                    reason="file_not_found",
                ))
                continue

            # File exists; if there's an anchor, do best-effort check
            if anchor_part and target_path.suffix.lower() in _DOC_EXTENSIONS:
                try:
                    target_content = target_path.read_text(
                        encoding="utf-8", errors="replace",
                    )
                    target_anchors = _extract_headings(target_content)
                    if anchor_part not in target_anchors:
                        broken.append(BrokenLink(
                            source_file=rel_source,
                            line=line_num,
                            link_text=link_text,
                            link_target=link_target,
                            reason="anchor_not_found",
                        ))
                        continue
                except OSError:
                    pass  # Can't read target file; treat as valid

            valid += 1

    return total, valid, broken


class LinkChecker:
    """Validate internal links in documentation files."""

    def check(
        self,
        project_root: Path,
        *,
        files: list[str] | None = None,
    ) -> LinkReport:
        """Run link validation.

        Args:
            project_root: Root of the project to scan.
            files: Optional list of specific files to check.

        Returns:
            A LinkReport with valid/broken link counts.
        """
        if not project_root.is_dir():
            return LinkReport()

        doc_files = _find_doc_files(project_root, files)

        total_links = 0
        valid_links = 0
        all_broken: list[BrokenLink] = []

        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            total, valid, broken = _check_file_links(doc_file, project_root, content)
            total_links += total
            valid_links += valid
            all_broken.extend(broken)

        return LinkReport(
            total_links=total_links,
            valid_links=valid_links,
            broken_links=all_broken,
        )
