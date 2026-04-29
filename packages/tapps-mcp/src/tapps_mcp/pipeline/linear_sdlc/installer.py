"""Linear SDLC installer (TAP-411).

Writes the rendered templates from :mod:`tapps_mcp.pipeline.linear_sdlc.renderer`
into a consuming project and clones the upstream Linear-Claude skill into
``.claude/skills/linear/``. The clone target is the active production
pattern proven by ``~/code/NLTlabsPE/.claude/skills/linear/`` — see the
README at line 27 of that file for the manual procedure this automates.
"""

from __future__ import annotations

import datetime
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.linear_sdlc.config import LinearSDLCConfig
from tapps_mcp.pipeline.linear_sdlc.renderer import TEMPLATE_PATHS, render_all

UPSTREAM_SKILL_REPO: str = "https://github.com/wrsmith108/linear-claude-skill"
SKILL_INSTALL_PATH: str = ".claude/skills/linear"
CLONE_TIMEOUT_SECONDS: int = 30


def install_linear_sdlc(
    project_root: Path,
    config: LinearSDLCConfig,
    *,
    dry_run: bool = False,
    content_return: bool = False,
) -> dict[str, Any]:
    """Render Linear SDLC templates into *project_root* and clone the skill.

    Args:
        project_root: Repository root that will receive the SDLC artifacts.
        config: Render parameters (issue prefix, agent name, skill path).
        dry_run: When True, return the planned actions without writing or
            cloning.
        content_return: When True, return rendered file contents in the
            response (for Docker / read-only filesystems) and skip cloning.

    Returns:
        Dict with ``files_written`` (list of relative paths actually
        written), ``skill_cloned`` (bool), ``skill_path`` (str, relative),
        ``skipped_reason`` (str, when the clone was skipped), and optional
        ``content`` (dict[str, str], in content_return mode).
    """
    rendered = render_all(config)
    result: dict[str, Any] = {
        "files_written": [],
        "skill_cloned": False,
        "skill_path": SKILL_INSTALL_PATH,
        "skipped_reason": "",
    }

    if content_return:
        result["content"] = rendered
        result["skipped_reason"] = "content_return mode — caller must write files"
        return result

    if dry_run:
        result["files_written"] = list(rendered.keys())
        result["skipped_reason"] = "dry_run"
        return result

    written: list[str] = []
    for relative_path, body in rendered.items():
        target = project_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        if relative_path.endswith(".sh"):
            target.chmod(0o755)
        written.append(relative_path)
    result["files_written"] = written

    skill_dir = project_root / SKILL_INSTALL_PATH
    if (skill_dir / ".git").exists():
        result["skipped_reason"] = "skill already cloned"
        return result

    if shutil.which("git") is None:
        result["skipped_reason"] = "git not on PATH"
        return result

    skill_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", UPSTREAM_SKILL_REPO, str(skill_dir)],
            check=True,
            capture_output=True,
            timeout=CLONE_TIMEOUT_SECONDS,
        )
        result["skill_cloned"] = True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        result["skipped_reason"] = f"git clone failed: {exc}"

    return result


def _detect_prefix_from_installed(project_root: Path) -> str:
    """Infer the issue prefix from the installed WORKFLOW.md (e.g. 'TAP')."""
    workflow = project_root / TEMPLATE_PATHS[0]
    if not workflow.exists():
        return "TAP"
    try:
        text = workflow.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"\b([A-Z]{2,})-XXX\b", text)
        if match:
            return match.group(1)
    except OSError:
        pass
    return "TAP"


def refresh_linear_sdlc(
    project_root: Path,
    config: LinearSDLCConfig | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Refresh stale Linear SDLC template files in *project_root*.

    Compares each rendered template against the on-disk file. Files whose
    content already matches are reported as ``unchanged`` and not touched.
    Stale files get a timestamped backup written to
    ``.tapps-mcp/backups/linear-sdlc-<ts>/`` before being overwritten.

    Args:
        project_root: Project root previously bootstrapped with
            :func:`install_linear_sdlc`.
        config: Render parameters. When ``None``, the prefix is inferred from
            the installed ``WORKFLOW.md`` (falls back to ``"TAP"``).
        dry_run: When True, report what would change without writing anything.

    Returns:
        Dict with ``refreshed`` (list of rewritten relative paths),
        ``unchanged`` (list of already-current paths), ``errors`` (per-file
        error messages), and ``backup_dir`` (relative backup path, empty
        string when nothing was backed up or dry_run is True).
    """
    if config is None:
        config = LinearSDLCConfig(issue_prefix=_detect_prefix_from_installed(project_root))

    rendered = render_all(config)
    result: dict[str, Any] = {
        "refreshed": [],
        "unchanged": [],
        "errors": [],
        "backup_dir": "",
    }

    stale: list[str] = []
    for rel_path, body in rendered.items():
        target = project_root / rel_path
        if not target.exists():
            stale.append(rel_path)
            continue
        try:
            existing = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result["errors"].append(f"{rel_path}: read error — {exc}")
            continue
        if existing != body:
            stale.append(rel_path)
        else:
            result["unchanged"].append(rel_path)

    if dry_run:
        result["refreshed"] = list(stale)
        return result

    if not stale:
        return result

    ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = project_root / ".tapps-mcp" / "backups" / f"linear-sdlc-{ts}"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for rel_path in stale:
            src = project_root / rel_path
            if src.exists():
                (backup_dir / Path(rel_path).name).write_bytes(src.read_bytes())
        result["backup_dir"] = str(backup_dir.relative_to(project_root))
    except OSError as exc:
        result["errors"].append(f"backup failed: {exc}")
        return result

    refreshed: list[str] = []
    for rel_path in stale:
        body = rendered[rel_path]
        target = project_root / rel_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            if rel_path.endswith(".sh"):
                target.chmod(0o755)
            refreshed.append(rel_path)
        except OSError as exc:
            result["errors"].append(f"{rel_path}: write error — {exc}")

    result["refreshed"] = refreshed
    return result


__all__ = [
    "CLONE_TIMEOUT_SECONDS",
    "SKILL_INSTALL_PATH",
    "UPSTREAM_SKILL_REPO",
    "install_linear_sdlc",
    "refresh_linear_sdlc",
]
