"""Epic markdown structural validation for ``tapps_checklist``.

Parses an epic document, extracts its stories, and reports structural
findings (missing sections, point/size mismatches, dependency cycles,
uncovered files). Split out of ``checklist.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from tapps_mcp.tools.checklist_models import ChecklistResult

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Epic validation models
# ---------------------------------------------------------------------------

# Valid point ranges per size label
_SIZE_POINT_RANGES: dict[str, tuple[int, int]] = {
    "S": (1, 2),
    "M": (3, 5),
    "L": (8, 13),
}


class EpicStoryInfo(BaseModel):
    """Parsed information about a single story in an epic."""

    story_id: str = Field(description="Story identifier (e.g. '1.1').")
    title: str = Field(default="", description="Story title text.")
    points: int | None = Field(default=None, description="Story points.")
    size: str | None = Field(default=None, description="Size label (S/M/L).")
    priority: str | None = Field(default=None, description="Priority (P0-P4).")
    files: list[str] = Field(default_factory=list, description="Files listed.")
    has_acceptance_criteria: bool = Field(default=False, description="Whether AC section exists.")
    has_tasks: bool = Field(default=False, description="Whether Tasks section exists.")
    linked_file: str | None = Field(
        default=None, description="File path from a markdown link in the heading or table row."
    )


class EpicFinding(BaseModel):
    """A single validation finding for an epic document."""

    severity: str = Field(description="'error' or 'warning'.")
    message: str = Field(description="Human-readable finding description.")
    story_id: str | None = Field(default=None, description="Story ID if finding is story-specific.")


class CrossFileSummary(BaseModel):
    """Aggregate completeness metrics from linked story files."""

    total_stories: int = Field(default=0, description="Stories with linked files.")
    stories_with_files: int = Field(default=0, description="Stories that have linked files.")
    files_found: int = Field(default=0, description="Linked files that exist on disk.")
    files_missing: int = Field(default=0, description="Linked files not found.")
    with_acceptance_criteria: int = Field(
        default=0, description="Stories whose linked file has an AC section."
    )
    with_tasks: int = Field(default=0, description="Stories whose linked file has a Tasks section.")
    with_definition_of_done: int = Field(
        default=0, description="Stories whose linked file has a DoD section."
    )
    summary: str = Field(default="", description="Human-readable summary line.")


class EpicValidation(BaseModel):
    """Result of structural validation of an epic markdown file."""

    sections_found: list[str] = Field(default_factory=list, description="Top-level sections found.")
    stories: list[EpicStoryInfo] = Field(default_factory=list, description="Parsed stories.")
    files_affected_entries: list[str] = Field(
        default_factory=list,
        description="Files listed in a files-affected table.",
    )
    findings: list[EpicFinding] = Field(default_factory=list, description="Validation findings.")
    valid: bool = Field(
        default=True,
        description="True when no error-severity findings exist.",
    )
    cross_file_summary: CrossFileSummary | None = Field(
        default=None,
        description="Cross-file story completeness metrics (when linked files are validated).",
    )


class EpicChecklistResult(ChecklistResult):
    """Extended checklist result with epic-specific validation."""

    epic_validation: EpicValidation | None = Field(
        default=None,
        description="Epic structural validation (present when file_path provided).",
    )


# ---------------------------------------------------------------------------
# Epic markdown parsing
# ---------------------------------------------------------------------------

# Regex for story headings: "### Story X.Y: Title" or "### X.Y — Title"
_STORY_HEADING_RE = re.compile(
    r"^###\s+(?:Story\s+)?(\d+\.\d+)\s*[:\u2014-]\s*(.*)",
    re.MULTILINE,
)

# Linked heading: "### [X.Y](path) -- Title"
_LINKED_HEADING_RE = re.compile(
    r"^###\s+\[(\d+\.\d+)\]\(([^)]+)\)\s*[:\u2014-]+\s*(.*)",
    re.MULTILINE,
)

# Table-linked story: "| ID | [Title](file.md) | ... |"
_TABLE_STORY_RE = re.compile(
    r"^\|\s*(\S+)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|(.*)$",
    re.MULTILINE,
)

# Points pattern: "**Points:** N" or "Points: N"
_POINTS_RE = re.compile(r"\*{0,2}Points:?\*{0,2}:?\s*(\d+)", re.IGNORECASE)

# Size pattern: "**Size:** S" or "Size: M"
_SIZE_RE = re.compile(r"\*{0,2}Size:?\*{0,2}:?\s*([SML])\b", re.IGNORECASE)

# Priority pattern: "**Priority:** P1" or "Priority: P2"
_PRIORITY_RE = re.compile(r"\*{0,2}Priority:?\*{0,2}:?\s*(P\d)\b", re.IGNORECASE)

# Files pattern: lines starting with "- `path`" in a Files section
_FILE_ENTRY_RE = re.compile(r"^-\s+`([^`]+)`", re.MULTILINE)

# Table row for files-affected: "| `path` | ..."
_FILES_TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`", re.MULTILINE)


def _parse_table_size_priority(remaining_cols: str) -> tuple[str | None, str | None]:
    """Extract size and priority from remaining table columns.

    Args:
        remaining_cols: The portion of the table row after the link column.

    Returns:
        Tuple of (size, priority) — each may be None.
    """
    cells = [c.strip() for c in remaining_cols.split("|") if c.strip()]
    size: str | None = None
    priority: str | None = None
    size_re = re.compile(r"^(XS|XL|S|M|L)$", re.IGNORECASE)
    prio_re = re.compile(r"^(P[0-4])$", re.IGNORECASE)
    for cell in cells:
        if not size and size_re.match(cell):
            size = cell.upper()
        elif not priority and prio_re.match(cell):
            priority = cell.upper()
    return size, priority


def _block_between(content: str, matches: list[re.Match[str]], i: int) -> str:
    """Text from the end of match *i* to the start of the next one (or EOF)."""
    start = matches[i].end()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
    return content[start:end]


def _story_metadata(block: str) -> dict[str, Any]:
    """Points / size / priority / files / subsection flags for one story block."""
    points_m = _POINTS_RE.search(block)
    size_m = _SIZE_RE.search(block)
    priority_m = _PRIORITY_RE.search(block)
    return {
        "points": int(points_m.group(1)) if points_m else None,
        "size": size_m.group(1).upper() if size_m else None,
        "priority": priority_m.group(1).upper() if priority_m else None,
        "files": _extract_story_files(block),
        "has_acceptance_criteria": _has_subsection(block, "acceptance criteria"),
        "has_tasks": _has_subsection(block, "tasks"),
    }


def _parse_classic_stories(content: str) -> list[EpicStoryInfo]:
    """Stories written as classic ``### Story X.Y: Title`` headings."""
    matches = list(_STORY_HEADING_RE.finditer(content))
    return [
        EpicStoryInfo(
            story_id=m.group(1),
            title=m.group(2).strip(),
            **_story_metadata(_block_between(content, matches, i)),
        )
        for i, m in enumerate(matches)
    ]


def _parse_linked_stories(content: str, existing_ids: set[str]) -> list[EpicStoryInfo]:
    """Stories written as ``### [X.Y](path) -- Title`` linked headings.

    *existing_ids* is both an input filter and a running dedupe set: ids
    already captured by another parser are skipped.
    """
    matches = list(_LINKED_HEADING_RE.finditer(content))
    stories: list[EpicStoryInfo] = []
    for i, m in enumerate(matches):
        story_id = m.group(1)
        if story_id in existing_ids:
            continue
        stories.append(
            EpicStoryInfo(
                story_id=story_id,
                title=m.group(3).strip(),
                linked_file=m.group(2).strip(),
                **_story_metadata(_block_between(content, matches, i)),
            )
        )
        existing_ids.add(story_id)
    return stories


def _parse_table_stories(content: str) -> list[EpicStoryInfo]:
    """Stories written as rows of a stories table."""
    stories: list[EpicStoryInfo] = []
    for m in _TABLE_STORY_RE.finditer(content):
        size, priority = _parse_table_size_priority(m.group(4))
        stories.append(
            EpicStoryInfo(
                story_id=m.group(1),
                title=m.group(2).strip(),
                linked_file=m.group(3).strip(),
                size=size,
                priority=priority,
            )
        )
    return stories


def _parse_epic_markdown(
    content: str,
) -> tuple[
    list[str],
    list[EpicStoryInfo],
    list[str],
]:
    """Parse an epic markdown file and extract structural information.

    Three story notations are supported, tried in order: classic headings,
    linked headings, and — only when neither matched — a stories table.

    Returns:
        Tuple of (section_headings, stories, files_affected_entries).
    """
    sections = re.findall(r"^##\s+(.+)", content, re.MULTILINE)
    section_names = [s.strip() for s in sections]

    stories = _parse_classic_stories(content)
    stories.extend(_parse_linked_stories(content, {s.story_id for s in stories}))
    if not stories:
        stories = _parse_table_stories(content)

    return section_names, stories, _extract_files_affected(content)


def _extract_story_files(block: str) -> list[str]:
    """Extract file paths from a story block's Files section."""
    # Find "**Files:**" or "#### Files" section
    files_match = re.search(
        r"(?:\*\*Files:?\*\*|####\s+Files)\s*\n((?:\s*-\s+`[^`]+`.*\n?)+)",
        block,
        re.IGNORECASE,
    )
    if not files_match:
        return []
    files_text = files_match.group(1)
    return _FILE_ENTRY_RE.findall(files_text)


def _has_subsection(block: str, name: str) -> bool:
    """Check whether a block contains a sub-section with the given name."""
    pattern = re.compile(
        rf"(?:^####?\s+{re.escape(name)}|^\*\*{re.escape(name)}:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(pattern.search(block))


def _extract_files_affected(content: str) -> list[str]:
    """Extract file paths from a files-affected table."""
    # Look for a "Files Affected" or "Files-Affected" section
    section_match = re.search(
        r"(?:^##\s+Files[- ]Affected|^\*\*Files[- ]Affected:?\*\*)",
        content,
        re.IGNORECASE | re.MULTILINE,
    )
    if not section_match:
        return []
    start = section_match.end()
    # Find next section heading
    next_section = re.search(r"^##\s+", content[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(content)
    table_text = content[start:end]
    return _FILES_TABLE_ROW_RE.findall(table_text)


# ---------------------------------------------------------------------------
# Epic structural validation
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = {"Goal", "Acceptance Criteria", "Stories"}


def _check_required_sections(
    section_names: list[str],
    findings: list[EpicFinding],
) -> None:
    """Check that required top-level sections exist."""
    normalized = {s.lower().strip() for s in section_names}
    findings.extend(
        EpicFinding(
            severity="error",
            message=f"Missing required section: '{req}'",
        )
        for req in _REQUIRED_SECTIONS
        if req.lower() not in normalized
    )


def _check_story_completeness(
    stories: list[EpicStoryInfo],
    findings: list[EpicFinding],
) -> None:
    """Check each story for required sub-fields."""
    for story in stories:
        if story.points is None:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Points",
                    story_id=story.story_id,
                )
            )
        if story.size is None:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Size",
                    story_id=story.story_id,
                )
            )
        if story.priority is None:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Priority",
                    story_id=story.story_id,
                )
            )
        if not story.files:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Files list",
                    story_id=story.story_id,
                )
            )
        if not story.has_acceptance_criteria:
            findings.append(
                EpicFinding(
                    severity="error",
                    message=f"Story {story.story_id} missing Acceptance Criteria",
                    story_id=story.story_id,
                )
            )
        if not story.has_tasks:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Tasks",
                    story_id=story.story_id,
                )
            )


def _check_point_size_consistency(
    stories: list[EpicStoryInfo],
    findings: list[EpicFinding],
) -> None:
    """Flag stories where points don't match the expected range for the size."""
    for story in stories:
        if story.points is None or story.size is None:
            continue
        expected = _SIZE_POINT_RANGES.get(story.size)
        if expected is None:
            continue
        lo, hi = expected
        if not (lo <= story.points <= hi):
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=(
                        f"Story {story.story_id} size {story.size} "
                        f"expects {lo}-{hi} points but has {story.points}"
                    ),
                    story_id=story.story_id,
                )
            )


def _check_dependency_cycles(
    content: str,
    findings: list[EpicFinding],
) -> None:
    """Check for cycles in story dependency references.

    Looks for patterns like "Dependencies: Story X.Y" and builds
    a simple DAG to detect cycles.
    """
    dep_re = re.compile(
        r"(?:depends\s+on|dependencies?:?|requires)\s+(?:story\s+)?(\d+\.\d+)",
        re.IGNORECASE,
    )
    # Build adjacency from story blocks
    story_blocks = list(_STORY_HEADING_RE.finditer(content))
    graph: dict[str, list[str]] = {}

    for i, match in enumerate(story_blocks):
        story_id = match.group(1)
        start = match.end()
        end = story_blocks[i + 1].start() if i + 1 < len(story_blocks) else len(content)
        block = content[start:end]
        deps = dep_re.findall(block)
        if deps:
            graph[story_id] = deps

    # Simple cycle detection via DFS
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _dfs(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in graph.get(node, []):
            if _dfs(dep):
                return True
        in_stack.discard(node)
        return False

    for node in graph:
        if _dfs(node):
            findings.append(
                EpicFinding(
                    severity="error",
                    message=f"Dependency cycle detected involving story {node}",
                    story_id=node,
                )
            )
            break  # One cycle finding is sufficient


def _check_files_table_coverage(
    stories: list[EpicStoryInfo],
    files_affected: list[str],
    findings: list[EpicFinding],
) -> None:
    """Check that files in stories appear in the files-affected table."""
    if not files_affected:
        return  # No table present, skip check
    table_set = set(files_affected)
    for story in stories:
        findings.extend(
            EpicFinding(
                severity="warning",
                message=(
                    f"Story {story.story_id} references '{f}' not found in files-affected table"
                ),
                story_id=story.story_id,
            )
            for f in story.files
            if f not in table_set
        )


def _check_story_file_structure(
    content: str,
) -> tuple[bool, bool, bool, int | None, str | None]:
    """Check a story file for structural sections.

    Returns:
        Tuple of (has_ac, has_tasks, has_dod, points, size).
    """
    ac_re = re.compile(
        r"(?:^##?\s+Acceptance\s+Criteria|^\*\*Acceptance\s+Criteria:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    tasks_re = re.compile(
        r"(?:^##?\s+Tasks?\b|^\*\*Tasks?:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    dod_re = re.compile(
        r"(?:^##?\s+Definition\s+of\s+Done|^\*\*Definition\s+of\s+Done:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )

    has_ac = bool(ac_re.search(content))
    has_tasks = bool(tasks_re.search(content))
    has_dod = bool(dod_re.search(content))

    pm = _POINTS_RE.search(content)
    points = int(pm.group(1)) if pm else None

    sm = _SIZE_RE.search(content)
    size = sm.group(1).upper() if sm else None

    return has_ac, has_tasks, has_dod, points, size


def _load_linked_story(
    story: EpicStoryInfo,
    epic_dir: Path,
    epic_file_path: Path,
    seen_paths: set[str],
    findings: list[EpicFinding],
) -> tuple[str, str | None]:
    """Resolve and read one story's linked file.

    Returns ``(status, content)``. Status is ``skip`` (duplicate link or a
    self-reference — do not count it either way), ``missing`` (dangling
    link), ``unreadable`` (the file exists but could not be read, so it
    still counts as found), or ``ok``. Both failure statuses append a
    warning finding.
    """
    linked = story.linked_file
    if linked is None:  # pragma: no cover — filtered by the caller
        return "skip", None

    resolved = (epic_dir / linked).resolve()
    canonical = str(resolved)
    # Guard against circular/self references
    if canonical in seen_paths:
        return "skip", None
    seen_paths.add(canonical)
    if resolved == epic_file_path.resolve():
        return "skip", None

    if not resolved.is_file():
        findings.append(
            EpicFinding(
                severity="warning",
                message=f"Story {story.story_id} linked file not found: {linked}",
                story_id=story.story_id,
            )
        )
        return "missing", None

    try:
        return "ok", resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        findings.append(
            EpicFinding(
                severity="warning",
                message=f"Story {story.story_id} cannot read linked file: {linked}",
                story_id=story.story_id,
            )
        )
        return "unreadable", None


def _merge_linked_story_structure(
    story: EpicStoryInfo,
    content: str,
    findings: list[EpicFinding],
) -> tuple[bool, bool, bool]:
    """Fold a linked file's structure into *story*; the linked file wins.

    Returns (has_acceptance_criteria, has_tasks, has_definition_of_done)
    for the caller's counters.
    """
    has_ac, has_tasks_sec, has_dod, points, size = _check_story_file_structure(content)

    if has_ac:
        story.has_acceptance_criteria = True
    elif not story.has_acceptance_criteria:
        findings.append(
            EpicFinding(
                severity="info",
                message=(f"Story {story.story_id} linked file missing Acceptance Criteria"),
                story_id=story.story_id,
            )
        )

    if has_tasks_sec:
        story.has_tasks = True
    elif not story.has_tasks:
        findings.append(
            EpicFinding(
                severity="info",
                message=f"Story {story.story_id} linked file missing Tasks section",
                story_id=story.story_id,
            )
        )

    if points is not None and story.points is None:
        story.points = points
    if size is not None and story.size is None:
        story.size = size
    return has_ac, has_tasks_sec, has_dod


def _validate_linked_stories(
    stories: list[EpicStoryInfo],
    findings: list[EpicFinding],
    epic_file_path: Path,
) -> CrossFileSummary | None:
    """Follow linked story files and validate their structure.

    Args:
        stories: Parsed stories (may have ``linked_file`` set).
        findings: Findings list to append to.
        epic_file_path: Path to the epic file (links are resolved relative to its parent).

    Returns:
        A ``CrossFileSummary`` or ``None`` if no stories have linked files.
    """
    epic_dir = epic_file_path.parent
    stories_with_files = [s for s in stories if s.linked_file]

    if not stories_with_files:
        return None

    files_found = 0
    files_missing = 0
    with_ac = 0
    with_tasks = 0
    with_dod = 0
    seen_paths: set[str] = set()

    for story in stories_with_files:
        status, content = _load_linked_story(
            story, epic_dir, epic_file_path, seen_paths, findings
        )
        if status == "skip":
            continue
        if status == "missing":
            files_missing += 1
            continue

        files_found += 1
        if content is None:  # unreadable — counted as found, nothing to merge
            continue

        has_ac, has_tasks_sec, has_dod = _merge_linked_story_structure(story, content, findings)
        with_ac += int(has_ac)
        with_tasks += int(has_tasks_sec)
        with_dod += int(has_dod)

    total = len(stories_with_files)
    parts = [
        f"{total} stories",
        f"{files_found}/{total} files found",
        f"{with_ac}/{total} have AC",
        f"{with_tasks}/{total} have tasks",
    ]
    return CrossFileSummary(
        total_stories=total,
        stories_with_files=total,
        files_found=files_found,
        files_missing=files_missing,
        with_acceptance_criteria=with_ac,
        with_tasks=with_tasks,
        with_definition_of_done=with_dod,
        summary=", ".join(parts),
    )


def validate_epic_markdown(
    content: str,
    *,
    epic_file_path: Path | None = None,
    validate_linked_stories: bool = True,
) -> EpicValidation:
    """Validate an epic markdown document for structural completeness.

    Args:
        content: The epic markdown content.
        epic_file_path: Path to the epic file on disk.  Required for
            cross-file story validation (resolving linked story files).
        validate_linked_stories: When True and ``epic_file_path`` is given,
            follow linked story files and validate their structure.

    Returns an ``EpicValidation`` with all findings.
    """
    section_names, stories, files_affected = _parse_epic_markdown(content)
    findings: list[EpicFinding] = []

    _check_required_sections(section_names, findings)

    cross_file_summary: CrossFileSummary | None = None

    if not stories:
        findings.append(
            EpicFinding(
                severity="error",
                message=(
                    "No stories found (expected '### Story X.Y:', "
                    "'### [X.Y](path) --', or table-linked rows)"
                ),
            )
        )
    else:
        _check_story_completeness(stories, findings)
        _check_point_size_consistency(stories, findings)
        _check_files_table_coverage(stories, files_affected, findings)

        # Cross-file story validation
        if validate_linked_stories and epic_file_path is not None:
            cross_file_summary = _validate_linked_stories(
                stories,
                findings,
                epic_file_path,
            )

    _check_dependency_cycles(content, findings)

    has_errors = any(f.severity == "error" for f in findings)

    return EpicValidation(
        sections_found=section_names,
        stories=stories,
        files_affected_entries=files_affected,
        findings=findings,
        valid=not has_errors,
        cross_file_summary=cross_file_summary,
    )
