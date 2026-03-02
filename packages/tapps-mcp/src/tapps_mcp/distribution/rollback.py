"""Backup and rollback manager for TappsMCP upgrade operations.

Provides :class:`BackupManager` which creates timestamped backups before
upgrades and restores from them on demand.  Backups are stored under
``.tapps-mcp/backups/{timestamp}/`` with a ``manifest.json`` describing
what was backed up and why.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from tapps_core.common.logging import get_logger

log = get_logger(__name__)


class BackupInfo(BaseModel):
    """Summary of a single backup."""

    timestamp: str
    version: str
    file_count: int
    path: str


@dataclass
class BackupManager:
    """Create, list, and restore configuration backups."""

    project_root: Path

    @property
    def _backups_dir(self) -> Path:
        return self.project_root / ".tapps-mcp" / "backups"

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_backup(
        self,
        files_to_backup: list[Path],
        *,
        reason: str = "pre-upgrade backup",
        version: str = "",
    ) -> Path:
        """Copy *files_to_backup* into a timestamped backup directory.

        Returns the backup directory path.
        """
        ts = time.strftime("%Y-%m-%d-%H%M%S")
        # Add suffix to avoid collisions within the same second
        backup_dir = self._backups_dir / ts
        counter = 0
        while backup_dir.exists():
            counter += 1
            backup_dir = self._backups_dir / f"{ts}-{counter}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        copied: list[str] = []
        for src in files_to_backup:
            if not src.exists():
                continue
            try:
                rel = src.relative_to(self.project_root)
            except ValueError:
                log.warning("backup_skip_outside_root", path=str(src))
                continue
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(str(rel))

        manifest: dict[str, Any] = {
            "timestamp": ts,
            "version": version,
            "reason": reason,
            "files": copied,
        }
        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        log.info(
            "backup_created",
            backup_dir=str(backup_dir),
            file_count=len(copied),
        )
        return backup_dir

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_backups(self) -> list[BackupInfo]:
        """Return available backups sorted newest-first."""
        if not self._backups_dir.exists():
            return []
        backups: list[BackupInfo] = []
        for child in sorted(self._backups_dir.iterdir(), reverse=True):
            manifest_path = child / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                backups.append(
                    BackupInfo(
                        timestamp=data.get("timestamp", child.name),
                        version=data.get("version", ""),
                        file_count=len(data.get("files", [])),
                        path=str(child),
                    )
                )
            except (json.JSONDecodeError, KeyError):
                log.warning("backup_manifest_invalid", path=str(manifest_path))
        return backups

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_backup(
        self,
        backup_dir: Path | None = None,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Restore files from a backup.

        If *backup_dir* is ``None``, the latest backup is used.
        Returns the list of restored relative paths.
        """
        if backup_dir is None:
            backups = self.list_backups()
            if not backups:
                return []
            backup_dir = Path(backups[0].path)

        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            log.error("backup_manifest_missing", path=str(manifest_path))
            return []

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files: list[str] = data.get("files", [])

        restored: list[str] = []
        for rel in files:
            src = backup_dir / rel
            dest = self.project_root / rel
            if not src.exists():
                log.warning("backup_file_missing", file=rel)
                continue
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            restored.append(rel)

        log.info(
            "backup_restored",
            backup_dir=str(backup_dir),
            file_count=len(restored),
            dry_run=dry_run,
        )
        return restored

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_old_backups(self, *, keep: int = 5) -> int:
        """Remove backups beyond the *keep* most recent.

        Returns count of removed backups.
        """
        backups = self.list_backups()
        to_remove = backups[keep:]
        removed = 0
        for info in to_remove:
            try:
                shutil.rmtree(info.path)
                removed += 1
                log.debug("backup_removed", path=info.path)
            except OSError:
                log.warning("backup_remove_failed", path=info.path)
        return removed
