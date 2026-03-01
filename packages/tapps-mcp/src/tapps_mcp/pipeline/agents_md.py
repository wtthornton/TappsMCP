"""AGENTS.md validation and smart-merge logic for tapps_init."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp import __version__

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 9 canonical sections in the AGENTS.md template (## headings)
EXPECTED_SECTIONS: list[str] = [
    "What TappsMCP is",
    "When to use each tool",
    "tapps_session_start vs tapps_init",
    "Domain hints for tapps_consult_expert",
    "Recommended workflow",
    "Checklist task types",
    "Memory systems",
    "Platform hooks and automation",
    "Troubleshooting: MCP tool permissions",
]

# The 28 canonical tool names the template should mention
EXPECTED_TOOLS: list[str] = [
    "tapps_server_info",
    "tapps_session_start",
    "tapps_score_file",
    "tapps_quick_check",
    "tapps_security_scan",
    "tapps_quality_gate",
    "tapps_validate_changed",
    "tapps_lookup_docs",
    "tapps_validate_config",
    "tapps_consult_expert",
    "tapps_research",
    "tapps_list_experts",
    "tapps_project_profile",
    "tapps_session_notes",
    "tapps_memory",
    "tapps_impact_analysis",
    "tapps_report",
    "tapps_checklist",
    "tapps_dashboard",
    "tapps_stats",
    "tapps_feedback",
    "tapps_init",
    "tapps_upgrade",
    "tapps_doctor",
    "tapps_set_engagement_level",
    "tapps_dead_code",
    "tapps_dependency_scan",
    "tapps_dependency_graph",
]

_VERSION_RE = re.compile(r"<!--\s*tapps-agents-version:\s*([\d.]+)\s*-->")
_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class AgentsValidation:
    """Result of validating an existing AGENTS.md file."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.existing_version = self._extract_version()
        self.sections_found, self.sections_missing = self._check_sections()
        self.tools_found, self.tools_missing = self._check_tools()

    def _extract_version(self) -> str | None:
        m = _VERSION_RE.search(self.content)
        return m.group(1) if m else None

    def _check_sections(self) -> tuple[list[str], list[str]]:
        headings = _SECTION_RE.findall(self.content)
        found = [s for s in EXPECTED_SECTIONS if s in headings]
        missing = [s for s in EXPECTED_SECTIONS if s not in headings]
        return found, missing

    def _check_tools(self) -> tuple[list[str], list[str]]:
        found = [t for t in EXPECTED_TOOLS if t in self.content]
        missing = [t for t in EXPECTED_TOOLS if t not in self.content]
        return found, missing

    @property
    def is_up_to_date(self) -> bool:
        """True when version matches and no sections/tools are missing."""
        return (
            self.existing_version == __version__
            and not self.sections_missing
            and not self.tools_missing
        )

    @property
    def needs_update(self) -> bool:
        """True when the file is outdated or incomplete."""
        return not self.is_up_to_date

    def to_dict(self) -> dict[str, Any]:
        """Serialise validation results for the init result dict."""
        return {
            "existing_version": self.existing_version,
            "current_version": __version__,
            "sections_found": self.sections_found,
            "sections_missing": self.sections_missing,
            "tools_found": self.tools_found,
            "tools_missing": self.tools_missing,
            "is_up_to_date": self.is_up_to_date,
        }


# ---------------------------------------------------------------------------
# Section-based merge
# ---------------------------------------------------------------------------


def _split_into_sections(content: str) -> list[tuple[str | None, str]]:
    """Split markdown into ``(heading, body)`` pairs.

    The first element may have ``heading=None`` for content before the
    first ``## `` heading.
    """
    parts: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines(keepends=True):
        m = re.match(r"^## (.+?)[\r\n]*$", line)
        if m:
            # Flush previous section
            if current_lines or current_heading is not None:
                parts.append((current_heading, "".join(current_lines)))
            current_heading = m.group(1)
            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush last section
    if current_lines or current_heading is not None:
        parts.append((current_heading, "".join(current_lines)))

    return parts


def merge_agents_md(
    existing_content: str,
    template_content: str,
) -> tuple[str, list[str]]:
    """Smart-merge existing AGENTS.md with the latest template.

    Returns ``(merged_content, changes_list)`` where *changes_list*
    describes what was updated.
    """
    changes: list[str] = []

    existing_sections = _split_into_sections(existing_content)
    template_sections = _split_into_sections(template_content)

    # Build heading -> body map for the template
    template_map: dict[str | None, str] = dict(template_sections)

    merged_parts: list[str] = []
    seen_expected: set[str] = set()

    for heading, body in existing_sections:
        if heading is None:
            # Preamble (before first ##): update from template
            if None in template_map:
                merged_parts.append(template_map[None])
                if body.strip() != template_map[None].strip():
                    changes.append("updated_preamble")
            else:
                merged_parts.append(body)
        elif heading in EXPECTED_SECTIONS:
            # Known TAPPS section: replace with template version
            seen_expected.add(heading)
            template_body = template_map.get(heading, body)
            merged_parts.append(template_body)
            if body.strip() != template_body.strip():
                changes.append(f"updated_section:{heading}")
        else:
            # User-added section: preserve as-is
            merged_parts.append(body)

    # Append any EXPECTED sections that were missing entirely
    for heading in EXPECTED_SECTIONS:
        if heading not in seen_expected and heading in template_map:
            merged_parts.append(template_map[heading])
            changes.append(f"added_section:{heading}")

    merged = "".join(merged_parts)

    # Ensure version marker is present
    if not _VERSION_RE.search(merged):
        merged = f"<!-- tapps-agents-version: {__version__} -->\n" + merged
        changes.append("added_version_marker")

    return merged, changes


# ---------------------------------------------------------------------------
# Public API used by init.py
# ---------------------------------------------------------------------------


def validate_agents_md(agents_path: Path) -> AgentsValidation:
    """Validate an existing AGENTS.md file."""
    content = agents_path.read_text(encoding="utf-8")
    return AgentsValidation(content)


def update_agents_md(
    agents_path: Path,
    template_content: str,
    *,
    overwrite: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Update an existing AGENTS.md.

    Returns ``(action, detail_dict)`` where *action* is one of
    ``"validated"``, ``"updated"``, or ``"overwritten"``.
    """
    existing_content = agents_path.read_text(encoding="utf-8")
    validation = AgentsValidation(existing_content)

    detail: dict[str, Any] = {
        "version": __version__,
        "validation": validation.to_dict(),
    }

    if overwrite:
        agents_path.write_text(template_content, encoding="utf-8")
        detail["changes"] = ["full_overwrite"]
        return "overwritten", detail

    if validation.is_up_to_date:
        detail["changes"] = []
        return "validated", detail

    # Smart merge
    merged, changes = merge_agents_md(existing_content, template_content)
    agents_path.write_text(merged, encoding="utf-8")
    detail["changes"] = changes
    return "updated", detail
