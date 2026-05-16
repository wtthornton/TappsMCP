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

# Canonical sections in the AGENTS.md template (## headings).
# "Tapps Rules" is the leading section ahead of the tool tables.
EXPECTED_SECTIONS: list[str] = [
    "Tapps Rules",
    "Essential tools (always-on workflow)",
    "tapps_session_start vs tapps_init",
    "Using tapps_lookup_docs for domain guidance",
    "Recommended workflow",
    "Checklist task types",
    "Memory systems",
    "Platform hooks and automation",
    "Troubleshooting: MCP tool permissions",
]

# Core tools the template must mention (slimmed template references these; full table in skill)
EXPECTED_TOOLS: list[str] = [
    "tapps_session_start",
    "tapps_quick_check",
    "tapps_validate_changed",
    "tapps_checklist",
    "tapps_quality_gate",
    "tapps_init",
]

_VERSION_RE = re.compile(r"<!--\s*tapps-agents-version:\s*([\d.]+)\s*-->")
_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)

# Markers used by pipeline/karpathy_block.py to wrap the vendored block.
# We detect them here (duplicated to avoid a circular import) so merge_agents_md
# can excise the block before section-splitting.  The block contains a
# `## Karpathy Behavioral Guidelines` heading, so left in place it confuses
# _split_into_sections: the BEGIN marker ends up in the trailing body of the
# previous EXPECTED section and is discarded when that section is replaced
# with the template version, leaving install_or_refresh unable to find the
# block and forcing it to append a duplicate.
_KARPATHY_BEGIN_PREFIX = "<!-- BEGIN: karpathy-guidelines"
_KARPATHY_END_MARKER = "<!-- END: karpathy-guidelines -->"
_LEGACY_KARPATHY_HEADING_RE = re.compile(
    r"\n*^## Karpathy Behavioral Guidelines\b.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)


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


def _strip_karpathy_content(content: str) -> tuple[str, bool]:
    """Remove Karpathy block spans and legacy unwrapped sections.

    The Karpathy guideline block contains a ``## `` heading, which collides
    with the section splitter used by :func:`merge_agents_md`.  We excise
    the block (and any legacy unwrapped copies left by pre-marker versions)
    here so the section merge is clean; :func:`install_or_refresh` then
    re-installs one canonical copy after the merge has written out.

    Returns ``(stripped_content, had_karpathy_content)``.
    """
    had_content = False

    # Remove properly-wrapped BEGIN...END spans (can occur 0+ times).
    while True:
        begin = content.find(_KARPATHY_BEGIN_PREFIX)
        if begin == -1:
            break
        end_idx = content.find(_KARPATHY_END_MARKER, begin)
        if end_idx == -1:
            break
        had_content = True
        end_exclusive = end_idx + len(_KARPATHY_END_MARKER)
        # Consume trailing newlines after END so we don't leave a stranded blank run.
        while end_exclusive < len(content) and content[end_exclusive] == "\n":
            end_exclusive += 1
        # Consume leading newlines before BEGIN for the same reason.
        start = begin
        while start > 0 and content[start - 1] == "\n":
            start -= 1
        content = content[:start] + content[end_exclusive:]

    # Remove legacy unwrapped `## Karpathy Behavioral Guidelines` sections
    # left by pre-marker versions (pre-2.10 projects re-upgrading).
    new_content, count = _LEGACY_KARPATHY_HEADING_RE.subn("", content)
    if count > 0:
        had_content = True
        content = new_content

    # Remove any remaining stray END markers (from malformed prior state).
    if _KARPATHY_END_MARKER in content:
        had_content = True
        content = content.replace(_KARPATHY_END_MARKER, "")

    # Collapse runs of 3+ blank lines the excisions may have created.
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content, had_content


def merge_agents_md(
    existing_content: str,
    template_content: str,
) -> tuple[str, list[str]]:
    """Smart-merge existing AGENTS.md with the latest template.

    Returns ``(merged_content, changes_list)`` where *changes_list*
    describes what was updated.
    """
    changes: list[str] = []

    # TAP-1795: snapshot the existing stamp before any rewriting so we can
    # report whether the merge actually moved it.
    existing_stamp_match = _VERSION_RE.search(existing_content)
    existing_stamp = existing_stamp_match.group(1) if existing_stamp_match else None

    # Excise Karpathy content before section-split (see _strip_karpathy_content).
    # install_or_refresh runs after merge_agents_md in the upgrade pipeline and
    # will re-install one clean block at end-of-file.
    existing_content, had_karpathy = _strip_karpathy_content(existing_content)
    template_content, _ = _strip_karpathy_content(template_content)
    if had_karpathy:
        changes.append("excised_karpathy_block")

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

    # TAP-1795: keep the stamp aligned with the content. The merge above
    # rewrote canonical sections from the current template; leaving an older
    # stamp would make `is_up_to_date` lie and lock skip-merge heuristics on
    # stale content forever.
    stamp_match = _VERSION_RE.search(merged)
    if stamp_match is None:
        merged = f"<!-- tapps-agents-version: {__version__} -->\n" + merged
        changes.append("added_version_marker")
    elif stamp_match.group(1) != __version__:
        merged = _VERSION_RE.sub(
            f"<!-- tapps-agents-version: {__version__} -->",
            merged,
            count=1,
        )
        changes.append("updated_version_marker")

    # If a prior rewrite (e.g. preamble replacement) silently moved the stamp,
    # still surface the change so callers can observe it.
    if (
        existing_stamp is not None
        and existing_stamp != __version__
        and "updated_version_marker" not in changes
        and "added_version_marker" not in changes
    ):
        changes.append("updated_version_marker")

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
