"""Git log parser for DocsMCP.

Wraps ``gitpython`` to extract commit history, tags, and per-file
last-modified timestamps. All methods return empty/degraded results
when the directory is not a Git repository.
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


class CommitInfo(BaseModel):
    """Lightweight representation of a single Git commit."""

    hash: str
    short_hash: str
    author: str
    author_email: str
    date: str  # ISO 8601
    message: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


class TagInfo(BaseModel):
    """A Git tag with optional semver metadata."""

    name: str
    commit_hash: str
    date: str  # ISO 8601
    is_semver: bool = False
    version: str = ""


# Pre-compiled semver regex (matches v1.2.3, 1.2.3, v1.2.3-rc.1, etc.)
_SEMVER_RE = re.compile(
    r"^v?(\d+\.\d+\.\d+(?:[-+].+)?)$",
)


def _parse_semver_tag(tag_name: str) -> tuple[bool, str]:
    """Return ``(is_semver, version_string)`` for *tag_name*."""
    m = _SEMVER_RE.match(tag_name)
    if m:
        return True, m.group(1)
    return False, ""


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class GitHistoryAnalyzer:
    """Extracts commit history and tag information from a Git repository."""

    def __init__(self, repo_path: Path) -> None:
        self._repo_path = repo_path
        self._repo = self._open_repo()

    # -- private helpers ---------------------------------------------------

    def _open_repo(self) -> object | None:
        """Try to open a git.Repo; return ``None`` on failure."""
        try:
            import git

            return git.Repo(self._repo_path)
        except Exception:
            logger.debug("git_repo_open_failed", path=str(self._repo_path))
            return None

    # -- public API --------------------------------------------------------

    def get_commits(
        self,
        *,
        limit: int = 100,
        since: str | None = None,
        until: str | None = None,
        path: str | None = None,
    ) -> list[CommitInfo]:
        """Return recent commits, newest first.

        Parameters
        ----------
        limit:
            Maximum number of commits to return.
        since:
            ISO date string — only commits after this date.
        until:
            ISO date string — only commits before this date.
        path:
            If given, only commits touching this file/directory.
        """
        if self._repo is None:
            return []

        try:
            import git as git_module

            repo: git_module.Repo = self._repo  # type: ignore[assignment]

            kwargs: dict[str, object] = {"max_count": limit}
            if since:
                kwargs["since"] = since
            if until:
                kwargs["until"] = until

            if path:
                commits_iter = repo.iter_commits(paths=path, **kwargs)  # type: ignore[arg-type]  # gitpython stubs are imprecise
            else:
                commits_iter = repo.iter_commits(**kwargs)  # type: ignore[arg-type]  # gitpython stubs are imprecise

            results: list[CommitInfo] = []
            for commit in commits_iter:
                files_changed = 0
                insertions = 0
                deletions = 0
                try:
                    stats = commit.stats.total
                    files_changed = stats.get("files", 0)
                    insertions = stats.get("insertions", 0)
                    deletions = stats.get("deletions", 0)
                except Exception:
                    pass

                results.append(
                    CommitInfo(
                        hash=commit.hexsha,
                        short_hash=commit.hexsha[:7],
                        author=str(commit.author),
                        author_email=str(commit.author.email) if commit.author.email else "",
                        date=commit.committed_datetime.isoformat(),
                        message=str(commit.message).strip(),
                        files_changed=files_changed,
                        insertions=insertions,
                        deletions=deletions,
                    )
                )
            return results
        except Exception:
            logger.debug("git_get_commits_failed", path=str(self._repo_path), exc_info=True)
            return []

    def get_tags(self) -> list[TagInfo]:
        """Return all tags in the repository."""
        if self._repo is None:
            return []

        try:
            import git as git_module

            repo: git_module.Repo = self._repo  # type: ignore[assignment]
            results: list[TagInfo] = []

            for tag in repo.tags:
                try:
                    commit = tag.commit
                    is_semver, version = _parse_semver_tag(tag.name)
                    results.append(
                        TagInfo(
                            name=tag.name,
                            commit_hash=commit.hexsha,
                            date=commit.committed_datetime.isoformat(),
                            is_semver=is_semver,
                            version=version,
                        )
                    )
                except Exception:
                    continue

            return results
        except Exception:
            logger.debug("git_get_tags_failed", path=str(self._repo_path), exc_info=True)
            return []

    def get_file_last_modified(self, file_path: str) -> str | None:
        """Return the ISO 8601 date of the last commit touching *file_path*.

        Returns ``None`` if the file has no commits or the repo is not valid.
        """
        if self._repo is None:
            return None

        try:
            import git as git_module

            repo: git_module.Repo = self._repo  # type: ignore[assignment]
            commits = list(repo.iter_commits(paths=file_path, max_count=1))
            if commits:
                return commits[0].committed_datetime.isoformat()
            return None
        except Exception:
            logger.debug(
                "git_file_last_modified_failed",
                path=str(self._repo_path),
                file=file_path,
                exc_info=True,
            )
            return None
