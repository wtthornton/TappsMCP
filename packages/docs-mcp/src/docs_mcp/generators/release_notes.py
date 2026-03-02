"""Release notes generation for a specific version.

Extracts highlights, breaking changes, features, fixes, contributors,
and other changes from a version boundary's commits and renders
structured release notes as markdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from docs_mcp.analyzers.version_detector import VersionBoundary

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ReleaseNotes(BaseModel):
    """Structured release notes for a single version."""

    version: str
    date: str
    highlights: list[str] = []
    breaking_changes: list[str] = []
    features: list[str] = []
    fixes: list[str] = []
    other_changes: list[str] = []
    contributors: list[str] = []


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class ReleaseNotesGenerator:
    """Generates release notes from a version boundary."""

    def generate(
        self,
        version_boundary: VersionBoundary,
    ) -> ReleaseNotes:
        """Generate structured release notes from a version boundary.

        Parameters
        ----------
        version_boundary:
            A ``VersionBoundary`` containing version info and commits.

        Returns
        -------
        ReleaseNotes
            Structured release notes with categorized changes.
        """
        from docs_mcp.analyzers.commit_parser import classify_commit

        features: list[str] = []
        fixes: list[str] = []
        breaking_changes: list[str] = []
        other_changes: list[str] = []
        contributors_set: set[str] = set()

        for commit in version_boundary.commits:
            parsed = classify_commit(commit.message)
            description = (
                parsed.description if parsed.description else commit.message.split("\n")[0]
            )

            # Track contributor
            if commit.author:
                contributors_set.add(commit.author)

            # Classify into categories
            if parsed.breaking:
                breaking_changes.append(description)

            if parsed.type == "feat":
                if parsed.scope:
                    features.append(f"**{parsed.scope}:** {description}")
                else:
                    features.append(description)
            elif parsed.type == "fix":
                if parsed.scope:
                    fixes.append(f"**{parsed.scope}:** {description}")
                else:
                    fixes.append(description)
            elif parsed.type in ("docs", "refactor", "perf", "test", "chore",
                                  "style", "ci", "build", "revert"):
                if parsed.scope:
                    other_changes.append(f"**{parsed.scope}:** {description}")
                else:
                    other_changes.append(description)
            else:
                other_changes.append(description)

        # Generate highlights: features + breaking changes (top items)
        highlights = self._extract_highlights(features, breaking_changes)

        date_str = self._format_date(version_boundary.date)

        return ReleaseNotes(
            version=version_boundary.version,
            date=date_str,
            highlights=highlights,
            breaking_changes=breaking_changes,
            features=features,
            fixes=fixes,
            other_changes=other_changes,
            contributors=sorted(contributors_set),
        )

    def render_markdown(self, notes: ReleaseNotes) -> str:
        """Render release notes as markdown.

        Parameters
        ----------
        notes:
            Structured release notes to render.

        Returns
        -------
        str
            Markdown-formatted release notes.
        """
        lines: list[str] = [f"# Release {notes.version}"]
        lines.append("")
        lines.append(f"**Release Date:** {notes.date}")

        if notes.highlights:
            lines.append("")
            lines.append("## Highlights")
            lines.append("")
            for highlight in notes.highlights:
                lines.append(f"- {highlight}")

        if notes.breaking_changes:
            lines.append("")
            lines.append("## Breaking Changes")
            lines.append("")
            for change in notes.breaking_changes:
                lines.append(f"- {change}")

        if notes.features:
            lines.append("")
            lines.append("## New Features")
            lines.append("")
            for feature in notes.features:
                lines.append(f"- {feature}")

        if notes.fixes:
            lines.append("")
            lines.append("## Bug Fixes")
            lines.append("")
            for fix in notes.fixes:
                lines.append(f"- {fix}")

        if notes.other_changes:
            lines.append("")
            lines.append("## Other Changes")
            lines.append("")
            for change in notes.other_changes:
                lines.append(f"- {change}")

        if notes.contributors:
            lines.append("")
            lines.append("## Contributors")
            lines.append("")
            for contributor in notes.contributors:
                lines.append(f"- {contributor}")

        return "\n".join(lines) + "\n"

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _extract_highlights(
        features: list[str],
        breaking_changes: list[str],
    ) -> list[str]:
        """Extract highlights from features and breaking changes.

        Returns up to 5 highlights, prioritizing breaking changes
        then features.
        """
        highlights: list[str] = []
        max_highlights = 5

        for bc in breaking_changes:
            if len(highlights) >= max_highlights:
                break
            highlights.append(f"BREAKING: {bc}")

        for feat in features:
            if len(highlights) >= max_highlights:
                break
            highlights.append(feat)

        return highlights

    @staticmethod
    def _format_date(iso_date: str) -> str:
        """Extract YYYY-MM-DD from an ISO 8601 date string."""
        if not iso_date:
            return "unknown"
        return iso_date[:10]

    def generate_from_versions(
        self,
        versions: list[Any],
        version: str = "",
    ) -> ReleaseNotes | None:
        """Find and generate release notes for a specific version.

        Parameters
        ----------
        versions:
            List of ``VersionBoundary`` objects.
        version:
            Version string to find. If empty, uses the first (newest) version.

        Returns
        -------
        ReleaseNotes | None
            Release notes, or ``None`` if the version was not found.
        """
        if not versions:
            return None

        if not version:
            return self.generate(versions[0])

        for vb in versions:
            if vb.version == version:
                return self.generate(vb)

        return None
