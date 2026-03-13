"""Cross-reference validator for documentation files (Epic 85.4).

Validates that cross-references between documentation files are
consistent and bidirectional. Detects orphan docs, missing backlinks,
and broken inter-doc references.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]

# Directories to skip when scanning.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".env", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", ".tapps-mcp",
})

# Documentation file extensions.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# Markdown link pattern: [text](target)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


class CrossRefIssue(BaseModel):
    """A single cross-reference issue."""

    source_file: str
    issue_type: str  # orphan, broken_ref, missing_backlink
    target: str = ""
    message: str


class CrossRefReport(BaseModel):
    """Result of cross-reference validation."""

    issues: list[CrossRefIssue]
    total_files: int
    total_refs: int
    orphan_count: int
    broken_count: int
    missing_backlink_count: int
    score: int  # 0-100


class CrossRefValidator:
    """Validates cross-references between documentation files.

    Checks for:
    - Orphan documents (not linked from any other doc)
    - Broken references (links to non-existent files)
    - Missing backlinks (A links to B but B doesn't link back)
    """

    # Files that are allowed to be orphans (typically entry points)
    _ENTRY_POINT_NAMES: ClassVar[frozenset[str]] = frozenset({
        "readme", "index", "changelog", "license", "contributing",
        "code_of_conduct", "security", "agents", "claude",
    })

    def validate(
        self,
        project_root: Path,
        *,
        doc_dirs: list[str] | None = None,
        check_backlinks: bool = True,
    ) -> CrossRefReport:
        """Validate cross-references in documentation.

        Args:
            project_root: Root directory of the project.
            doc_dirs: Optional list of directories to scan.
            check_backlinks: Whether to check for missing backlinks.

        Returns:
            CrossRefReport with issues found.
        """
        if not project_root.is_dir():
            return CrossRefReport(
                issues=[], total_files=0, total_refs=0,
                orphan_count=0, broken_count=0,
                missing_backlink_count=0, score=100,
            )

        # Collect all doc files
        doc_files: set[str] = set()
        if doc_dirs:
            for d in doc_dirs:
                dir_path = project_root / d
                if dir_path.is_dir():
                    self._collect_docs(project_root, dir_path, doc_files)
        else:
            self._collect_docs(project_root, project_root, doc_files)
            # Also pick up root-level docs
            for f in project_root.iterdir():
                if f.is_file() and f.suffix.lower() in _DOC_EXTENSIONS:
                    rel = str(f.relative_to(project_root)).replace("\\", "/")
                    doc_files.add(rel)

        if not doc_files:
            return CrossRefReport(
                issues=[], total_files=0, total_refs=0,
                orphan_count=0, broken_count=0,
                missing_backlink_count=0, score=100,
            )

        # Build reference graph: source -> set of targets
        ref_graph: dict[str, set[str]] = {}
        total_refs = 0
        issues: list[CrossRefIssue] = []

        for rel_path in doc_files:
            abs_path = project_root / rel_path
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            refs = self._extract_refs(content, rel_path, project_root)
            ref_graph[rel_path] = set()

            for target in refs:
                total_refs += 1
                # Normalize target
                normalized = self._normalize_target(target, rel_path)
                if normalized is None:
                    continue  # External URL or anchor-only

                ref_graph[rel_path].add(normalized)

                # Check if target exists
                if normalized not in doc_files:
                    target_path = project_root / normalized
                    if not target_path.exists():
                        issues.append(CrossRefIssue(
                            source_file=rel_path,
                            issue_type="broken_ref",
                            target=normalized,
                            message=f"Reference to '{normalized}' but file does not exist",
                        ))

        # Check for orphans
        linked_files: set[str] = set()
        for targets in ref_graph.values():
            linked_files.update(targets)

        orphan_count = 0
        for rel_path in doc_files:
            if rel_path not in linked_files:
                stem = Path(rel_path).stem.lower()
                if stem not in self._ENTRY_POINT_NAMES:
                    issues.append(CrossRefIssue(
                        source_file=rel_path,
                        issue_type="orphan",
                        message=f"'{rel_path}' is not linked from any other document",
                    ))
                    orphan_count += 1

        # Check for missing backlinks
        missing_backlink_count = 0
        if check_backlinks:
            for source, targets in ref_graph.items():
                for target in targets:
                    if target in ref_graph and source not in ref_graph.get(target, set()):
                        # Only flag if both are non-entry-point docs
                        source_stem = Path(source).stem.lower()
                        target_stem = Path(target).stem.lower()
                        if (
                            source_stem not in self._ENTRY_POINT_NAMES
                            and target_stem not in self._ENTRY_POINT_NAMES
                        ):
                            issues.append(CrossRefIssue(
                                source_file=source,
                                issue_type="missing_backlink",
                                target=target,
                                message=(
                                    f"'{source}' links to '{target}' but "
                                    f"'{target}' does not link back"
                                ),
                            ))
                            missing_backlink_count += 1

        broken_count = sum(1 for i in issues if i.issue_type == "broken_ref")

        # Calculate score
        score = self._calculate_score(
            len(doc_files), total_refs, orphan_count, broken_count, missing_backlink_count
        )

        return CrossRefReport(
            issues=issues,
            total_files=len(doc_files),
            total_refs=total_refs,
            orphan_count=orphan_count,
            broken_count=broken_count,
            missing_backlink_count=missing_backlink_count,
            score=score,
        )

    def _collect_docs(
        self, project_root: Path, scan_dir: Path, doc_files: set[str]
    ) -> None:
        """Recursively collect documentation files."""
        try:
            for item in scan_dir.iterdir():
                if item.is_dir():
                    if item.name in _SKIP_DIRS or item.name.startswith("."):
                        continue
                    self._collect_docs(project_root, item, doc_files)
                elif item.is_file() and item.suffix.lower() in _DOC_EXTENSIONS:
                    rel = str(item.relative_to(project_root)).replace("\\", "/")
                    doc_files.add(rel)
        except PermissionError:
            pass

    def _extract_refs(
        self, content: str, source_path: str, project_root: Path
    ) -> list[str]:
        """Extract documentation references from content."""
        refs: list[str] = []
        in_code_block = False
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            for match in _LINK_RE.finditer(line):
                target = match.group(2)
                # Skip external URLs, images, anchors-only
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                # Strip anchor
                target = target.split("#")[0]
                if target:
                    refs.append(target)
        return refs

    def _normalize_target(self, target: str, source_path: str) -> str | None:
        """Normalize a reference target to a project-relative path."""
        if target.startswith(("http://", "https://", "mailto:")):
            return None
        if target.startswith("#"):
            return None

        # Strip anchor
        target = target.split("#")[0]
        if not target:
            return None

        # Resolve relative path against source directory
        source_dir = str(Path(source_path).parent).replace("\\", "/")
        if source_dir == ".":
            resolved = target
        else:
            resolved = f"{source_dir}/{target}"

        # Normalize path components (handle ../ etc.)
        parts: list[str] = []
        for part in resolved.replace("\\", "/").split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)

        return "/".join(parts) if parts else None

    def _calculate_score(
        self,
        total_files: int,
        total_refs: int,
        orphan_count: int,
        broken_count: int,
        missing_backlink_count: int,
    ) -> int:
        """Calculate a cross-reference health score (0-100)."""
        if total_files == 0:
            return 100

        score = 100.0

        # Broken refs are the worst (-15 each, capped at 60)
        score -= min(broken_count * 15, 60)

        # Orphans are moderate (-5 each, capped at 25)
        orphan_ratio = orphan_count / total_files if total_files > 0 else 0
        score -= min(orphan_ratio * 50, 25)

        # Missing backlinks are minor (-2 each, capped at 15)
        score -= min(missing_backlink_count * 2, 15)

        return max(0, min(100, int(score)))
