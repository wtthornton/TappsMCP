"""Internal link validator for documentation files."""

from __future__ import annotations

import os
import re
from pathlib import Path

import structlog
from pydantic import BaseModel

from docs_mcp.validators._scan_filters import matches_any_pattern

logger = structlog.get_logger(__name__)

# Regex for markdown links: [text](target)
# Captures link text (group 1) and target (group 2).
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Match `path/to/file.ext` or `file.ext` where ext is a known extension.
# Excludes triple-backtick (```) by using negative lookbehind/lookahead.
_BACKTICK_REF_RE = re.compile(
    r"(?<!`)`([^`\n]+\.(?:py|md|yaml|yml|toml|json|txt|rst|cfg|ini|sh|ts|js"
    r"|jsx|tsx|css|html))`(?!`)"
)

# Fenced code block delimiter (``` with optional language tag).
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

# Documentation file extensions to scan.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# Directories to skip.
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
        ".tapps-mcp-cache",
        ".claude",
        ".ralph",
    }
)


class BrokenLink(BaseModel):
    """A single broken link finding."""

    source_file: str
    line: int
    link_text: str
    link_target: str
    reason: str  # "file_not_found", "anchor_not_found", "invalid_path"


class BacktickReference(BaseModel):
    """A backtick-wrapped file reference found in documentation."""

    source_file: str
    line: int
    reference: str
    exists: bool
    reason: str  # "found", "not_found", "skipped_code_block"


class LinkReport(BaseModel):
    """Aggregated link check results."""

    total_links: int = 0
    valid_links: int = 0
    broken_links: list[BrokenLink] = []
    backtick_references: list[BacktickReference] = []
    total_backtick_refs: int = 0
    valid_backtick_refs: int = 0
    missing_backtick_refs: int = 0
    missing_backtick_ref_count: int = 0
    warnings: list[str] = []
    score: int = 100
    # Pagination / filtering metadata. These describe whether the detail lists
    # in this report were truncated by the caller-supplied ``max_items`` cap.
    truncated: bool = False
    total_available_broken_links: int = 0
    total_available_backtick_references: int = 0
    total_available_warnings: int = 0
    excluded_paths_count: int = 0


def _compute_score(
    total_links: int,
    valid_links: int,
    total_backtick_refs: int,
    valid_backtick_refs: int,
) -> int:
    """Compute a 0-100 link-health score.

    Treats markdown links and backtick refs as one combined pool. When there
    are no signals at all (no links, no refs) we return a perfect 100 --
    the caller already surfaces zero-link warnings separately.
    """
    denom = total_links + total_backtick_refs
    if denom == 0:
        return 100
    numer = valid_links + valid_backtick_refs
    return max(0, min(100, round((numer / denom) * 100)))


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
            # GitHub maps each space to a hyphen WITHOUT collapsing repeats,
            # so "Spacing & Layout" -> "spacing--layout" (after & is stripped).
            # Collapsing here would produce "spacing-layout" and falsely flag
            # the GitHub-style anchor as broken.
            slug = slug.replace(" ", "-")
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


def _find_fenced_blocks(content: str) -> set[int]:
    """Return set of 1-based line numbers that are inside fenced code blocks."""
    inside_fence = False
    fence_char = ""
    fence_len = 0
    fenced_lines: set[int] = set()

    for line_num, line in enumerate(content.splitlines(), start=1):
        m = _FENCE_RE.match(line)
        if m:
            delimiter = m.group(1)
            if not inside_fence:
                inside_fence = True
                fence_char = delimiter[0]
                fence_len = len(delimiter)
                fenced_lines.add(line_num)
                continue
            # Closing fence must use same char and at least same length
            if delimiter[0] == fence_char and len(delimiter) >= fence_len:
                fenced_lines.add(line_num)
                inside_fence = False
                continue
        if inside_fence:
            fenced_lines.add(line_num)

    return fenced_lines


def _check_backtick_refs(
    file_path: Path,
    project_root: Path,
    content: str,
    fenced_lines: set[int],
) -> list[BacktickReference]:
    """Find backtick-wrapped file references and check if they exist.

    Returns:
        List of BacktickReference results.
    """
    refs: list[BacktickReference] = []
    rel_source = str(file_path.relative_to(project_root)).replace("\\", "/")
    file_dir = file_path.parent

    for line_num, line in enumerate(content.splitlines(), start=1):
        if line_num in fenced_lines:
            # Record matches inside fenced blocks as skipped
            for match in _BACKTICK_REF_RE.finditer(line):
                refs.append(
                    BacktickReference(
                        source_file=rel_source,
                        line=line_num,
                        reference=match.group(1),
                        exists=False,
                        reason="skipped_code_block",
                    )
                )
            continue

        for match in _BACKTICK_REF_RE.finditer(line):
            ref_path = match.group(1)

            # Check relative to project root first, then file directory
            target_from_root = project_root / ref_path
            target_from_file = file_dir / ref_path

            if target_from_root.exists() or target_from_file.exists():
                refs.append(
                    BacktickReference(
                        source_file=rel_source,
                        line=line_num,
                        reference=ref_path,
                        exists=True,
                        reason="found",
                    )
                )
            else:
                refs.append(
                    BacktickReference(
                        source_file=rel_source,
                        line=line_num,
                        reference=ref_path,
                        exists=False,
                        reason="not_found",
                    )
                )

    return refs


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
                    broken.append(
                        BrokenLink(
                            source_file=rel_source,
                            line=line_num,
                            link_text=link_text,
                            link_target=link_target,
                            reason="anchor_not_found",
                        )
                    )
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
                broken.append(
                    BrokenLink(
                        source_file=rel_source,
                        line=line_num,
                        link_text=link_text,
                        link_target=link_target,
                        reason="invalid_path",
                    )
                )
                continue

            if not target_path.exists():
                broken.append(
                    BrokenLink(
                        source_file=rel_source,
                        line=line_num,
                        link_text=link_text,
                        link_target=link_target,
                        reason="file_not_found",
                    )
                )
                continue

            # File exists; if there's an anchor, do best-effort check
            if anchor_part and target_path.suffix.lower() in _DOC_EXTENSIONS:
                try:
                    target_content = target_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                    target_anchors = _extract_headings(target_content)
                    if anchor_part not in target_anchors:
                        broken.append(
                            BrokenLink(
                                source_file=rel_source,
                                line=line_num,
                                link_text=link_text,
                                link_target=link_target,
                                reason="anchor_not_found",
                            )
                        )
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
        summary_only: bool = False,
        max_items: int = 200,
        broken_only: bool = False,
        include_backtick_refs: bool = True,
        archive_paths: list[str] | None = None,
    ) -> LinkReport:
        """Run link validation.

        Args:
            project_root: Root of the project to scan.
            files: Optional list of specific files to check.
            summary_only: When True, omit all per-item detail lists and
                return scalar counts / score only. Default ``False``
                preserves the historical rich-list behavior.
            max_items: Cap on the number of detailed items returned in each
                list (``broken_links``, ``backtick_references``, ``warnings``).
                When a list is truncated, ``truncated=True`` is set and the
                corresponding ``total_available_*`` field reports the real
                pre-truncation count. Default ``200``.
            broken_only: When True, omit valid / OK entries from the detail
                lists -- only broken links, missing backtick refs, and
                warnings are returned. Scalar counts are unaffected.
            include_backtick_refs: When True (default), the backtick-ref
                items remain in ``backtick_references`` exactly as before
                -- this preserves the pre-pagination contract for existing
                dashboards. When False, ``backtick_references`` is emptied
                (but ``missing_backtick_ref_count`` is still populated so
                dashboards can track the signal).

        Returns:
            A LinkReport with valid/broken link counts and, by default,
            detailed per-item findings.
        """
        if not project_root.is_dir():
            return LinkReport()

        doc_files = _find_doc_files(project_root, files)

        excluded_count = 0
        if archive_paths:
            kept: list[Path] = []
            for f in doc_files:
                try:
                    rel = str(f.relative_to(project_root)).replace("\\", "/")
                except ValueError:
                    rel = str(f).replace("\\", "/")
                if matches_any_pattern(rel, archive_paths):
                    excluded_count += 1
                else:
                    kept.append(f)
            doc_files = kept

        total_links = 0
        valid_links = 0
        all_broken: list[BrokenLink] = []
        all_backtick_refs: list[BacktickReference] = []
        total_backtick = 0
        valid_backtick = 0
        missing_backtick = 0
        warnings: list[str] = []

        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            total, valid, broken = _check_file_links(doc_file, project_root, content)
            total_links += total
            valid_links += valid
            all_broken.extend(broken)

            # Check backtick file references
            fenced_lines = _find_fenced_blocks(content)
            bt_refs = _check_backtick_refs(
                doc_file,
                project_root,
                content,
                fenced_lines,
            )
            all_backtick_refs.extend(bt_refs)
            for ref in bt_refs:
                if ref.reason == "skipped_code_block":
                    continue
                total_backtick += 1
                if ref.exists:
                    valid_backtick += 1
                else:
                    missing_backtick += 1

            # Zero-link warning
            rel_name = str(
                doc_file.relative_to(project_root),
            ).replace("\\", "/")
            non_skipped_bt = sum(1 for r in bt_refs if r.reason != "skipped_code_block")
            if total == 0 and non_skipped_bt == 0:
                warnings.append(
                    f"No links or file references found in {rel_name}"
                    " -- consider adding cross-references."
                )

        score = _compute_score(
            total_links=total_links,
            valid_links=valid_links,
            total_backtick_refs=total_backtick,
            valid_backtick_refs=valid_backtick,
        )

        # Apply ``broken_only`` filter on the full detail lists before any
        # truncation so the ``total_available_*`` counters reflect the
        # post-filter universe the caller asked for.
        broken_for_output: list[BrokenLink] = all_broken
        backtick_for_output: list[BacktickReference] = all_backtick_refs
        warnings_for_output: list[str] = warnings
        if broken_only:
            # BrokenLink entries are all broken by construction; the filter
            # only prunes backtick refs that are OK / skipped.
            backtick_for_output = [
                r for r in all_backtick_refs if not r.exists and r.reason != "skipped_code_block"
            ]

        if not include_backtick_refs:
            backtick_for_output = []

        total_avail_broken = len(broken_for_output)
        total_avail_backtick = len(backtick_for_output)
        total_avail_warnings = len(warnings_for_output)

        truncated = False
        if summary_only:
            broken_for_output = []
            backtick_for_output = []
            warnings_for_output = []
        else:
            if len(broken_for_output) > max_items:
                broken_for_output = broken_for_output[:max_items]
                truncated = True
            if len(backtick_for_output) > max_items:
                backtick_for_output = backtick_for_output[:max_items]
                truncated = True
            if len(warnings_for_output) > max_items:
                warnings_for_output = warnings_for_output[:max_items]
                truncated = True

        return LinkReport(
            total_links=total_links,
            valid_links=valid_links,
            broken_links=broken_for_output,
            backtick_references=backtick_for_output,
            total_backtick_refs=total_backtick,
            valid_backtick_refs=valid_backtick,
            missing_backtick_refs=missing_backtick,
            missing_backtick_ref_count=missing_backtick,
            warnings=warnings_for_output,
            score=score,
            truncated=truncated,
            total_available_broken_links=total_avail_broken,
            total_available_backtick_references=total_avail_backtick,
            total_available_warnings=total_avail_warnings,
            excluded_paths_count=excluded_count,
        )
