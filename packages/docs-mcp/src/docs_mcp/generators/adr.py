"""Architecture Decision Record (ADR) generation in MADR and Nygard formats."""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


class ADRRecord(BaseModel):
    """An Architecture Decision Record."""

    number: int
    title: str
    status: str = "proposed"  # proposed, accepted, deprecated, superseded
    date: str = ""  # YYYY-MM-DD, auto-filled if empty
    context: str = ""
    decision: str = ""
    consequences: str = ""
    supersedes: int | None = None


class ADRGenerator:
    """Generates Architecture Decision Records in MADR or Nygard format.

    Supports auto-numbering, slug-based filenames, and index generation.
    """

    VALID_TEMPLATES: ClassVar[frozenset[str]] = frozenset({"madr", "nygard"})
    VALID_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {
            "proposed",
            "accepted",
            "deprecated",
            "superseded",
        }
    )

    _NUMBER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^(\d{4})-.*\.md$")

    def generate(
        self,
        title: str,
        *,
        template: str = "madr",
        context: str = "",
        decision: str = "",
        consequences: str = "",
        status: str = "proposed",
        adr_dir: Path | None = None,
        project_root: Path,
    ) -> tuple[str, str]:
        """Generate an ADR document and return (content, filename).

        Args:
            title: The title of the decision.
            template: Template format - "madr" or "nygard".
            context: The problem context.
            decision: The decision made.
            consequences: The consequences of the decision.
            status: ADR status (proposed, accepted, deprecated, superseded).
            adr_dir: Directory for ADR files. Defaults to project_root/docs/decisions.
            project_root: Root directory of the project.

        Returns:
            A tuple of (rendered content, filename).
        """
        if template not in self.VALID_TEMPLATES:
            logger.warning(
                "invalid_template_falling_back",
                template=template,
                fallback="madr",
            )
            template = "madr"

        if status not in self.VALID_STATUSES:
            logger.warning(
                "invalid_status_falling_back",
                status=status,
                fallback="proposed",
            )
            status = "proposed"

        if adr_dir is None:
            adr_dir = project_root / "docs" / "decisions"

        number = self._next_number(adr_dir)
        adr_date = date.today().isoformat()

        record = ADRRecord(
            number=number,
            title=title,
            status=status,
            date=adr_date,
            context=context,
            decision=decision,
            consequences=consequences,
        )

        content = self._render_nygard(record) if template == "nygard" else self._render_madr(record)

        slug = self._slugify(title)
        filename = f"{number:04d}-{slug}.md"

        logger.debug(
            "adr_generated",
            number=number,
            template=template,
            filename=filename,
        )

        return content, filename

    def _next_number(self, adr_dir: Path) -> int:
        """Determine the next ADR number by scanning existing files.

        Looks for files matching the pattern ``NNNN-*.md`` (4-digit prefix)
        and returns max + 1. Returns 1 if no existing ADRs are found.

        Args:
            adr_dir: Directory containing ADR files.

        Returns:
            The next sequential ADR number.
        """
        max_number = 0

        if not adr_dir.is_dir():
            return 1

        for path in adr_dir.iterdir():
            match = self._NUMBER_PATTERN.match(path.name)
            if match:
                num = int(match.group(1))
                max_number = max(max_number, num)

        return max_number + 1

    def _render_madr(self, record: ADRRecord) -> str:
        """Render an ADR using MADR (Markdown Any Decision Records) format.

        Args:
            record: The ADR record to render.

        Returns:
            Rendered markdown content.
        """
        lines: list[str] = [
            f"# {record.number}. {record.title}",
            "",
            f"Date: {record.date}",
            "",
            "## Status",
            "",
            record.status,
        ]

        if record.supersedes is not None:
            lines.append("")
            lines.append(f"Supersedes [ADR {record.supersedes}]({record.supersedes:04d}-*.md)")

        lines.extend(
            [
                "",
                "## Context",
                "",
                record.context or "Describe the context and problem statement...",
                "",
                "## Decision",
                "",
                record.decision or "Describe the decision that was made...",
                "",
                "## Consequences",
                "",
                record.consequences or "Describe the consequences of this decision...",
                "",
            ]
        )

        return "\n".join(lines)

    def _render_nygard(self, record: ADRRecord) -> str:
        """Render an ADR using Nygard (Michael Nygard) format.

        Args:
            record: The ADR record to render.

        Returns:
            Rendered markdown content.
        """
        lines: list[str] = [
            f"# {record.number}. {record.title}",
            "",
            f"Date: {record.date}",
            "",
            "## Status",
            "",
            record.status,
            "",
            "## Context",
            "",
            record.context or "What is the issue...",
            "",
            "## Decision",
            "",
            record.decision or "What is the change...",
            "",
            "## Consequences",
            "",
            record.consequences or "What becomes easier or more difficult...",
            "",
        ]

        return "\n".join(lines)

    def generate_index(self, adr_dir: Path) -> str:
        """Generate a markdown index of all ADR files in a directory.

        Scans existing ADR files, parses the number, title, status, and date
        from their content, and returns a formatted markdown table.

        Args:
            adr_dir: Directory containing ADR files.

        Returns:
            Markdown index content. Returns an empty index table if no ADRs
            are found or the directory does not exist.
        """
        header_lines: list[str] = [
            "# Architecture Decision Records",
            "",
            "| Number | Title | Status | Date |",
            "|--------|-------|--------|------|",
        ]

        if not adr_dir.is_dir():
            logger.debug("adr_dir_not_found", adr_dir=str(adr_dir))
            return "\n".join(header_lines) + "\n"

        entries: list[tuple[int, str, str, str]] = []

        for path in sorted(adr_dir.iterdir()):
            match = self._NUMBER_PATTERN.match(path.name)
            if not match:
                continue

            number = int(match.group(1))
            title, status, adr_date = self._parse_adr_file(path)

            if title:
                entries.append((number, title, status, adr_date))

        # Sort by number
        entries.sort(key=lambda e: e[0])

        row_lines: list[str] = []
        for number, title, status, adr_date in entries:
            row_lines.append(f"| {number} | {title} | {status} | {adr_date} |")

        return "\n".join(header_lines + row_lines) + "\n"

    def _parse_adr_file(self, path: Path) -> tuple[str, str, str]:
        """Parse title, status, and date from an ADR file.

        Args:
            path: Path to the ADR markdown file.

        Returns:
            A tuple of (title, status, date). Returns empty strings on error.
        """
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.debug("adr_parse_failed", path=str(path), reason=str(exc))
            return "", "", ""

        title = ""
        status = ""
        adr_date = ""

        for line in content.splitlines():
            stripped = line.strip()

            # Parse title from H1: "# N. Title"
            if not title and stripped.startswith("# "):
                # Remove "# N. " prefix
                h1_match = re.match(r"^#\s+\d+\.\s+(.+)$", stripped)
                if h1_match:
                    title = h1_match.group(1).strip()

            # Parse date from "Date: YYYY-MM-DD"
            if not adr_date and stripped.startswith("Date:"):
                adr_date = stripped[len("Date:") :].strip()

            # Parse status: first non-empty line after "## Status"
            if stripped == "## Status":
                status = self._read_next_content_line(content, line)

        return title, status, adr_date

    @staticmethod
    def _read_next_content_line(content: str, after_line: str) -> str:
        """Read the first non-empty line after a given line in content.

        Args:
            content: Full file content.
            after_line: The line to search for (exact match after stripping).

        Returns:
            The first non-empty, non-heading line after the target line.
        """
        found = False
        for line in content.splitlines():
            if found:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    return stripped
            elif line.strip() == after_line.strip():
                found = True
        return ""

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a URL-friendly slug.

        Args:
            text: The text to slugify.

        Returns:
            A lowercase, hyphenated slug.
        """
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")
