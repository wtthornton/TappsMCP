"""Architecture Decision Record (ADR) generation in MADR and Nygard formats."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

import structlog
import yaml
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

    _NUMBER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+)-.*\.md$")

    # Shape A: YAML frontmatter block delimited by "---" lines.
    _FRONTMATTER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL
    )

    # Shape B: a "Status:"/"Date:" label line, optionally wrapped in bold
    # markers ("**Status:** Accepted"), bare ("Status: Accepted"), or as a
    # markdown list item ("- **Status:** Accepted"). The optional-bold match
    # also covers the bare variant used by this repo's own ADR-0008, which
    # has neither a YAML block nor a "## Status" heading; the optional list
    # marker covers AgentForge ADRs that render the same field as a bullet.
    _BOLD_FIELD_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:[-*]\s+)?\*{0,2}(status|date)\s*:\*{0,2}\s*(.+?)\*{0,2}\s*$", re.IGNORECASE
    )

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
        adr_date = datetime.now(UTC).date().isoformat()

        record = ADRRecord(
            number=number,
            title=title,
            status=status,
            date=adr_date,
            context=context,
            decision=decision,
            consequences=consequences,
        )

        content = (
            self._render_nygard(record, adr_dir)
            if template == "nygard"
            else self._render_madr(record, adr_dir)
        )

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

    @staticmethod
    def _find_adr_filename(adr_dir: Path, number: int) -> str | None:
        """Return the first ADR filename whose numeric prefix equals *number*.

        Accepts both zero-padded (``0001-foo.md``) and legacy unpadded
        (``001-foo.md``) names via :attr:`_NUMBER_PATTERN`.
        """
        if not adr_dir.is_dir():
            return None
        for path in sorted(adr_dir.iterdir()):
            match = ADRGenerator._NUMBER_PATTERN.match(path.name)
            if match and int(match.group(1)) == number:
                return path.name
        return None

    def _supersedes_link(self, adr_dir: Path | None, supersedes: int) -> str:
        """Build a markdown link to the superseded ADR."""
        filename: str | None = None
        if adr_dir is not None:
            filename = self._find_adr_filename(adr_dir, supersedes)
        resolved = filename if filename is not None else f"{supersedes:04d}.md"
        return f"Supersedes [ADR {supersedes}]({resolved})"

    def _render_madr(self, record: ADRRecord, adr_dir: Path | None = None) -> str:
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
            lines.append(self._supersedes_link(adr_dir, record.supersedes))

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

    def _render_nygard(self, record: ADRRecord, adr_dir: Path | None = None) -> str:
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
        ]

        if record.supersedes is not None:
            lines.append("")
            lines.append(self._supersedes_link(adr_dir, record.supersedes))

        lines.extend(
            [
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
        )

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
        for line in content.splitlines():
            stripped = line.strip()
            # Parse title from H1: "# N. Title"
            if not title and stripped.startswith("# "):
                h1_match = re.match(r"^#\s+\d+\.\s+(.+)$", stripped)
                if h1_match:
                    title = h1_match.group(1).strip()
                    break

        status, adr_date = self._parse_status_and_date(content)

        return title, status, adr_date

    def _parse_status_and_date(self, content: str) -> tuple[str, str]:
        """Extract (status, date) from whichever ADR shape the file uses.

        Three shapes exist across the fleet, tried in this precedence order:

        1. **YAML frontmatter** (``status:`` / ``last_reviewed:`` keys) --
           structured, machine-authored metadata. Wins outright when present,
           even over a bold prose line in the same file (8+ AgentForge ADRs
           carry both): the frontmatter is the canonical field, while a bold
           line is a human-facing restatement that may add detail or drift
           out of sync with it.
        2. **Bold markdown line** (``**Status:**`` / ``**Date:**``, or the
           bare ``Status:`` / ``Date:`` variant with no bold markers -- this
           repo's own ADR-0008 uses the bare form with no "## Status"
           heading at all).
        3. **Nygard heading** (``## Status`` followed by the next non-empty
           line) -- the loosest convention, so it is the fallback.

        Fields are taken from a single shape, not mixed across shapes, so a
        file's status and date always come from the same source of truth.
        Status values are lowercased on read (not rewritten on disk) so
        ``Accepted`` and ``accepted`` parse to the same value.
        """
        frontmatter = self._parse_frontmatter(content)
        if frontmatter is not None:
            fm_status = str(frontmatter.get("status") or "")
            if fm_status:
                fm_date = str(frontmatter.get("last_reviewed") or frontmatter.get("date") or "")
                return self._normalize_status(fm_status), fm_date

        bold_status, bold_date = self._parse_bold_fields(content)
        if bold_status:
            return self._normalize_status(bold_status), bold_date

        nygard_status, nygard_date = self._parse_nygard_fields(content)
        return self._normalize_status(nygard_status), nygard_date

    @classmethod
    def _parse_frontmatter(cls, content: str) -> dict[str, object] | None:
        """Parse a leading YAML frontmatter block, if present.

        Returns None when the file has no frontmatter block or the block
        fails to parse as a YAML mapping.
        """
        match = cls._FRONTMATTER_PATTERN.match(content)
        if not match:
            return None
        try:
            parsed = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            logger.debug("adr_frontmatter_parse_failed", reason=str(exc))
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _parse_bold_fields(cls, content: str) -> tuple[str, str]:
        """Parse "Status:"/"Date:" label lines, bold or bare."""
        status = ""
        adr_date = ""
        for line in content.splitlines():
            match = cls._BOLD_FIELD_PATTERN.match(line.strip())
            if not match:
                continue
            label = match.group(1).lower()
            value = match.group(2).strip()
            if label == "status" and not status:
                status = value
            elif label == "date" and not adr_date:
                adr_date = value
            if status and adr_date:
                break
        return status, adr_date

    @staticmethod
    def _parse_nygard_fields(content: str) -> tuple[str, str]:
        """Parse the classic Nygard shape: "Date:" line + "## Status" heading."""
        status = ""
        adr_date = ""
        for line in content.splitlines():
            stripped = line.strip()
            if not adr_date and stripped.startswith("Date:"):
                adr_date = stripped[len("Date:") :].strip()
            if stripped == "## Status":
                status = ADRGenerator._read_next_content_line(content, line)
        return status, adr_date

    @staticmethod
    def _normalize_status(status: str) -> str:
        """Lowercase a parsed status value for read-side normalization.

        This never rewrites ADR file content on disk -- it only normalizes
        the in-memory value returned to callers (e.g. the index table) so
        ``Accepted`` and ``accepted`` compare equal.
        """
        return status.lower() if status else status

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
