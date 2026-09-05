"""Pre-upgrade backup: what gets saved, and the rollback snapshot itself.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913). ``tapps-mcp
rollback`` restores from what :func:`collect_upgrade_targets` enumerates here,
so a file the upgrade overwrites but this list omits has no recovery path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_hooks_migration import is_managed_hook_filename

log = get_logger(__name__)

# Single files the upgrade may rewrite. Backed up only when they exist.
_CANDIDATE_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/settings.json",
    ".mcp.json",
    ".cursor/mcp.json",
    ".cursor/hooks.json",
    ".vscode/mcp.json",
    # Docker-related config files (Epic 46)
    ".tapps-mcp.yaml",
)

_HOOK_DIRS = (".claude/hooks", ".cursor/hooks")
# TAP-689: rule files that the upgrade regenerates. Without backing these up, a
# consumer's hand-edits to python-quality.md / agent-scope.md /
# tapps-pipeline.mdc (Cursor's canonical pipeline rule, TAP-6440) are lost with
# no rollback path. Covered by the ``_RULE_DIRS`` glob below, not this list.
_RULE_DIRS = (".claude/rules", ".cursor/rules")


def _managed_hook_files(project_root: Path) -> list[Path]:
    """Live ``tapps-*`` hook scripts across both host hook directories."""
    files: list[Path] = []
    for rel in _HOOK_DIRS:
        hooks_dir = project_root / rel
        if hooks_dir.is_dir():
            files.extend(
                f for f in hooks_dir.iterdir() if f.is_file() and is_managed_hook_filename(f.name)
            )
    return files


def _managed_skill_files(project_root: Path) -> list[Path]:
    """``SKILL.md`` for each installed ``tapps-*`` skill."""
    skills_dir = project_root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        skill_file
        for entry in skills_dir.iterdir()
        if entry.is_dir() and entry.name.startswith("tapps-")
        for skill_file in [entry / "SKILL.md"]
        if skill_file.exists()
    ]


def collect_upgrade_targets(project_root: Path) -> list[Path]:
    """Collect files that upgrade_pipeline will overwrite."""
    targets: list[Path] = []
    targets.extend(_managed_hook_files(project_root))
    targets.extend(_managed_skill_files(project_root))

    agents_dir = project_root / ".claude" / "agents"
    if agents_dir.is_dir():
        targets.extend(f for f in agents_dir.iterdir() if f.name.startswith("tapps-"))

    for rel in _RULE_DIRS:
        rules_dir = project_root / rel
        if rules_dir.is_dir():
            targets.extend(rules_dir.glob("*.md"))
            targets.extend(rules_dir.glob("*.mdc"))

    targets.extend(
        candidate
        for candidate in (project_root / rel for rel in _CANDIDATE_FILES)
        if candidate.exists()
    )
    return targets


def create_pre_upgrade_backup(project_root: Path, result: dict[str, Any]) -> bool:
    """Snapshot everything the upgrade may overwrite.

    Returns ``True`` when the upgrade may proceed. On failure the caller must
    abort: TAP-6952 requires ``success=False`` rather than an upgrade that
    silently ran with no rollback path.
    """
    from tapps_mcp import __version__
    from tapps_mcp.distribution.rollback import BackupManager

    try:
        mgr = BackupManager(project_root)
        backup_targets = collect_upgrade_targets(project_root)
        if not backup_targets:
            result["backup"] = "skipped (no targets)"
            return True
        recent = mgr.find_recent_backup(max_age_seconds=60)
        if recent is not None:
            result["backup"] = f"reused: {recent} (deduped within 60s)"
        else:
            backup_dir = mgr.create_backup(
                backup_targets,
                reason="pre-upgrade backup",
                version=__version__,
            )
            result["backup"] = str(backup_dir)
        mgr.cleanup_old_backups(keep=5)
        return True
    except Exception as exc:
        log.exception("backup_failed")
        result["backup"] = f"failed: {exc}"
        result["errors"].append(
            f"Upgrade aborted: backup failed ({exc}). "
            "Fix the backup issue or run with dry_run=True to preview changes."
        )
        result["success"] = False
        return False
