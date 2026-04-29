"""Linear SDLC installer (TAP-411).

Writes the rendered templates from :mod:`tapps_mcp.pipeline.linear_sdlc.renderer`
into a consuming project and clones the upstream Linear-Claude skill into
``.claude/skills/linear/``. The clone target is the active production
pattern proven by ``~/code/NLTlabsPE/.claude/skills/linear/`` — see the
README at line 27 of that file for the manual procedure this automates.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.linear_sdlc.config import LinearSDLCConfig
from tapps_mcp.pipeline.linear_sdlc.renderer import render_all

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


__all__ = [
    "CLONE_TIMEOUT_SECONDS",
    "SKILL_INSTALL_PATH",
    "UPSTREAM_SKILL_REPO",
    "install_linear_sdlc",
]
