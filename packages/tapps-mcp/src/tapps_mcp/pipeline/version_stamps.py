"""Version stamp helpers for AGENTS.md and CLAUDE.md.

Shared by ``tapps_upgrade`` (stamp-only refresh when files are in
``upgrade_skip_files``), ``tapps-mcp bump-stamps``, and release tooling.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STAMP_RE_CACHE: dict[str, re.Pattern[str]] = {}


def stamp_regex(stamp_key: str) -> re.Pattern[str]:
    """Return a regex matching ``<!-- <stamp_key>: X.Y.Z -->``."""
    if stamp_key not in _STAMP_RE_CACHE:
        _STAMP_RE_CACHE[stamp_key] = re.compile(rf"<!--\s*{re.escape(stamp_key)}:\s*([\d.]+)\s*-->")
    return _STAMP_RE_CACHE[stamp_key]


def read_stamp(path: Path, stamp_key: str) -> str | None:
    """Return the stamp value from *path*, or ``None`` if absent."""
    if not path.exists():
        return None
    match = stamp_regex(stamp_key).search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def rewrite_stamp(path: Path, stamp_key: str, new_version: str) -> tuple[str | None, str]:
    """Rewrite the named version stamp in *path*.

    Returns ``(old_stamp, new_content)``. Raises ``ValueError`` when no stamp
    exists.
    """
    content = path.read_text(encoding="utf-8")
    regex = stamp_regex(stamp_key)
    match = regex.search(content)
    if not match:
        raise ValueError(f"No {stamp_key} stamp found in {path}")
    old = match.group(1)
    new_content = regex.sub(f"<!-- {stamp_key}: {new_version} -->", content, count=1)
    return old, new_content


def bump_stamp_if_stale(
    path: Path,
    stamp_key: str,
    target_version: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bump *path* stamp to *target_version* when stale or missing action info."""
    if not path.exists():
        return {"action": "skipped", "detail": "file missing"}

    current = read_stamp(path, stamp_key)
    if current == target_version:
        return {"action": "unchanged", "stamp": current}

    if current is None:
        return {
            "action": "skipped",
            "detail": f"no {stamp_key} stamp — add manually or remove from upgrade_skip_files",
        }

    if dry_run:
        return {
            "action": "would-bump-stamp",
            "from": current,
            "to": target_version,
        }

    old, new_content = rewrite_stamp(path, stamp_key, target_version)
    path.write_text(new_content, encoding="utf-8")
    return {"action": "bumped-stamp", "from": old, "to": target_version}
