"""Smart merge engine for preserving human-written README sections."""

from __future__ import annotations

from typing import ClassVar

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class MergeResult(BaseModel):
    """Result of merging existing and generated README content."""

    content: str
    sections_preserved: list[str] = []
    sections_updated: list[str] = []
    sections_added: list[str] = []


class SmartMerger:
    """Merges generated README content with existing human-written content.

    Sections wrapped in ``<!-- docsmcp:start:section -->`` /
    ``<!-- docsmcp:end:section -->`` markers are machine-managed and will be
    updated. Sections without markers are considered human-written and
    preserved. The title (``# Name``) is always updated.
    """

    SECTION_MARKER_START: ClassVar[str] = "<!-- docsmcp:start:{section} -->"
    SECTION_MARKER_END: ClassVar[str] = "<!-- docsmcp:end:{section} -->"

    def merge(self, existing: str, generated: str) -> MergeResult:
        """Merge existing and generated README content.

        Args:
            existing: The current README content (may be empty).
            generated: The freshly generated README content.

        Returns:
            MergeResult with the merged content and tracking lists.
        """
        if not existing.strip():
            # No existing content - wrap generated sections with markers
            wrapped = self._wrap_with_markers(generated)
            sections = self._extract_section_names(generated)
            return MergeResult(
                content=wrapped,
                sections_added=sections,
            )

        existing_sections = self._parse_sections(existing)
        generated_sections = self._parse_sections(generated)

        preserved: list[str] = []
        updated: list[str] = []
        added: list[str] = []

        # Start with the title from generated (fall back to existing title)
        gen_title = self._extract_title(generated)
        if not gen_title:
            gen_title = self._extract_title(existing)
        result_parts: list[str] = [gen_title] if gen_title else []

        # Track which generated sections we've handled
        handled_generated: set[str] = set()

        # Process existing sections in order.
        # Check markers against the full existing text (markers may appear
        # before the ``## `` heading, outside the parsed section content).
        for section_name, section_content in existing_sections:
            norm_name = self._normalize_name(section_name)

            # Check if this section has docsmcp markers in the full document
            if self._has_markers(existing, norm_name):
                # Machine-managed - replace with generated version
                gen_content = self._find_section(generated_sections, section_name)
                if gen_content is not None:
                    wrapped = self._wrap_section(norm_name, gen_content)
                    result_parts.append(wrapped)
                    updated.append(section_name)
                    handled_generated.add(norm_name)
                else:
                    # Section was in existing with markers but not in generated
                    # Keep it as-is (preserve)
                    result_parts.append(section_content)
                    preserved.append(section_name)
            else:
                # Human-written - preserve
                result_parts.append(section_content)
                preserved.append(section_name)
                handled_generated.add(norm_name)

        # Add new sections from generated that aren't in existing
        for section_name, section_content in generated_sections:
            norm_name = self._normalize_name(section_name)
            if norm_name not in handled_generated:
                wrapped = self._wrap_section(norm_name, section_content)
                result_parts.append(wrapped)
                added.append(section_name)

        content = "\n\n".join(part.strip() for part in result_parts if part.strip())
        # Ensure trailing newline
        if content and not content.endswith("\n"):
            content += "\n"

        return MergeResult(
            content=content,
            sections_preserved=preserved,
            sections_updated=updated,
            sections_added=added,
        )

    def _extract_title(self, content: str) -> str:
        """Extract the H1 title line from content."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped
        return ""

    def _parse_sections(self, content: str) -> list[tuple[str, str]]:
        """Parse content into (section_name, section_content) pairs.

        Returns sections starting from ``## `` headings. The H1 title
        is excluded. Content before the first ``## `` heading is also excluded.
        """
        sections: list[tuple[str, str]] = []
        lines = content.splitlines()

        current_name = ""
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Skip H1 titles
            if stripped.startswith("# ") and not stripped.startswith("## "):
                continue

            if stripped.startswith("## "):
                # Save previous section
                if current_name:
                    sections.append((current_name, "\n".join(current_lines)))

                # Start new section
                current_name = stripped.removeprefix("## ").strip()
                current_lines = [line]
            elif current_name:
                current_lines.append(line)

        # Save final section
        if current_name:
            sections.append((current_name, "\n".join(current_lines)))

        return sections

    def _extract_section_names(self, content: str) -> list[str]:
        """Extract all H2 section names from content."""
        names: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                names.append(stripped.removeprefix("## ").strip())
        return names

    def _normalize_name(self, name: str) -> str:
        """Normalize a section name for comparison."""
        return name.lower().strip().replace(" ", "-")

    def _find_section(self, sections: list[tuple[str, str]], name: str) -> str | None:
        """Find a section by name (case-insensitive)."""
        norm = self._normalize_name(name)
        for section_name, section_content in sections:
            if self._normalize_name(section_name) == norm:
                return section_content
        return None

    def _has_markers(self, content: str, section_name: str) -> bool:
        """Check if content contains docsmcp markers for the given section."""
        start_marker = self.SECTION_MARKER_START.format(section=section_name)
        end_marker = self.SECTION_MARKER_END.format(section=section_name)
        return start_marker in content and end_marker in content

    def _wrap_section(self, section_name: str, content: str) -> str:
        """Wrap a section with docsmcp markers."""
        start_marker = self.SECTION_MARKER_START.format(section=section_name)
        end_marker = self.SECTION_MARKER_END.format(section=section_name)
        return f"{start_marker}\n{content.strip()}\n{end_marker}"

    def _wrap_with_markers(self, content: str) -> str:
        """Wrap all sections in content with docsmcp markers."""
        lines = content.splitlines()
        result: list[str] = []

        current_section: str | None = None
        section_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("## ") and not stripped.startswith("### "):
                # Flush previous section
                if current_section is not None:
                    norm = self._normalize_name(current_section)
                    start = self.SECTION_MARKER_START.format(section=norm)
                    end = self.SECTION_MARKER_END.format(section=norm)
                    result.append(start)
                    result.extend(section_lines)
                    result.append(end)

                current_section = stripped.removeprefix("## ").strip()
                section_lines = [line]
            elif current_section is not None:
                section_lines.append(line)
            else:
                # Before first section (title, badges, description)
                result.append(line)

        # Flush final section
        if current_section is not None:
            norm = self._normalize_name(current_section)
            start = self.SECTION_MARKER_START.format(section=norm)
            end = self.SECTION_MARKER_END.format(section=norm)
            result.append(start)
            result.extend(section_lines)
            result.append(end)

        return "\n".join(result)
