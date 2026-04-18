"""Cross-reference validator for documentation files (Epic 85.4).

Validates that cross-references between documentation files are
consistent and bidirectional. Detects orphan docs, missing backlinks,
and broken inter-doc references.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
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

# Documentation file extensions.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# Markdown link pattern: [text](target)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Minimum number of broken refs sharing a prefix to surface as a pattern.
_MIN_PATTERN_COUNT: int = 5

# Maximum samples kept per group / pattern (keeps responses compact).
_MAX_SAMPLES: int = 5


class CrossRefIssue(BaseModel):
    """A single cross-reference issue."""

    source_file: str
    issue_type: str  # orphan, broken_ref, missing_backlink
    target: str = ""
    message: str


class CrossRefGroup(BaseModel):
    """Broken cross-refs grouped by source file.

    Surfaces the "one file with many broken refs" concentration pattern
    so users see the problem is localized, not systemic.
    """

    source_file: str
    broken_count: int
    sample_targets: list[str]


class CrossRefPattern(BaseModel):
    """A common-prefix pattern detected across broken refs.

    When many broken refs share the same path prefix (e.g. a generated
    index used the wrong base path), this surfaces the shared prefix so
    users can fix all broken refs at once.
    """

    prefix: str
    example_targets: list[str]
    count: int


class CrossRefReport(BaseModel):
    """Result of cross-reference validation."""

    issues: list[CrossRefIssue]
    groups: list[CrossRefGroup]
    patterns: list[CrossRefPattern]
    total_files: int
    total_refs: int
    orphan_count: int
    broken_count: int
    missing_backlink_count: int
    score: int  # 0-100, per-file-mean scoring
    legacy_score: int  # 0-100, old per-total-ref scoring (for calibration)
    scoring_method: str  # always "per_file_mean" for the new score


class CrossRefValidator:
    """Validates cross-references between documentation files.

    Checks for:
    - Orphan documents (not linked from any other doc)
    - Broken references (links to non-existent files)
    - Missing backlinks (A links to B but B doesn't link back)
    """

    # Files that are allowed to be orphans (typically entry points)
    _ENTRY_POINT_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "readme",
            "index",
            "changelog",
            "license",
            "contributing",
            "code_of_conduct",
            "security",
            "agents",
            "claude",
        }
    )

    def validate(
        self,
        project_root: Path,
        *,
        doc_dirs: list[str] | None = None,
        check_backlinks: bool = True,
        group_by_source: bool = False,
    ) -> CrossRefReport:
        """Validate cross-references in documentation.

        Args:
            project_root: Root directory of the project.
            doc_dirs: Optional list of directories to scan.
            check_backlinks: Whether to check for missing backlinks.
            group_by_source: When True, omits the flat ``issues`` list in the
                response and returns grouped/pattern data only. Significantly
                reduces response size for projects with many broken refs.

        Returns:
            CrossRefReport with issues found.
        """
        if not project_root.is_dir():
            return self._empty_report()

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
            return self._empty_report()

        ref_graph, total_refs, issues, per_file_refs, per_file_broken = self._build_ref_graph(
            doc_files,
            project_root,
        )

        orphan_count = self._find_orphans(doc_files, ref_graph, issues)

        missing_backlink_count = 0
        if check_backlinks:
            missing_backlink_count = self._find_missing_backlinks(ref_graph, issues)

        broken_count = sum(1 for i in issues if i.issue_type == "broken_ref")

        groups = self._build_groups(issues)
        patterns = self._detect_patterns(issues)

        score = self._calculate_per_file_mean_score(
            per_file_refs,
            per_file_broken,
            orphan_count,
            len(doc_files),
            missing_backlink_count,
        )
        legacy_score = self._calculate_legacy_score(
            len(doc_files), orphan_count, broken_count, missing_backlink_count
        )

        return CrossRefReport(
            issues=[] if group_by_source else issues,
            groups=groups,
            patterns=patterns,
            total_files=len(doc_files),
            total_refs=total_refs,
            orphan_count=orphan_count,
            broken_count=broken_count,
            missing_backlink_count=missing_backlink_count,
            score=score,
            legacy_score=legacy_score,
            scoring_method="per_file_mean",
        )

    def _empty_report(self) -> CrossRefReport:
        return CrossRefReport(
            issues=[],
            groups=[],
            patterns=[],
            total_files=0,
            total_refs=0,
            orphan_count=0,
            broken_count=0,
            missing_backlink_count=0,
            score=100,
            legacy_score=100,
            scoring_method="per_file_mean",
        )

    def _build_ref_graph(
        self,
        doc_files: set[str],
        project_root: Path,
    ) -> tuple[
        dict[str, set[str]],
        int,
        list[CrossRefIssue],
        dict[str, int],
        dict[str, int],
    ]:
        """Build reference graph and detect broken refs.

        Returns:
            ``(graph, total_refs, issues, per_file_refs, per_file_broken)``
            where ``per_file_refs`` counts project-internal resolved refs per
            source file and ``per_file_broken`` counts broken refs per source
            file.
        """
        ref_graph: dict[str, set[str]] = {}
        total_refs = 0
        issues: list[CrossRefIssue] = []
        per_file_refs: dict[str, int] = {}
        per_file_broken: dict[str, int] = {}

        for rel_path in doc_files:
            abs_path = project_root / rel_path
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            refs = self._extract_refs(content, rel_path, project_root)
            ref_graph[rel_path] = set()
            per_file_refs.setdefault(rel_path, 0)
            per_file_broken.setdefault(rel_path, 0)

            for target in refs:
                total_refs += 1
                normalized = self._normalize_target(target, rel_path)
                if normalized is None:
                    continue  # External URL or anchor-only

                ref_graph[rel_path].add(normalized)
                per_file_refs[rel_path] += 1

                if normalized not in doc_files:
                    target_path = project_root / normalized
                    if not target_path.exists():
                        issues.append(
                            CrossRefIssue(
                                source_file=rel_path,
                                issue_type="broken_ref",
                                target=normalized,
                                message=f"Reference to '{normalized}' but file does not exist",
                            )
                        )
                        per_file_broken[rel_path] += 1

        return ref_graph, total_refs, issues, per_file_refs, per_file_broken

    def _find_orphans(
        self,
        doc_files: set[str],
        ref_graph: dict[str, set[str]],
        issues: list[CrossRefIssue],
    ) -> int:
        """Find orphan documents (not linked from any other doc). Returns orphan count."""
        linked_files: set[str] = set()
        for targets in ref_graph.values():
            linked_files.update(targets)

        orphan_count = 0
        for rel_path in doc_files:
            if rel_path not in linked_files:
                stem = Path(rel_path).stem.lower()
                if stem not in self._ENTRY_POINT_NAMES:
                    issues.append(
                        CrossRefIssue(
                            source_file=rel_path,
                            issue_type="orphan",
                            message=f"'{rel_path}' is not linked from any other document",
                        )
                    )
                    orphan_count += 1
        return orphan_count

    def _find_missing_backlinks(
        self,
        ref_graph: dict[str, set[str]],
        issues: list[CrossRefIssue],
    ) -> int:
        """Find missing backlinks (A->B but B doesn't link back). Returns missing count."""
        missing_backlink_count = 0
        for source, targets in ref_graph.items():
            for target in targets:
                if target in ref_graph and source not in ref_graph.get(target, set()):
                    source_stem = Path(source).stem.lower()
                    target_stem = Path(target).stem.lower()
                    if (
                        source_stem not in self._ENTRY_POINT_NAMES
                        and target_stem not in self._ENTRY_POINT_NAMES
                    ):
                        issues.append(
                            CrossRefIssue(
                                source_file=source,
                                issue_type="missing_backlink",
                                target=target,
                                message=(
                                    f"'{source}' links to '{target}' but "
                                    f"'{target}' does not link back"
                                ),
                            )
                        )
                        missing_backlink_count += 1
        return missing_backlink_count

    def _build_groups(self, issues: list[CrossRefIssue]) -> list[CrossRefGroup]:
        """Group broken refs by source file, with most-frequent sample targets."""
        buckets: dict[str, list[str]] = {}
        for issue in issues:
            if issue.issue_type != "broken_ref":
                continue
            buckets.setdefault(issue.source_file, []).append(issue.target)

        groups: list[CrossRefGroup] = []
        for source_file, targets in buckets.items():
            counts = Counter(targets)
            samples = [t for t, _ in counts.most_common(_MAX_SAMPLES)]
            groups.append(
                CrossRefGroup(
                    source_file=source_file,
                    broken_count=len(targets),
                    sample_targets=samples,
                )
            )
        groups.sort(key=lambda g: g.broken_count, reverse=True)
        return groups

    def _detect_patterns(self, issues: list[CrossRefIssue]) -> list[CrossRefPattern]:
        """Detect common path prefixes across broken refs.

        For each broken-ref target, split on '/' and test progressively
        shorter prefixes. Emit the **longest** prefix that still covers at
        least ``_MIN_PATTERN_COUNT`` broken refs.
        """
        broken_targets = [i.target for i in issues if i.issue_type == "broken_ref" and i.target]
        if len(broken_targets) < _MIN_PATTERN_COUNT:
            return []

        # Count every prefix occurrence across all targets.
        prefix_counts: Counter[str] = Counter()
        prefix_examples: dict[str, list[str]] = {}
        for target in broken_targets:
            parts = target.split("/")
            # Only multi-segment targets can have a directory prefix.
            for depth in range(1, len(parts)):
                prefix = "/".join(parts[:depth])
                prefix_counts[prefix] += 1
                prefix_examples.setdefault(prefix, []).append(target)

        # Keep only prefixes that meet the threshold.
        candidates = {p: c for p, c in prefix_counts.items() if c >= _MIN_PATTERN_COUNT}
        if not candidates:
            return []

        # Pick the longest prefix per "prefix family" — we want the most
        # specific prefix that still covers >= threshold targets. A prefix is
        # only kept if no *longer* candidate fully covers it.
        sorted_by_len = sorted(candidates.items(), key=lambda kv: (-kv[0].count("/"), -kv[1]))
        selected: list[tuple[str, int]] = []
        for prefix, count in sorted_by_len:
            # Skip if this prefix is subsumed by an already-selected longer one
            # with the same count (i.e. shorter version of an existing pick).
            if any(s.startswith(prefix + "/") and sc == count for s, sc in selected):
                continue
            # Skip if a longer already-selected prefix renders this one
            # redundant (covers same targets).
            if any(s.startswith(prefix + "/") and sc >= _MIN_PATTERN_COUNT for s, sc in selected):
                continue
            selected.append((prefix, count))

        patterns: list[CrossRefPattern] = []
        for prefix, count in selected:
            examples = prefix_examples.get(prefix, [])
            # De-duplicate while preserving order, then cap.
            seen: set[str] = set()
            unique_examples: list[str] = []
            for ex in examples:
                if ex not in seen:
                    seen.add(ex)
                    unique_examples.append(ex)
                if len(unique_examples) >= _MAX_SAMPLES:
                    break
            patterns.append(
                CrossRefPattern(prefix=prefix, example_targets=unique_examples, count=count)
            )

        patterns.sort(key=lambda p: p.count, reverse=True)
        return patterns

    def _collect_docs(self, project_root: Path, scan_dir: Path, doc_files: set[str]) -> None:
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

    def _extract_refs(self, content: str, source_path: str, project_root: Path) -> list[str]:
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
        target = target.split("#", maxsplit=1)[0]
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

    def _calculate_per_file_mean_score(
        self,
        per_file_refs: dict[str, int],
        per_file_broken: dict[str, int],
        orphan_count: int,
        total_files: int,
        missing_backlink_count: int,
    ) -> int:
        """Score via mean of per-file broken ratios.

        Rationale: a single autogenerated file with 232/232 broken refs
        should contribute one file's worth to the mean — not 232 line-items
        that swamp the rest of the project.

        Formula:
          broken_penalty = mean(broken_i / refs_i) over files with refs_i > 0,
                           scaled to a 75-point penalty.
          orphan_penalty = min(orphan_ratio * 50, 25).
          backlink_penalty = min(missing_backlink_count * 2, 15).
          score = 100 - broken_penalty - orphan_penalty - backlink_penalty.

        The 75-point weight means even a 100%-broken single-file project
        drops into a 0-25 range (combined with the orphan penalty), which
        satisfies the "single file all broken => score 0" invariant.
        """
        if total_files == 0:
            return 100

        files_with_refs = [f for f, n in per_file_refs.items() if n > 0]

        score = 100.0

        if files_with_refs:
            ratios = [per_file_broken[f] / per_file_refs[f] for f in files_with_refs]
            mean_broken_ratio = sum(ratios) / len(ratios)
            score -= mean_broken_ratio * 75

        orphan_ratio = orphan_count / total_files if total_files > 0 else 0
        score -= min(orphan_ratio * 50, 25)

        score -= min(missing_backlink_count * 2, 15)

        return max(0, min(100, int(score)))

    def _calculate_legacy_score(
        self,
        total_files: int,
        orphan_count: int,
        broken_count: int,
        missing_backlink_count: int,
    ) -> int:
        """Legacy scoring: -15 per broken ref (capped at 60). Kept for calibration."""
        if total_files == 0:
            return 100

        score = 100.0
        score -= min(broken_count * 15, 60)
        orphan_ratio = orphan_count / total_files if total_files > 0 else 0
        score -= min(orphan_ratio * 50, 25)
        score -= min(missing_backlink_count * 2, 15)
        return max(0, min(100, int(score)))
