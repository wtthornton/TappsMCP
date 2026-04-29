"""Content sourcing for release update documents (TAP-1112).

Handles CHANGELOG section extraction, git log parsing, and TAP-### ref
scraping. Called by the tapps_release_update MCP tool handler.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_TAP_REF_RE = re.compile(r"\b(TAP-\d+)\b")
_CHANGELOG_HEADER_RE = re.compile(r"^#{1,3}\s+\[?v?(\d+\.\d+\.\d+[^\]]*)\]?", re.MULTILINE)


def source_changelog_section(project_root: Path, version: str) -> str | None:
    """Extract the section for *version* from CHANGELOG.md if it exists.

    Returns the raw markdown block (stripped), or None if the file doesn't
    exist or the version isn't found.
    """
    changelog = project_root / "CHANGELOG.md"
    if not changelog.exists():
        return None

    text = changelog.read_text(encoding="utf-8", errors="replace")
    clean_version = version.lstrip("v")

    matches = list(_CHANGELOG_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).lstrip("v").startswith(clean_version):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return None


def source_git_log(
    project_root: Path,
    prev_version: str,
    version: str = "HEAD",
) -> tuple[list[str], list[str]]:
    """Parse git log between *prev_version* and *version*.

    Returns (highlights, issues_closed):
    - highlights: conventional-commit descriptions (feat/fix/perf), one per line
    - issues_closed: "TAP-### description" strings scraped from commit messages
    """
    rev_range = f"v{prev_version.lstrip('v')}..{version}"
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", rev_range],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=10,
        )
        if result.returncode != 0:
            logger.debug("git_log_failed", stderr=result.stderr[:200])
            return [], []
        raw_lines = result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return [], []

    highlights: list[str] = []
    tap_refs: dict[str, str] = {}

    for line in raw_lines:
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        msg = parts[1]

        # Collect TAP-### refs with description
        for ref in _TAP_REF_RE.findall(msg):
            if ref not in tap_refs:
                tap_refs[ref] = _clean_description(msg)

        # Conventional commit highlights
        if re.match(r"^(feat|fix|perf|refactor|revert)(\(.*?\))?[!:]", msg):
            desc = re.sub(r"^[^:]+:\s*", "", msg).strip()
            desc = re.sub(r"\s*\(TAP-\d+(?:,\s*TAP-\d+)*\)\s*$", "", desc).strip()
            if desc:
                highlights.append(desc)

    issues_closed = [f"{ref}: {desc}" for ref, desc in tap_refs.items()]
    return highlights, issues_closed


def _clean_description(msg: str) -> str:
    """Strip conventional commit prefix and TAP-### from a git oneline message."""
    # Remove SHA (already stripped by --oneline processing caller)
    desc = re.sub(r"^[^:]+:\s*", "", msg).strip()
    desc = re.sub(r"\s*\(TAP-\d+(?:,\s*TAP-\d+)*\)\s*", " ", desc).strip()
    return desc or msg


def build_release_content(
    version: str,
    prev_version: str,
    bump_type: str,
    project_root: Path,
) -> dict[str, Any]:
    """Source body content for a release update.

    Priority: CHANGELOG.md section → git log conventional commits + TAP-### scrape.
    Returns a dict ready to pass to ReleaseUpdateConfig.
    """
    from docs_mcp.generators.release_update import infer_bump_type

    effective_bump = bump_type or infer_bump_type(version, prev_version)

    # Try CHANGELOG first
    changelog_body = source_changelog_section(project_root, version)
    if changelog_body:
        highlights = [
            line.lstrip("- ").strip()
            for line in changelog_body.splitlines()
            if line.strip().startswith("-") and line.strip() != "-"
        ][:10]
        from docs_mcp.generators.release_update import scrape_tap_refs

        tap_refs = scrape_tap_refs(changelog_body)
        issues_closed = [f"{ref}" for ref in tap_refs]
    else:
        highlights, issues_closed = source_git_log(project_root, prev_version, "HEAD")

    return {
        "version": version,
        "prev_version": prev_version,
        "bump_type": effective_bump,
        "highlights": highlights,
        "issues_closed": issues_closed,
        "changelog_body": changelog_body,
    }
