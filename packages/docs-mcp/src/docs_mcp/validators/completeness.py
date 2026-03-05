"""Documentation completeness checker."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# Directories to skip when scanning (extends shared constants).
from docs_mcp.constants import SKIP_DIRS as _BASE_SKIP_DIRS

_SKIP_DIRS: frozenset[str] = _BASE_SKIP_DIRS | frozenset({".hg", ".svn", ".env"})


class CompletenessCategory(BaseModel):
    """A single category in the completeness report."""

    name: str
    score: float = 0.0  # 0.0-1.0
    present: list[str] = []
    missing: list[str] = []
    weight: float = 1.0


class CompletenessReport(BaseModel):
    """Aggregated completeness check results."""

    overall_score: float = 0.0  # Weighted average 0-100
    categories: list[CompletenessCategory] = []
    recommendations: list[str] = []


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if dirname in _SKIP_DIRS:
        return True
    return dirname.endswith(".egg-info")


def _file_exists_case_insensitive(project_root: Path, filename: str) -> str | None:
    """Check if a file exists (case-insensitive) in the project root.

    Returns the actual filename if found, or None.
    """
    target_lower = filename.lower()
    target_stem = target_lower.rsplit(".", 1)[0] if "." in target_lower else target_lower
    try:
        for entry in project_root.iterdir():
            if not entry.is_file():
                continue
            name_lower = entry.name.lower()
            if name_lower == target_lower:
                return entry.name
            # Also match without extension (e.g., LICENSE vs LICENSE.md)
            entry_stem = name_lower.rsplit(".", 1)[0] if "." in name_lower else name_lower
            if entry_stem == target_stem:
                return entry.name
    except OSError:
        pass
    return None


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


def _check_essential_docs(project_root: Path) -> CompletenessCategory:
    """Check for essential documentation files (README.md, LICENSE)."""
    essential = ["README.md", "LICENSE"]
    present: list[str] = []
    missing: list[str] = []

    for doc in essential:
        found = _file_exists_case_insensitive(project_root, doc)
        if found:
            present.append(found)
        else:
            missing.append(doc)

    score = len(present) / len(essential) if essential else 0.0

    return CompletenessCategory(
        name="essential_docs",
        score=round(score, 3),
        present=present,
        missing=missing,
        weight=3.0,
    )


def _check_development_docs(project_root: Path) -> CompletenessCategory:
    """Check for development documentation files (CONTRIBUTING.md, CHANGELOG.md)."""
    dev_docs = ["CONTRIBUTING.md", "CHANGELOG.md"]
    present: list[str] = []
    missing: list[str] = []

    for doc in dev_docs:
        found = _file_exists_case_insensitive(project_root, doc)
        if found:
            present.append(found)
        else:
            missing.append(doc)

    score = len(present) / len(dev_docs) if dev_docs else 0.0

    return CompletenessCategory(
        name="development_docs",
        score=round(score, 3),
        present=present,
        missing=missing,
        weight=2.0,
    )


def _check_api_documentation(project_root: Path) -> CompletenessCategory:
    """Check % of public modules with docstrings using APISurfaceAnalyzer."""
    from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

    py_files = _find_python_files(project_root)
    if not py_files:
        return CompletenessCategory(
            name="api_documentation",
            score=0.0,
            weight=2.0,
        )

    analyzer = APISurfaceAnalyzer()
    documented_modules: list[str] = []
    undocumented_modules: list[str] = []

    for py_file in py_files:
        # Skip test files and __init__.py with no content
        rel_path = str(py_file.relative_to(project_root)).replace("\\", "/")
        if "test" in rel_path.lower():
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue

        if not content:
            continue

        surface = analyzer.analyze(py_file, project_root=project_root)
        if surface.total_public == 0:
            continue

        if surface.coverage >= 0.5:
            documented_modules.append(rel_path)
        else:
            undocumented_modules.append(rel_path)

    total = len(documented_modules) + len(undocumented_modules)
    score = len(documented_modules) / total if total > 0 else 0.0

    return CompletenessCategory(
        name="api_documentation",
        score=round(score, 3),
        present=documented_modules,
        missing=undocumented_modules,
        weight=2.0,
    )


def _check_inline_docs(project_root: Path) -> CompletenessCategory:
    """Check % of public functions/classes with docstrings."""
    from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

    py_files = _find_python_files(project_root)
    if not py_files:
        return CompletenessCategory(
            name="inline_docs",
            score=0.0,
            weight=1.0,
        )

    analyzer = APISurfaceAnalyzer()
    total_public = 0
    total_documented = 0
    documented_names: list[str] = []
    undocumented_names: list[str] = []

    for py_file in py_files:
        rel_path = str(py_file.relative_to(project_root)).replace("\\", "/")
        if "test" in rel_path.lower():
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue

        if not content:
            continue

        surface = analyzer.analyze(py_file, project_root=project_root)

        for func in surface.functions:
            total_public += 1
            if func.docstring_present:
                total_documented += 1
                documented_names.append(f"{rel_path}:{func.name}")
            else:
                undocumented_names.append(f"{rel_path}:{func.name}")

        for cls in surface.classes:
            total_public += 1
            if cls.docstring_present:
                total_documented += 1
                documented_names.append(f"{rel_path}:{cls.name}")
            else:
                undocumented_names.append(f"{rel_path}:{cls.name}")

    score = total_documented / total_public if total_public > 0 else 0.0

    return CompletenessCategory(
        name="inline_docs",
        score=round(score, 3),
        present=documented_names,
        missing=undocumented_names,
        weight=1.0,
    )


def _check_project_docs(project_root: Path) -> CompletenessCategory:
    """Check if a docs/ directory exists with content."""
    docs_dir = project_root / "docs"
    present: list[str] = []
    missing: list[str] = []

    if docs_dir.is_dir():
        # Check if docs/ has any content files
        doc_extensions = {".md", ".rst", ".txt", ".html"}
        for entry in docs_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in doc_extensions:
                present.append(str(entry.relative_to(project_root)).replace("\\", "/"))

    if not present:
        missing.append("docs/")

    score = 1.0 if present else 0.0

    return CompletenessCategory(
        name="project_docs",
        score=score,
        present=present,
        missing=missing,
        weight=1.0,
    )


class CompletenessChecker:
    """Check documentation completeness across multiple categories."""

    def check(self, project_root: Path) -> CompletenessReport:
        """Run completeness check.

        Args:
            project_root: Root of the project to scan.

        Returns:
            A CompletenessReport with per-category scores and recommendations.
        """
        if not project_root.is_dir():
            return CompletenessReport(
                recommendations=["Project root directory does not exist."],
            )

        categories = [
            _check_essential_docs(project_root),
            _check_development_docs(project_root),
            _check_api_documentation(project_root),
            _check_inline_docs(project_root),
            _check_project_docs(project_root),
        ]

        # Calculate weighted average
        total_weight = sum(c.weight for c in categories)
        if total_weight > 0:
            weighted_sum = sum(c.score * c.weight for c in categories)
            overall_score = (weighted_sum / total_weight) * 100
        else:
            overall_score = 0.0

        # Build recommendations
        recommendations: list[str] = []
        for cat in categories:
            if cat.missing:
                if cat.name == "essential_docs":
                    for m in cat.missing:
                        recommendations.append(f"Add essential document: {m}")
                elif cat.name == "development_docs":
                    for m in cat.missing:
                        recommendations.append(f"Add development document: {m}")
                elif cat.name == "api_documentation":
                    count = len(cat.missing)
                    if count > 0:
                        recommendations.append(
                            f"{count} module(s) have less than 50% API documentation coverage."
                        )
                elif cat.name == "inline_docs":
                    count = len(cat.missing)
                    if count > 0:
                        recommendations.append(
                            f"{count} public function(s)/class(es) are missing docstrings."
                        )
                elif cat.name == "project_docs":
                    recommendations.append(
                        "Create a docs/ directory with project documentation."
                    )

        return CompletenessReport(
            overall_score=round(overall_score, 1),
            categories=categories,
            recommendations=recommendations,
        )
