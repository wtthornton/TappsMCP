"""Structural validator for epic planning documents.

Parses markdown epic files and checks for required sections, story
completeness, point/size consistency, dependency cycles, and
files-affected coverage.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_SIZE_POINT_RANGES: dict[str, tuple[int, int]] = {
    "S": (1, 2),
    "M": (3, 5),
    "L": (8, 13),
    "XL": (13, 40),
}

# Regex patterns
# Classic: ### Story 67.1: Title
_STORY_HEADING_RE = re.compile(
    r"^###\s+Story\s+(\d+(?:\.\d+)?)\s*:\s*(.+)",
    re.IGNORECASE,
)
# DocsMCP generator: ### 67.1 -- Title (matches docs_generate_epic stubs)
_STORY_HEADING_DOCSMCP_RE = re.compile(
    r"^###\s+(\d+(?:\.\d+)?)\s*--\s*(.+)\s*$",
    re.IGNORECASE,
)
_POINTS_RE = re.compile(r"\*\*Points:\*\*\s*(\d+)", re.IGNORECASE)
_SIZE_RE = re.compile(r"\*\*Size:\*\*\s*(XS|S|M|L|XL)", re.IGNORECASE)
_PRIORITY_RE = re.compile(r"\*\*Priority:\*\*\s*(P[0-4])", re.IGNORECASE)
_CHECKBOX_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+")
_H2_RE = re.compile(r"^##\s+(.+)")
_H3_RE = re.compile(r"^###\s+(.+)")
_H4_RE = re.compile(r"^####\s+(.+)")
_STORY_REF_RE = re.compile(r"(?:Story\s+)?(\d+\.\d+)", re.IGNORECASE)

# Linked heading: ### [X.Y](path) -- Title
_LINKED_HEADING_RE = re.compile(
    r"^###\s+\[(\d+\.\d+)\]\(([^)]+)\)\s*[:\u2014-]+\s*(.*)",
    re.IGNORECASE,
)

# Table-linked story: | ID | [Title](file.md) | ... |
_TABLE_STORY_RE = re.compile(
    r"^\|\s*(\S+)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|(.*)$",
    re.MULTILINE,
)


class EpicIssue(BaseModel):
    """A single validation finding."""

    severity: str  # "error", "warning", "info"
    location: str  # e.g., "Story 67.1" or "Files Affected"
    message: str


class StoryInfo(BaseModel):
    """Extracted metadata for one story."""

    number: str  # e.g., "67.1"
    title: str
    points: int | None = None
    size: str | None = None  # S, M, L, XL
    priority: str | None = None
    has_acceptance_criteria: bool = False
    has_tasks: bool = False
    has_files: bool = False
    ac_count: int = 0
    task_count: int = 0
    linked_file: str | None = None  # file path from markdown link


class CrossFileSummary(BaseModel):
    """Aggregate completeness metrics from linked story files."""

    total_stories: int = 0
    stories_with_files: int = 0
    files_found: int = 0
    files_missing: int = 0
    with_acceptance_criteria: int = 0
    with_tasks: int = 0
    with_definition_of_done: int = 0
    summary: str = ""


class EpicValidationReport(BaseModel):
    """Aggregated epic validation results."""

    file_path: str
    epic_title: str = ""
    total_stories: int = 0
    stories: list[StoryInfo] = []
    issues: list[EpicIssue] = []
    score: int = 100  # Start at 100, deduct for issues
    passed: bool = True
    cross_file_summary: CrossFileSummary | None = None


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


def _parse_story_heading(stripped: str) -> tuple[str, str] | tuple[str, str, str] | None:
    """Parse a ### story heading.

    Supports:
    - ``### Story N: Title``
    - ``### N -- Title``  (docs_generate_epic format)
    - ``### [N](path) -- Title``  (linked heading)

    Returns a 2-tuple ``(number, title)`` for plain headings, or a 3-tuple
    ``(number, title, linked_file)`` for linked headings.  ``None`` if no match.
    """
    m = _STORY_HEADING_RE.match(stripped)
    if m:
        return m.group(1), m.group(2)
    ml = _LINKED_HEADING_RE.match(stripped)
    if ml:
        return ml.group(1), ml.group(3), ml.group(2)
    m2 = _STORY_HEADING_DOCSMCP_RE.match(stripped)
    if m2:
        return m2.group(1), m2.group(2)
    return None


def _parse_table_size_priority(remaining_cols: str) -> tuple[str | None, str | None]:
    """Extract size and priority from remaining table columns."""
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


def _split_by_heading(
    lines: list[str],
    level: int,
) -> list[tuple[str, list[str]]]:
    """Split lines into sections by heading level.

    Returns a list of (heading_text, body_lines) tuples.
    The first element may have an empty heading if content precedes
    the first heading of the given level.
    """
    prefix = "#" * level
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Check if this is a heading at exactly the target level
        if stripped.startswith(prefix + " ") and (
            len(stripped) == len(prefix) or not stripped[len(prefix)].startswith("#")
        ):
            # Avoid matching deeper headings (e.g., ### when looking for ##)
            raw_heading = stripped[len(prefix) :].strip()
            # Is this exactly the right level? Check no extra # before content
            if not stripped.startswith(prefix + "#"):
                if current_heading or current_body:
                    sections.append((current_heading, current_body))
                current_heading = raw_heading
                current_body = []
                continue
        current_body.append(line)

    if current_heading or current_body:
        sections.append((current_heading, current_body))

    return sections


def _extract_story(
    number: str,
    title: str,
    body_lines: list[str],
) -> StoryInfo:
    """Extract metadata from a story's body lines."""
    points: int | None = None
    size: str | None = None
    priority: str | None = None
    has_ac = False
    has_tasks = False
    has_files = False
    ac_count = 0
    task_count = 0

    in_ac_section = False
    in_tasks_section = False
    in_files_section = False

    for line in body_lines:
        stripped = line.strip()

        # Check points/size/priority on metadata lines
        pm = _POINTS_RE.search(stripped)
        if pm:
            points = int(pm.group(1))
        sm = _SIZE_RE.search(stripped)
        if sm:
            size = sm.group(1).upper()
        prm = _PRIORITY_RE.search(stripped)
        if prm:
            priority = prm.group(1).upper()

        # Detect h2 sub-sections (docs_generate_story uses ## Acceptance Criteria)
        h2_match = _H2_RE.match(stripped)
        if h2_match:
            heading_text = h2_match.group(1).strip().lower()
            in_ac_section = heading_text == "acceptance criteria"
            in_tasks_section = heading_text.startswith("task")
            in_files_section = heading_text.startswith("file")
            if in_ac_section:
                has_ac = True
            if in_tasks_section:
                has_tasks = True
            continue

        # Detect h4 sub-sections
        h4_match = _H4_RE.match(stripped)
        if h4_match:
            heading_text = h4_match.group(1).strip().lower()
            in_ac_section = "acceptance criteria" in heading_text
            in_tasks_section = heading_text.startswith("task")
            in_files_section = heading_text.startswith("file")
            if in_ac_section:
                has_ac = True
            if in_tasks_section:
                has_tasks = True
            continue

        # Detect files section via **Files:** bold marker
        if stripped.lower().startswith("**files:**") or stripped.lower().startswith("**files**"):
            has_files = True
            in_files_section = True
            in_ac_section = False
            in_tasks_section = False
            continue

        # Count checkboxes in AC and Tasks sections
        if _CHECKBOX_RE.match(stripped):
            if in_ac_section:
                ac_count += 1
            elif in_tasks_section:
                task_count += 1

        # Detect file list items (indented lines starting with - `)
        if in_files_section and stripped.startswith("- `"):
            has_files = True

    return StoryInfo(
        number=number,
        title=title.strip(),
        points=points,
        size=size,
        priority=priority,
        has_acceptance_criteria=has_ac,
        has_tasks=has_tasks,
        has_files=has_files,
        ac_count=ac_count,
        task_count=task_count,
    )


def _check_point_size_consistency(story: StoryInfo) -> EpicIssue | None:
    """Check if points and size are consistent."""
    if story.points is None or story.size is None:
        return None

    expected = _SIZE_POINT_RANGES.get(story.size)
    if expected is None:
        return None

    lo, hi = expected
    if story.points < lo or story.points > hi:
        return EpicIssue(
            severity="warning",
            location=f"Story {story.number}",
            message=(
                f"Points ({story.points}) inconsistent with size {story.size} (expected {lo}-{hi})"
            ),
        )
    return None


def _parse_implementation_order(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Parse Implementation Order section for dependency edges.

    Looks for patterns like:
    - Story 67.2 depends on Story 67.1
    - Story 67.3 -> Story 67.1
    - "67.2 (depends on 67.1)"

    Returns list of (story, [dependencies]) tuples.
    """
    edges: dict[str, list[str]] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        refs = _STORY_REF_RE.findall(stripped)
        if len(refs) < 2:
            continue

        # Heuristic: if line contains "depends on", "after", "requires",
        # treat the first ref as dependent on subsequent refs.
        lower = stripped.lower()
        if any(kw in lower for kw in ("depends on", "after", "requires", "blocks")):
            dependent = refs[0]
            deps = refs[1:]
            if dependent not in edges:
                edges[dependent] = []
            edges[dependent].extend(deps)
        elif "->" in stripped:
            # Arrow notation: A -> B means A depends on B
            dependent = refs[0]
            deps = refs[1:]
            if dependent not in edges:
                edges[dependent] = []
            edges[dependent].extend(deps)

    return list(edges.items())


def _detect_cycle(edges: list[tuple[str, list[str]]]) -> list[str] | None:
    """Simple topological sort to detect cycles.

    Returns the cycle path if found, or None.
    """
    graph: dict[str, list[str]] = {}
    for node, deps in edges:
        if node not in graph:
            graph[node] = []
        graph[node].extend(deps)
        for d in deps:
            if d not in graph:
                graph[d] = []

    visited: set[str] = set()
    in_stack: set[str] = set()
    path: list[str] = []

    def _dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor in in_stack:
                path.append(neighbor)
                return True
            if neighbor not in visited and _dfs(neighbor):
                return True

        path.pop()
        in_stack.discard(node)
        return False

    for node in graph:
        if node not in visited and _dfs(node):
            return path

    return None


def _check_story_file_structure(
    content: str,
) -> tuple[bool, bool, bool, int | None, str | None]:
    """Check a story file for structural sections.

    Returns:
        Tuple of (has_ac, has_tasks, has_dod, points, size).
    """
    _ac_re = re.compile(
        r"(?:^##?\s+Acceptance\s+Criteria|^\*\*Acceptance\s+Criteria:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    _tasks_re = re.compile(
        r"(?:^##?\s+Tasks?\b|^\*\*Tasks?:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    _dod_re = re.compile(
        r"(?:^##?\s+Definition\s+of\s+Done|^\*\*Definition\s+of\s+Done:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )

    has_ac = bool(_ac_re.search(content))
    has_tasks = bool(_tasks_re.search(content))
    has_dod = bool(_dod_re.search(content))

    pm = _POINTS_RE.search(content)
    points = int(pm.group(1)) if pm else None

    sm = _SIZE_RE.search(content)
    size = sm.group(1).upper() if sm else None

    return has_ac, has_tasks, has_dod, points, size


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class EpicValidator:
    """Validate the structure and completeness of epic planning documents."""

    def validate(
        self,
        file_path: Path,
        *,
        validate_linked_stories: bool = True,
    ) -> EpicValidationReport:
        """Validate an epic document.

        Args:
            file_path: Path to the epic markdown file.
            validate_linked_stories: When True, follow linked story files and
                validate their internal structure.

        Returns:
            An EpicValidationReport with findings and score.
        """
        report = EpicValidationReport(
            file_path=str(file_path),
        )

        if not file_path.exists():
            report.issues.append(
                EpicIssue(
                    severity="error",
                    location="File",
                    message=f"File does not exist: {file_path}",
                )
            )
            report.score = 0
            report.passed = False
            return report

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report.issues.append(
                EpicIssue(
                    severity="error",
                    location="File",
                    message=f"Cannot read file: {exc}",
                )
            )
            report.score = 0
            report.passed = False
            return report

        if not content.strip():
            report.issues.append(
                EpicIssue(
                    severity="error",
                    location="File",
                    message="File is empty",
                )
            )
            report.score = 0
            report.passed = False
            return report

        lines = content.splitlines()

        # Extract epic title from first H1
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                report.epic_title = stripped[2:].strip()
                break

        # Parse H2 sections
        h2_sections = _split_by_heading(lines, 2)
        h2_names = {name.lower().strip() for name, _ in h2_sections if name}

        # Check required sections
        self._check_required_sections(h2_names, report)

        # Parse stories
        stories_body: list[str] = []
        files_affected_body: list[str] = []
        impl_order_body: list[str] = []

        for name, body in h2_sections:
            lower_name = name.lower().strip()
            if lower_name == "stories":
                stories_body = body
            elif "files affected" in lower_name or lower_name == "files":
                files_affected_body = body
            elif "implementation order" in lower_name or "order" in lower_name:
                impl_order_body = body

        # Extract individual stories
        if stories_body:
            self._parse_stories(stories_body, report)

        # Check stories for completeness
        self._check_story_completeness(report)

        # Check point/size consistency
        self._check_consistency(report)

        # Check implementation order for cycles
        if impl_order_body:
            self._check_implementation_order(impl_order_body, report)

        # Check files-affected coverage
        if files_affected_body and report.stories:
            self._check_files_affected(files_affected_body, report)

        # Cross-file story validation
        if validate_linked_stories and report.stories:
            self._validate_linked_stories(file_path, report)

        # Calculate final score
        self._calculate_score(report)

        return report

    def _check_required_sections(
        self,
        h2_names: set[str],
        report: EpicValidationReport,
    ) -> None:
        """Check that required top-level sections exist."""
        required = {
            "goal": "Goal",
            "motivation": "Motivation",
            "acceptance criteria": "Acceptance Criteria",
            "stories": "Stories",
        }

        for key, display_name in required.items():
            if not any(key in name for name in h2_names):
                report.issues.append(
                    EpicIssue(
                        severity="error",
                        location="Document",
                        message=f"Missing required section: {display_name}",
                    )
                )

    def _parse_stories(
        self,
        stories_body: list[str],
        report: EpicValidationReport,
    ) -> None:
        """Parse story headings and extract metadata.

        Tries heading-based parsing first (classic, linked, docsmcp).
        Falls back to table-linked rows if no headings found.
        """
        # Split stories by ### headings
        current_number = ""
        current_title = ""
        current_linked_file: str | None = None
        current_lines: list[str] = []

        for line in stories_body:
            stripped = line.strip()
            parsed = _parse_story_heading(stripped)
            if parsed:
                # Save previous story
                if current_number:
                    story = _extract_story(current_number, current_title, current_lines)
                    story.linked_file = current_linked_file
                    report.stories.append(story)

                if len(parsed) == 3:
                    current_number, current_title, current_linked_file = parsed
                else:
                    current_number, current_title = parsed
                    current_linked_file = None
                current_lines = []
            else:
                current_lines.append(line)

        # Save last story
        if current_number:
            story = _extract_story(current_number, current_title, current_lines)
            story.linked_file = current_linked_file
            report.stories.append(story)

        # --- Table fallback: try table-linked rows if no heading stories found ---
        if not report.stories:
            body_text = "\n".join(stories_body)
            table_matches = list(_TABLE_STORY_RE.finditer(body_text))
            for match in table_matches:
                story_id = match.group(1)
                title = match.group(2).strip()
                linked_file = match.group(3).strip()
                remaining = match.group(4)

                size, priority = _parse_table_size_priority(remaining)

                report.stories.append(
                    StoryInfo(
                        number=story_id,
                        title=title,
                        linked_file=linked_file,
                        size=size,
                        priority=priority,
                    )
                )

        report.total_stories = len(report.stories)

    def _check_story_completeness(self, report: EpicValidationReport) -> None:
        """Check each story for required elements."""
        for story in report.stories:
            loc = f"Story {story.number}"

            if not story.has_acceptance_criteria and story.ac_count == 0:
                report.issues.append(
                    EpicIssue(
                        severity="error",
                        location=loc,
                        message="Missing acceptance criteria",
                    )
                )

            if story.points is None:
                report.issues.append(
                    EpicIssue(
                        severity="warning",
                        location=loc,
                        message="Missing story points",
                    )
                )

            if story.size is None:
                report.issues.append(
                    EpicIssue(
                        severity="warning",
                        location=loc,
                        message="Missing size estimate",
                    )
                )

            if not story.has_files:
                report.issues.append(
                    EpicIssue(
                        severity="info",
                        location=loc,
                        message="No files listed",
                    )
                )

    def _check_consistency(self, report: EpicValidationReport) -> None:
        """Check point/size consistency for all stories."""
        for story in report.stories:
            issue = _check_point_size_consistency(story)
            if issue:
                report.issues.append(issue)

    def _check_implementation_order(
        self,
        impl_lines: list[str],
        report: EpicValidationReport,
    ) -> None:
        """Check implementation order for dependency cycles."""
        edges = _parse_implementation_order(impl_lines)
        if not edges:
            return

        cycle = _detect_cycle(edges)
        if cycle:
            cycle_str = " -> ".join(cycle)
            report.issues.append(
                EpicIssue(
                    severity="error",
                    location="Implementation Order",
                    message=f"Dependency cycle detected: {cycle_str}",
                )
            )

    def _check_files_affected(
        self,
        files_lines: list[str],
        report: EpicValidationReport,
    ) -> None:
        """Check that story files appear in the Files Affected section."""
        # Collect all file paths mentioned in Files Affected
        affected_text = "\n".join(files_lines).lower()

        # Collect file paths from stories
        for story in report.stories:
            if not story.has_files:
                continue
            # This is a best-effort check -- we just verify the story
            # is referenced in the files-affected section
            if story.number not in affected_text and story.title.lower() not in affected_text:
                # Only warn if the section exists but doesn't reference the story
                report.issues.append(
                    EpicIssue(
                        severity="info",
                        location=f"Story {story.number}",
                        message="Story files not referenced in Files Affected section",
                    )
                )

    def _validate_linked_stories(
        self,
        epic_path: Path,
        report: EpicValidationReport,
    ) -> None:
        """Follow linked story files and validate their structure."""
        epic_dir = epic_path.parent
        stories_with_files = [s for s in report.stories if s.linked_file]

        if not stories_with_files:
            return

        files_found = 0
        files_missing = 0
        with_ac = 0
        with_tasks = 0
        with_dod = 0
        seen_paths: set[str] = set()

        for story in stories_with_files:
            linked = story.linked_file
            if linked is None:  # pragma: no cover — filtered above
                continue

            # Guard against circular/self references
            resolved = (epic_dir / linked).resolve()
            canonical = str(resolved)
            if canonical in seen_paths:
                continue
            seen_paths.add(canonical)

            # Don't read the epic file itself
            if resolved == epic_path.resolve():
                continue

            if not resolved.is_file():
                files_missing += 1
                report.issues.append(
                    EpicIssue(
                        severity="warning",
                        location=f"Story {story.number}",
                        message=f"Linked story file not found: {linked}",
                    )
                )
                continue

            files_found += 1
            try:
                content = resolved.read_text(encoding="utf-8", errors="replace")
            except OSError:
                report.issues.append(
                    EpicIssue(
                        severity="warning",
                        location=f"Story {story.number}",
                        message=f"Cannot read linked story file: {linked}",
                    )
                )
                continue

            has_ac, has_tasks_sec, has_dod, points, size = _check_story_file_structure(content)

            # Merge with inline metadata (linked file wins if present)
            if has_ac:
                story.has_acceptance_criteria = True
                with_ac += 1
            elif not story.has_acceptance_criteria:
                report.issues.append(
                    EpicIssue(
                        severity="info",
                        location=f"Story {story.number}",
                        message="Linked story file missing Acceptance Criteria section",
                    )
                )

            if has_tasks_sec:
                story.has_tasks = True
                with_tasks += 1
            elif not story.has_tasks:
                report.issues.append(
                    EpicIssue(
                        severity="info",
                        location=f"Story {story.number}",
                        message="Linked story file missing Tasks section",
                    )
                )

            if has_dod:
                with_dod += 1

            if points is not None and story.points is None:
                story.points = points
            if size is not None and story.size is None:
                story.size = size

        total = len(stories_with_files)
        parts = [
            f"{total} stories",
            f"{files_found}/{total} files found",
            f"{with_ac}/{total} have AC",
            f"{with_tasks}/{total} have tasks",
        ]
        report.cross_file_summary = CrossFileSummary(
            total_stories=total,
            stories_with_files=total,
            files_found=files_found,
            files_missing=files_missing,
            with_acceptance_criteria=with_ac,
            with_tasks=with_tasks,
            with_definition_of_done=with_dod,
            summary=", ".join(parts),
        )

    def _calculate_score(self, report: EpicValidationReport) -> None:
        """Calculate score: start at 100, deduct for issues."""
        score = 100
        for issue in report.issues:
            if issue.severity == "error":
                score -= 15
            elif issue.severity == "warning":
                score -= 5
            # info issues don't deduct

        report.score = max(score, 0)
        report.passed = report.score >= 50
