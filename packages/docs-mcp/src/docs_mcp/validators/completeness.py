"""Documentation completeness checker."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from pydantic import BaseModel

from docs_mcp.validators._scan_filters import (
    load_gitignore_patterns,
    should_exclude,
)

logger = structlog.get_logger(__name__)


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


def _find_python_files(
    project_root: Path,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> list[Path]:
    """Find all Python files under ``project_root``.

    Applies baseline exclusions plus optional gitignore + caller-supplied
    glob patterns so vendored / build / venv paths don't pollute the
    coverage counts.
    """
    py_files: list[Path] = []
    if not project_root.is_dir():
        return py_files
    gi = list(gitignore_patterns) if gitignore_patterns else []
    extras = list(extra_exclude) if extra_exclude else []
    for dirpath, dirnames, filenames in os.walk(project_root):
        current = Path(dirpath)

        kept: list[str] = []
        for d in dirnames:
            dir_rel = str((current / d).relative_to(project_root)).replace("\\", "/")
            if should_exclude(dir_rel, gi, extras):
                continue
            kept.append(d)
        dirnames[:] = kept

        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = current / fname
            file_rel = str(fpath.relative_to(project_root)).replace("\\", "/")
            if should_exclude(file_rel, gi, extras):
                continue
            py_files.append(fpath)
    return py_files


def _find_in_subdirs(
    project_root: Path,
    filename: str,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> str | None:
    """Search for a file in immediate child directories (monorepo support).

    Returns the relative path (e.g. ``subdir/README.md``) if found.
    Skips subdirectories that match the exclude filters so vendored
    README files don't get counted as project essentials.
    """
    target_lower = filename.lower()
    gi = list(gitignore_patterns) if gitignore_patterns else []
    extras = list(extra_exclude) if extra_exclude else []
    try:
        for entry in project_root.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            dir_rel = entry.name
            if should_exclude(dir_rel, gi, extras):
                continue
            for child in entry.iterdir():
                if child.is_file() and child.name.lower() == target_lower:
                    child_rel = str(child.relative_to(project_root)).replace("\\", "/")
                    if should_exclude(child_rel, gi, extras):
                        continue
                    return child_rel
    except OSError:
        pass
    return None


def _check_essential_docs(
    project_root: Path,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> CompletenessCategory:
    """Check for essential documentation files (README.md, LICENSE).

    Also checks immediate subdirectories so that monorepo or
    subdirectory-organized projects are not incorrectly flagged.
    """
    essential = ["README.md", "LICENSE"]
    present: list[str] = []
    missing: list[str] = []

    for doc in essential:
        found = _file_exists_case_insensitive(project_root, doc)
        if found:
            present.append(found)
        else:
            # Check subdirectories for monorepo layouts
            subdir_found = _find_in_subdirs(
                project_root,
                doc,
                gitignore_patterns=gitignore_patterns,
                extra_exclude=extra_exclude,
            )
            if subdir_found:
                present.append(subdir_found)
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


_API_DOC_EXTS = frozenset({".md", ".rst"})


def _find_api_doc_file(
    project_root: Path,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> str | None:
    """Find a written API documentation file.

    Matches common filenames (``api.md``, ``API.md``, ``api-reference.md``,
    ``api_docs.md``, ``reference.md``) in the project root, ``docs/``, or one
    level under ``docs/`` (e.g. ``docs/api/reference.md``). This keeps the
    category in sync with ``docs_session_start`` which classifies any path
    containing "api" as ``api_docs``.
    """
    gi = list(gitignore_patterns) if gitignore_patterns else []
    extras = list(extra_exclude) if extra_exclude else []

    def matches(entry: Path) -> bool:
        if entry.suffix.lower() not in _API_DOC_EXTS:
            return False
        stem = entry.stem.lower()
        return stem.startswith("api") or stem in {"reference", "references"}

    def scan(directory: Path) -> str | None:
        try:
            for entry in directory.iterdir():
                if not entry.is_file() or not matches(entry):
                    continue
                rel = str(entry.relative_to(project_root)).replace("\\", "/")
                if should_exclude(rel, gi, extras):
                    continue
                return rel
        except OSError:
            pass
        return None

    if (found := scan(project_root)) is not None:
        return found

    docs_dir = project_root / "docs"
    if not docs_dir.is_dir():
        return None
    if (found := scan(docs_dir)) is not None:
        return found

    try:
        for sub in docs_dir.iterdir():
            if not sub.is_dir():
                continue
            sub_rel = str(sub.relative_to(project_root)).replace("\\", "/")
            if should_exclude(sub_rel, gi, extras):
                continue
            if (found := scan(sub)) is not None:
                return found
    except OSError:
        pass
    return None


def _check_api_documentation(
    project_root: Path,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> CompletenessCategory:
    """Check API documentation coverage.

    A written API reference file (e.g. ``docs/api-reference.md``) short-circuits
    the category to ``score=1.0`` — if the project has curated API docs, it
    should not be penalized for low Python docstring coverage. Otherwise,
    fall back to per-module docstring coverage via APISurfaceAnalyzer.
    """
    api_doc = _find_api_doc_file(
        project_root,
        gitignore_patterns=gitignore_patterns,
        extra_exclude=extra_exclude,
    )
    if api_doc is not None:
        return CompletenessCategory(
            name="api_documentation",
            score=1.0,
            present=[api_doc],
            missing=[],
            weight=2.0,
        )

    from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

    py_files = _find_python_files(
        project_root,
        gitignore_patterns=gitignore_patterns,
        extra_exclude=extra_exclude,
    )
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


def _check_inline_docs(
    project_root: Path,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> CompletenessCategory:
    """Check % of public functions/classes with docstrings."""
    from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

    py_files = _find_python_files(
        project_root,
        gitignore_patterns=gitignore_patterns,
        extra_exclude=extra_exclude,
    )
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

    # No public symbols = nothing to document = trivially complete
    score = total_documented / total_public if total_public > 0 else 1.0

    return CompletenessCategory(
        name="inline_docs",
        score=round(score, 3),
        present=documented_names,
        missing=undocumented_names,
        weight=1.0,
    )


def _check_project_docs(
    project_root: Path,
    *,
    gitignore_patterns: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> CompletenessCategory:
    """Check if a docs/ directory exists with content.

    Files under ``docs/`` that match the exclude filters (for example,
    a vendored ``docs/third-party/README.md`` covered by a gitignore or
    ``exclude=["docs/third-party/**"]``) are not counted.
    """
    docs_dir = project_root / "docs"
    present: list[str] = []
    missing: list[str] = []
    gi = list(gitignore_patterns) if gitignore_patterns else []
    extras = list(extra_exclude) if extra_exclude else []

    if docs_dir.is_dir():
        # Check if docs/ has any content files (including subdirectories)
        doc_extensions = {".md", ".rst", ".txt", ".html"}
        for entry in docs_dir.rglob("*"):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in doc_extensions:
                continue
            entry_rel = str(entry.relative_to(project_root)).replace("\\", "/")
            if should_exclude(entry_rel, gi, extras):
                continue
            present.append(entry_rel)

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

    def check(
        self,
        project_root: Path,
        *,
        exclude: list[str] | None = None,
        respect_gitignore: bool = True,
    ) -> CompletenessReport:
        """Run completeness check.

        Args:
            project_root: Root of the project to scan.
            exclude: Extra glob patterns to exclude when scanning
                Python files and ``docs/`` content. Applied on top of
                the baseline and gitignore. Example:
                ``["vendored/**/*", "third_party/**"]``.
            respect_gitignore: When True (default), honor the project's
                root-level ``.gitignore`` when walking. Pass False to
                restore pre-fix behavior.

        Returns:
            A CompletenessReport with per-category scores and recommendations.
        """
        if not project_root.is_dir():
            return CompletenessReport(
                recommendations=["Project root directory does not exist."],
            )

        gitignore_patterns = load_gitignore_patterns(project_root) if respect_gitignore else []
        extras = list(exclude) if exclude else []

        categories = [
            _check_essential_docs(
                project_root,
                gitignore_patterns=gitignore_patterns,
                extra_exclude=extras,
            ),
            _check_development_docs(project_root),
            _check_api_documentation(
                project_root,
                gitignore_patterns=gitignore_patterns,
                extra_exclude=extras,
            ),
            _check_inline_docs(
                project_root,
                gitignore_patterns=gitignore_patterns,
                extra_exclude=extras,
            ),
            _check_project_docs(
                project_root,
                gitignore_patterns=gitignore_patterns,
                extra_exclude=extras,
            ),
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
                    recommendations.append("Create a docs/ directory with project documentation.")

        return CompletenessReport(
            overall_score=round(overall_score, 1),
            categories=categories,
            recommendations=recommendations,
        )
