"""Changelog generation in Keep-a-Changelog and Conventional formats.

Generates structured changelogs from git version boundaries and commits.
Uses Jinja2 templates for rendering, with fallback to programmatic
generation if templates are unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from docs_mcp.analyzers.version_detector import VersionBoundary

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_KEEP_A_CHANGELOG_CATEGORIES: list[str] = [
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
]

_CONVENTIONAL_CATEGORIES: list[str] = [
    "Features",
    "Bug Fixes",
    "Documentation",
    "Refactoring",
    "Performance",
    "Tests",
    "Build",
    "CI",
    "Chores",
    "Reverts",
    "Deprecated",
    "Security",
]


class ChangelogEntry(BaseModel):
    """A single entry in a changelog version section."""

    type: str  # "Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"
    description: str
    scope: str = ""
    commit_hash: str = ""
    breaking: bool = False


class ChangelogVersion(BaseModel):
    """A version section in the changelog."""

    version: str
    date: str  # YYYY-MM-DD
    entries: list[ChangelogEntry] = []


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class ChangelogGenerator:
    """Generates changelogs from git version boundaries.

    Maps conventional commit types to Keep-a-Changelog categories
    and renders output using Jinja2 templates.
    """

    TYPE_MAP: ClassVar[dict[str, str]] = {
        "feat": "Added",
        "fix": "Fixed",
        "docs": "Changed",
        "refactor": "Changed",
        "perf": "Changed",
        "test": "Changed",
        "chore": "Changed",
        "style": "Changed",
        "ci": "Changed",
        "build": "Changed",
        "revert": "Removed",
        "deprecate": "Deprecated",
        "security": "Security",
    }

    CONVENTIONAL_TYPE_MAP: ClassVar[dict[str, str]] = {
        "feat": "Features",
        "fix": "Bug Fixes",
        "docs": "Documentation",
        "refactor": "Refactoring",
        "perf": "Performance",
        "test": "Tests",
        "chore": "Chores",
        "style": "Chores",
        "ci": "CI",
        "build": "Build",
        "revert": "Reverts",
        "deprecate": "Deprecated",
        "security": "Security",
    }

    def generate(
        self,
        versions: list[VersionBoundary],
        *,
        format: str = "keep-a-changelog",
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Generate a changelog string from version boundaries.

        Parameters
        ----------
        versions:
            List of ``VersionBoundary`` objects (newest first).
        format:
            Output format - ``"keep-a-changelog"`` or ``"conventional"``.
        include_unreleased:
            Whether to include an ``[Unreleased]`` section.
        unreleased_commits:
            Optional list of ``CommitInfo`` objects for the unreleased section.

        Returns
        -------
        str
            The rendered changelog markdown.
        """
        if format == "conventional":
            return self._generate_conventional(
                versions,
                include_unreleased=include_unreleased,
                unreleased_commits=unreleased_commits,
            )
        return self._generate_keep_a_changelog(
            versions,
            include_unreleased=include_unreleased,
            unreleased_commits=unreleased_commits,
        )

    # -- Keep-a-Changelog format -------------------------------------------

    def _generate_keep_a_changelog(
        self,
        versions: list[VersionBoundary],
        *,
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Render Keep-a-Changelog format."""
        template = self._load_template("keep_a_changelog.md.j2")
        if template is not None:
            return self._render_keep_a_changelog_template(
                template, versions,
                include_unreleased=include_unreleased,
                unreleased_commits=unreleased_commits,
            )
        return self._render_keep_a_changelog_programmatic(
            versions,
            include_unreleased=include_unreleased,
            unreleased_commits=unreleased_commits,
        )

    def _render_keep_a_changelog_template(
        self,
        template: Any,
        versions: list[VersionBoundary],
        *,
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Render using the Jinja2 template."""
        unreleased_entries: dict[str, list[ChangelogEntry]] | None = None
        if include_unreleased and unreleased_commits:
            entries = self._commits_to_entries(unreleased_commits, format="keep-a-changelog")
            unreleased_entries = self._group_entries(entries, _KEEP_A_CHANGELOG_CATEGORIES)
            if not any(unreleased_entries.values()):
                unreleased_entries = None

        version_data: list[dict[str, Any]] = []
        for vb in versions:
            entries = self._commits_to_entries(vb.commits, format="keep-a-changelog")
            grouped = self._group_entries(entries, _KEEP_A_CHANGELOG_CATEGORIES)
            version_data.append({
                "version": vb.version,
                "date": self._format_date(vb.date),
                "grouped_entries": grouped,
            })

        result: str = template.render(
            unreleased_entries=unreleased_entries,
            versions=version_data,
        )
        return self._clean_output(result)

    def _render_keep_a_changelog_programmatic(
        self,
        versions: list[VersionBoundary],
        *,
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Render programmatically (fallback when Jinja2 template not found)."""
        lines: list[str] = [
            "# Changelog",
            "",
            "All notable changes to this project will be documented in this file.",
            "",
            "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).",
        ]

        if include_unreleased and unreleased_commits:
            entries = self._commits_to_entries(unreleased_commits, format="keep-a-changelog")
            grouped = self._group_entries(entries, _KEEP_A_CHANGELOG_CATEGORIES)
            if any(grouped.values()):
                lines.append("")
                lines.append("## [Unreleased]")
                lines.extend(self._render_grouped_entries_kac(grouped))

        for vb in versions:
            entries = self._commits_to_entries(vb.commits, format="keep-a-changelog")
            grouped = self._group_entries(entries, _KEEP_A_CHANGELOG_CATEGORIES)
            date_str = self._format_date(vb.date)
            lines.append("")
            lines.append(f"## [{vb.version}] - {date_str}")
            lines.extend(self._render_grouped_entries_kac(grouped))

        return "\n".join(lines) + "\n"

    def _render_grouped_entries_kac(
        self,
        grouped: dict[str, list[ChangelogEntry]],
    ) -> list[str]:
        """Render grouped entries in Keep-a-Changelog style."""
        lines: list[str] = []
        for category in _KEEP_A_CHANGELOG_CATEGORIES:
            entries = grouped.get(category, [])
            if not entries:
                continue
            lines.append("")
            lines.append(f"### {category}")
            for entry in entries:
                desc = entry.description
                if entry.scope:
                    desc = f"{desc} ({entry.scope})"
                if entry.breaking:
                    desc = f"{desc} **BREAKING**"
                lines.append(f"- {desc}")
        return lines

    # -- Conventional format -----------------------------------------------

    def _generate_conventional(
        self,
        versions: list[VersionBoundary],
        *,
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Render Conventional Changelog format."""
        template = self._load_template("conventional.md.j2")
        if template is not None:
            return self._render_conventional_template(
                template, versions,
                include_unreleased=include_unreleased,
                unreleased_commits=unreleased_commits,
            )
        return self._render_conventional_programmatic(
            versions,
            include_unreleased=include_unreleased,
            unreleased_commits=unreleased_commits,
        )

    def _render_conventional_template(
        self,
        template: Any,
        versions: list[VersionBoundary],
        *,
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Render using the Jinja2 conventional template."""
        unreleased_entries: dict[str, list[ChangelogEntry]] | None = None
        unreleased_breaking: list[ChangelogEntry] | None = None
        if include_unreleased and unreleased_commits:
            entries = self._commits_to_entries(unreleased_commits, format="conventional")
            unreleased_entries = self._group_entries(entries, _CONVENTIONAL_CATEGORIES)
            unreleased_breaking = [e for e in entries if e.breaking]
            if not any(unreleased_entries.values()):
                unreleased_entries = None
                unreleased_breaking = None

        version_data: list[dict[str, Any]] = []
        for vb in versions:
            entries = self._commits_to_entries(vb.commits, format="conventional")
            grouped = self._group_entries(entries, _CONVENTIONAL_CATEGORIES)
            breaking = [e for e in entries if e.breaking]
            version_data.append({
                "version": vb.version,
                "date": self._format_date(vb.date),
                "grouped_entries": grouped,
                "breaking_entries": breaking if breaking else None,
            })

        result: str = template.render(
            unreleased_entries=unreleased_entries,
            unreleased_breaking=unreleased_breaking,
            versions=version_data,
        )
        return self._clean_output(result)

    def _render_conventional_programmatic(
        self,
        versions: list[VersionBoundary],
        *,
        include_unreleased: bool = True,
        unreleased_commits: list[Any] | None = None,
    ) -> str:
        """Render conventional format programmatically."""
        lines: list[str] = ["# Changelog"]

        if include_unreleased and unreleased_commits:
            entries = self._commits_to_entries(unreleased_commits, format="conventional")
            grouped = self._group_entries(entries, _CONVENTIONAL_CATEGORIES)
            breaking = [e for e in entries if e.breaking]
            if any(grouped.values()):
                lines.append("")
                lines.append("## Unreleased")
                lines.extend(self._render_grouped_entries_conv(grouped))
                if breaking:
                    lines.append("")
                    lines.append("### BREAKING CHANGES")
                    for entry in breaking:
                        lines.append(f"* {entry.description}")

        for vb in versions:
            entries = self._commits_to_entries(vb.commits, format="conventional")
            grouped = self._group_entries(entries, _CONVENTIONAL_CATEGORIES)
            breaking = [e for e in entries if e.breaking]
            date_str = self._format_date(vb.date)
            lines.append("")
            lines.append(f"## {vb.version} ({date_str})")
            lines.extend(self._render_grouped_entries_conv(grouped))
            if breaking:
                lines.append("")
                lines.append("### BREAKING CHANGES")
                for entry in breaking:
                    lines.append(f"* {entry.description}")

        return "\n".join(lines) + "\n"

    def _render_grouped_entries_conv(
        self,
        grouped: dict[str, list[ChangelogEntry]],
    ) -> list[str]:
        """Render grouped entries in conventional style."""
        lines: list[str] = []
        for category in _CONVENTIONAL_CATEGORIES:
            entries = grouped.get(category, [])
            if not entries:
                continue
            lines.append("")
            lines.append(f"### {category}")
            for entry in entries:
                parts: list[str] = []
                if entry.scope:
                    parts.append(f"**{entry.scope}:** {entry.description}")
                else:
                    parts.append(entry.description)
                if entry.commit_hash:
                    parts.append(f" ({entry.commit_hash})")
                lines.append(f"* {''.join(parts)}")
        return lines

    # -- Shared helpers ----------------------------------------------------

    def _commits_to_entries(
        self,
        commits: list[Any],
        *,
        format: str = "keep-a-changelog",
    ) -> list[ChangelogEntry]:
        """Convert CommitInfo objects to ChangelogEntry objects."""
        from docs_mcp.analyzers.commit_parser import classify_commit

        type_map = self.TYPE_MAP if format == "keep-a-changelog" else self.CONVENTIONAL_TYPE_MAP
        entries: list[ChangelogEntry] = []

        for commit in commits:
            parsed = classify_commit(commit.message)
            category = type_map.get(parsed.type, "Changed" if format == "keep-a-changelog" else "Chores")
            description = parsed.description if parsed.description else commit.message.split("\n")[0]
            entries.append(
                ChangelogEntry(
                    type=category,
                    description=description,
                    scope=parsed.scope,
                    commit_hash=commit.short_hash,
                    breaking=parsed.breaking,
                )
            )

        return entries

    @staticmethod
    def _group_entries(
        entries: list[ChangelogEntry],
        category_order: list[str],
    ) -> dict[str, list[ChangelogEntry]]:
        """Group entries by type, maintaining category order."""
        grouped: dict[str, list[ChangelogEntry]] = {}
        for category in category_order:
            matching = [e for e in entries if e.type == category]
            if matching:
                grouped[category] = matching
        return grouped

    @staticmethod
    def _format_date(iso_date: str) -> str:
        """Extract YYYY-MM-DD from an ISO 8601 date string."""
        if not iso_date:
            return "unknown"
        return iso_date[:10]

    @staticmethod
    def _load_template(template_name: str) -> Any:
        """Load a Jinja2 template from the templates directory."""
        try:
            import jinja2

            template_dir = Path(__file__).parent / "templates" / "changelog"
            if not template_dir.is_dir():
                return None

            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(template_dir)),
                autoescape=False,  # nosec B701 — Markdown output, not HTML
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            return env.get_template(template_name)
        except Exception:
            logger.debug("template_load_failed", template=template_name, exc_info=True)
            return None

    @staticmethod
    def _clean_output(text: str) -> str:
        """Clean up template output: collapse excessive blank lines."""
        import re

        # Collapse 3+ consecutive newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Ensure trailing newline
        if not text.endswith("\n"):
            text += "\n"
        return text
