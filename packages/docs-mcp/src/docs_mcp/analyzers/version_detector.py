"""Tag/version boundary detection for DocsMCP.

Detects semver tags in a Git repository, groups commits between
version boundaries, and sorts by version number.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from pydantic import BaseModel

from docs_mcp.analyzers.git_history import CommitInfo, GitHistoryAnalyzer, TagInfo

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class VersionBoundary(BaseModel):
    """Commits between two version tags."""

    version: str
    tag: str
    date: str
    commit_count: int
    commits: list[CommitInfo] = []


# ---------------------------------------------------------------------------
# Semver parsing helper
# ---------------------------------------------------------------------------

_SEMVER_SORT_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:[-+](.+))?$",
)


def _semver_sort_key(version: str) -> tuple[int, int, int, str]:
    """Return a sortable tuple for a semver string.

    Pre-release versions sort before their release (e.g. 1.0.0-rc.1 < 1.0.0).
    """
    m = _SEMVER_SORT_RE.match(version)
    if not m:
        return (0, 0, 0, version)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Pre-release sorts before release: "~" is after all printable ASCII
    pre = m.group(4) if m.group(4) else "~"
    return (major, minor, patch, pre)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class VersionDetector:
    """Detects version boundaries from Git tags."""

    def detect_versions(
        self,
        repo_path: Path,
        *,
        include_commits: bool = True,
    ) -> list[VersionBoundary]:
        """Return version boundaries sorted by semver (newest first).

        Parameters
        ----------
        repo_path:
            Path to the Git repository root.
        include_commits:
            When True, populate the ``commits`` list for each boundary.
        """
        analyzer = GitHistoryAnalyzer(repo_path)
        tags = analyzer.get_tags()

        # Filter to semver tags only
        semver_tags = [t for t in tags if t.is_semver]
        if not semver_tags:
            return []

        # Sort by version ascending
        semver_tags.sort(key=lambda t: _semver_sort_key(t.version))

        boundaries: list[VersionBoundary] = []

        if include_commits:
            all_commits = analyzer.get_commits(limit=10_000)
            boundaries = self._build_boundaries_with_commits(semver_tags, all_commits)
        else:
            boundaries = self._build_boundaries_without_commits(semver_tags)

        # Return newest first
        boundaries.reverse()
        return boundaries

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _build_boundaries_with_commits(
        tags: list[TagInfo],
        all_commits: list[CommitInfo],
    ) -> list[VersionBoundary]:
        """Build boundaries and assign commits between consecutive tags."""
        # Build a mapping of commit hash -> index for fast lookup
        commit_index: dict[str, int] = {c.hash: i for i, c in enumerate(all_commits)}

        boundaries: list[VersionBoundary] = []

        for i, tag in enumerate(tags):
            tag_idx = commit_index.get(tag.commit_hash)

            if i == 0:
                # First version: all commits up to and including this tag
                if tag_idx is not None:
                    commits = all_commits[tag_idx:]
                else:
                    commits = []
            else:
                prev_tag = tags[i - 1]
                prev_idx = commit_index.get(prev_tag.commit_hash)

                if tag_idx is not None and prev_idx is not None:
                    # Commits between previous tag (exclusive) and this tag (inclusive)
                    # all_commits is newest-first, so tag_idx < prev_idx
                    commits = all_commits[tag_idx:prev_idx]
                elif tag_idx is not None:
                    commits = [all_commits[tag_idx]]
                else:
                    commits = []

            boundaries.append(
                VersionBoundary(
                    version=tag.version,
                    tag=tag.name,
                    date=tag.date,
                    commit_count=len(commits),
                    commits=commits,
                )
            )

        return boundaries

    @staticmethod
    def _build_boundaries_without_commits(
        tags: list[TagInfo],
    ) -> list[VersionBoundary]:
        """Build boundaries without commit details."""
        return [
            VersionBoundary(
                version=tag.version,
                tag=tag.name,
                date=tag.date,
                commit_count=0,
            )
            for tag in tags
        ]
