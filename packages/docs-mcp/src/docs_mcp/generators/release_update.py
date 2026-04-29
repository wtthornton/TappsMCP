"""Release update document generator for Linear project updates."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel


class ReleaseUpdateConfig(BaseModel):
    """Configuration for release update document generation."""

    version: str
    prev_version: str
    bump_type: str  # "patch" | "minor" | "major"
    highlights: list[str]
    issues_closed: list[str]  # ["TAP-123: title", ...]
    breaking_changes: list[str] = []
    links: dict[str, str] = {}  # {"Changelog": "url", ...}
    health: str = "On Track"  # "On Track" | "At Risk" | "Off Track"
    release_date: str = ""  # ISO date; defaults to today


class ReleaseUpdateGenerator:
    """Generates Linear project update documents for version releases.

    Template sections: version header, health, highlights, issues closed,
    breaking changes (minor/major only), links.
    """

    VALID_BUMP_TYPES: ClassVar[frozenset[str]] = frozenset({"patch", "minor", "major"})
    VALID_HEALTH: ClassVar[frozenset[str]] = frozenset({"On Track", "At Risk", "Off Track"})

    def generate(self, config: ReleaseUpdateConfig) -> str:
        """Return a markdown body for the release update document."""
        date = config.release_date or datetime.now(UTC).strftime("%Y-%m-%d")
        lines: list[str] = []

        lines.append(f"## Release v{config.version} ({date})\n")
        lines.append(f"**Health:** {config.health}\n")

        lines.append("### Highlights\n")
        if config.highlights:
            for h in config.highlights:
                lines.append(f"- {h}")
        else:
            lines.append("- No highlights recorded.")
        lines.append("")

        lines.append("### Issues Closed\n")
        if config.issues_closed:
            for issue in config.issues_closed:
                lines.append(f"- {issue}")
        else:
            lines.append("- None.")
        lines.append("")

        if config.bump_type in ("minor", "major") and config.breaking_changes:
            lines.append("### Breaking Changes\n")
            for change in config.breaking_changes:
                lines.append(f"- {change}")
            lines.append("")

        if config.links:
            lines.append("### Links\n")
            for label, url in config.links.items():
                lines.append(f"- {label}: {url}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers used by tapps_release_update
# ---------------------------------------------------------------------------

_TAP_REF_RE = re.compile(r"\b(TAP-\d+)\b")


def scrape_tap_refs(text: str) -> list[str]:
    """Return deduplicated TAP-### identifiers found in *text*, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for m in _TAP_REF_RE.finditer(text):
        ref = m.group(1)
        if ref not in seen:
            seen.add(ref)
            result.append(ref)
    return result


def infer_bump_type(version: str, prev_version: str) -> str:
    """Infer patch/minor/major from the semver delta between *version* and *prev_version*.

    Returns "patch" when parsing fails or versions are equal.
    """
    def _parse(v: str) -> tuple[int, int, int] | None:
        v = v.lstrip("v")
        parts = v.split(".")
        try:
            return int(parts[0]), int(parts[1]), int(parts[2].split("-")[0])
        except (IndexError, ValueError):
            return None

    cur = _parse(version)
    prev = _parse(prev_version)
    if cur is None or prev is None:
        return "patch"
    if cur[0] != prev[0]:
        return "major"
    if cur[1] != prev[1]:
        return "minor"
    return "patch"
