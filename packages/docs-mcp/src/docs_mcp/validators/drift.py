"""Drift detection: identify code changes not reflected in documentation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from docs_mcp.analyzers.api_surface import APISurface

logger = structlog.get_logger(__name__)

# Directories to skip when scanning for Python source files (extends shared constants).
from docs_mcp.constants import SKIP_DIRS as _BASE_SKIP_DIRS

_SKIP_DIRS: frozenset[str] = _BASE_SKIP_DIRS | frozenset({".hg", ".svn", ".env"})

# Documentation file extensions to scan for references.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})


class DriftItem(BaseModel):
    """A single drift finding between code and documentation."""

    file_path: str
    drift_type: str  # "added_undocumented", "modified_undocumented", "removed_stale"
    severity: str = "warning"  # "warning", "error"
    description: str = ""
    code_last_modified: str = ""  # ISO date
    doc_last_modified: str = ""  # ISO date


class DriftReport(BaseModel):
    """Aggregated drift detection results."""

    total_items: int = 0
    items: list[DriftItem] = []
    drift_score: float = 0.0  # 0.0 (no drift) to 1.0 (severe drift)
    checked_files: int = 0


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if dirname in _SKIP_DIRS:
        return True
    return dirname.endswith(".egg-info")


def _iso_from_mtime(mtime: float) -> str:
    """Convert a file modification time to an ISO date string (UTC)."""
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))


def _find_python_files(project_root: Path) -> list[Path]:
    """Find all Python files under the project root."""
    py_files: list[Path] = []
    if not project_root.is_dir():
        return py_files

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        current = Path(dirpath)
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(current / fname)
    return py_files


def _find_doc_files(
    project_root: Path,
    doc_dirs: list[str] | None = None,
) -> list[Path]:
    """Find all documentation files under the project root or specified dirs."""
    doc_files: list[Path] = []

    if doc_dirs:
        # Only scan specified directories
        for ddir in doc_dirs:
            search_root = project_root / ddir
            if not search_root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(search_root):
                dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
                current = Path(dirpath)
                for fname in filenames:
                    fpath = current / fname
                    if fpath.suffix.lower() in _DOC_EXTENSIONS:
                        doc_files.append(fpath)
    else:
        # Scan entire project for doc files (also grab root-level docs)
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


def _read_doc_content(doc_files: list[Path]) -> str:
    """Read and concatenate content from all documentation files."""
    parts: list[str] = []
    for fp in doc_files:
        try:
            parts.append(fp.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def _get_public_names(surface: APISurface) -> list[str]:
    """Extract public API names from an APISurface."""
    names: list[str] = []
    names.extend(f.name for f in surface.functions)
    names.extend(c.name for c in surface.classes)
    return names


class DriftDetector:
    """Detect documentation drift relative to code changes."""

    def check(
        self,
        project_root: Path,
        *,
        since: str | None = None,
        doc_dirs: list[str] | None = None,
    ) -> DriftReport:
        """Run drift detection.

        Args:
            project_root: Root of the project to scan.
            since: Unused for MVP (reserved for git ref/date filtering).
            doc_dirs: Optional list of directories containing docs.

        Returns:
            A DriftReport with drift findings.
        """
        if not project_root.is_dir():
            return DriftReport()

        py_files = _find_python_files(project_root)
        doc_files = _find_doc_files(project_root, doc_dirs)

        if not py_files:
            return DriftReport()

        # Read all doc content for reference checking
        doc_content_lower = _read_doc_content(doc_files).lower()

        # Get the most recent doc modification time (or 0 if no docs)
        doc_mtime: float = 0.0
        for df in doc_files:
            try:
                doc_mtime = max(doc_mtime, df.stat().st_mtime)
            except OSError:
                continue

        items: list[DriftItem] = []
        checked = 0

        from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

        analyzer = APISurfaceAnalyzer()

        for py_file in py_files:
            # Skip __init__.py with no significant content
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            stripped = content.strip()
            if not stripped or stripped == '""""""':
                continue

            checked += 1
            rel_path = str(py_file.relative_to(project_root)).replace("\\", "/")

            try:
                code_mtime = py_file.stat().st_mtime
            except OSError:
                continue

            code_iso = _iso_from_mtime(code_mtime)
            doc_iso = _iso_from_mtime(doc_mtime) if doc_mtime > 0 else ""

            # Analyze public API
            surface = analyzer.analyze(py_file, project_root=project_root)
            public_names = _get_public_names(surface)

            if not public_names:
                continue

            # Check if the module name is mentioned in docs
            py_file.stem.lower()

            # Check each public name against doc content
            undocumented: list[str] = []
            for name in public_names:
                if name.lower() not in doc_content_lower:
                    undocumented.append(name)

            if undocumented:
                # Determine severity: if code is newer than docs, it's more urgent
                severity = "warning"
                if doc_mtime > 0 and code_mtime > doc_mtime:
                    severity = "error"

                drift_type = "added_undocumented"
                if doc_mtime > 0 and code_mtime > doc_mtime:
                    drift_type = "modified_undocumented"

                items.append(
                    DriftItem(
                        file_path=rel_path,
                        drift_type=drift_type,
                        severity=severity,
                        description=(
                            f"Public names not found in docs: {', '.join(undocumented[:5])}"
                            + (f" (+{len(undocumented) - 5} more)" if len(undocumented) > 5 else "")
                        ),
                        code_last_modified=code_iso,
                        doc_last_modified=doc_iso,
                    )
                )

        # Calculate drift score
        drift_score = len(items) / checked if checked > 0 else 0.0
        drift_score = min(drift_score, 1.0)

        return DriftReport(
            total_items=len(items),
            items=items,
            drift_score=round(drift_score, 3),
            checked_files=checked,
        )
