"""Rename-then-replace exe upgrade for PyInstaller frozen binaries.

On Windows, a running exe cannot be overwritten because the OS holds a
read lock on the file.  However, a locked file *can* be renamed.  This
module exploits that: rename the locked exe to ``*.old``, copy the new
binary to the original path, and clean up the ``.old`` file on next
startup.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Any

import click

from tapps_core.common.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_EXE_SIZE = 1 * 1024 * 1024  # 1 MB
_MAX_EXE_SIZE = 500 * 1024 * 1024  # 500 MB
_OLD_SUFFIX = ".old"


# ---------------------------------------------------------------------------
# Startup cleanup
# ---------------------------------------------------------------------------


def cleanup_stale_old_exes() -> list[Path]:
    """Remove stale ``*.old`` exe backups next to the running binary.

    Called during CLI startup.  Silently skips files that are still locked
    (e.g. an older process is still running from them).

    Returns:
        List of paths that were successfully deleted.
    """
    if not getattr(sys, "frozen", False):
        return []

    exe_path = Path(sys.executable).resolve()
    exe_dir = exe_path.parent
    cleaned: list[Path] = []

    for old_file in exe_dir.glob(f"{exe_path.stem}*{_OLD_SUFFIX}*"):
        try:
            old_file.unlink()
            cleaned.append(old_file)
            log.info("cleaned_stale_exe", path=str(old_file))
        except OSError:
            # File still locked by another process -- skip silently
            log.debug("cleanup_skipped_locked", path=str(old_file))

    return cleaned


# ---------------------------------------------------------------------------
# Stale backup detection (for doctor)
# ---------------------------------------------------------------------------


def detect_stale_backups() -> list[Path]:
    """Return a list of stale ``.old`` exe backups next to the running binary.

    Returns an empty list when not running as a frozen exe.
    """
    if not getattr(sys, "frozen", False):
        return []

    exe_path = Path(sys.executable).resolve()
    exe_dir = exe_path.parent
    return list(exe_dir.glob(f"{exe_path.stem}*{_OLD_SUFFIX}*"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_frozen() -> Path:
    """Verify running as a frozen exe and return the current exe path.

    Raises:
        click.ClickException: If not running as a frozen exe.
    """
    if not getattr(sys, "frozen", False):
        msg = (
            "replace-exe can only be used when running as a frozen executable "
            "(PyInstaller). Use 'pip install --upgrade tapps-mcp' for pip installs."
        )
        raise click.ClickException(msg)
    return Path(sys.executable).resolve()


def _validate_new_exe(new_exe_path: Path, current_exe_path: Path) -> Path:
    """Validate the new exe before replacement.

    Args:
        new_exe_path: Path to the new exe file.
        current_exe_path: Path to the currently running exe.

    Returns:
        Resolved path to the validated new exe.

    Raises:
        click.ClickException: If validation fails.
    """
    resolved = new_exe_path.resolve()

    if not resolved.is_file():
        msg = f"New exe not found: {resolved}"
        raise click.ClickException(msg)

    if resolved == current_exe_path:
        msg = "New exe is the same file as the currently running exe."
        raise click.ClickException(msg)

    size = resolved.stat().st_size
    if size < _MIN_EXE_SIZE:
        msg = (
            f"New exe is suspiciously small ({size:,} bytes). "
            f"Expected at least {_MIN_EXE_SIZE:,} bytes for a PyInstaller exe."
        )
        raise click.ClickException(msg)
    if size > _MAX_EXE_SIZE:
        msg = (
            f"New exe is too large ({size:,} bytes). "
            f"Maximum allowed: {_MAX_EXE_SIZE:,} bytes."
        )
        raise click.ClickException(msg)

    if sys.platform == "win32" and resolved.suffix.lower() != ".exe":
        msg = (
            f"On Windows, the new file must have a .exe extension "
            f"(got: {resolved.suffix})"
        )
        raise click.ClickException(msg)

    return resolved


# ---------------------------------------------------------------------------
# Core replacement logic
# ---------------------------------------------------------------------------


def _choose_old_path(current_exe_path: Path) -> Path:
    """Choose the backup path for the current exe.

    Prefers ``tapps-mcp.exe.old``.  If that already exists and cannot be
    removed, falls back to a timestamped name.
    """
    old_path = current_exe_path.with_name(current_exe_path.name + _OLD_SUFFIX)

    if old_path.exists():
        try:
            old_path.unlink()
        except OSError:
            # File locked by another process -- use timestamped name
            ts = int(time.time())
            old_path = current_exe_path.with_name(
                f"{current_exe_path.name}{_OLD_SUFFIX}.{ts}"
            )

    return old_path


def replace_exe(new_exe_path: Path) -> dict[str, str]:
    """Perform the rename-then-copy exe replacement.

    Args:
        new_exe_path: Path to the new exe to install.

    Returns:
        Dict with ``current``, ``backup``, ``new`` paths and ``status``.

    Raises:
        click.ClickException: On validation or replacement failure.
    """
    current_exe = _validate_frozen()
    new_exe = _validate_new_exe(new_exe_path, current_exe)
    old_path = _choose_old_path(current_exe)

    log.info(
        "replace_exe_start",
        current=str(current_exe),
        new=str(new_exe),
        backup=str(old_path),
    )

    # Step 1: Rename current exe to .old
    try:
        current_exe.rename(old_path)
    except OSError as exc:
        msg = (
            f"Failed to rename current exe to {old_path.name}: {exc}\n"
            "Close all MCP clients using tapps-mcp and try again."
        )
        raise click.ClickException(msg) from exc

    # Step 2: Copy new exe to original path
    try:
        shutil.copy2(new_exe, current_exe)
    except OSError as exc:
        # Rollback: rename .old back to original
        log.warning("replace_exe_rollback", error=str(exc))
        try:
            old_path.rename(current_exe)
        except OSError as rollback_exc:
            msg = (
                f"CRITICAL: Copy failed ({exc}) and rollback also failed "
                f"({rollback_exc}). The original exe is at: {old_path}"
            )
            raise click.ClickException(msg) from exc
        msg = (
            f"Failed to copy new exe: {exc}\n"
            "The original exe has been restored."
        )
        raise click.ClickException(msg) from exc

    log.info("replace_exe_success", backup=str(old_path))

    return {
        "current": str(current_exe),
        "backup": str(old_path),
        "new": str(new_exe),
        "status": "success",
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_replace_exe(new_exe: str) -> bool:
    """Run the replace-exe command logic.

    Called from the CLI ``replace-exe`` command.

    Args:
        new_exe: Path to the new exe as a string.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    result: dict[str, Any] = replace_exe(Path(new_exe))

    click.echo(click.style("Exe replaced successfully!", fg="green"))
    click.echo(f"  Old exe backed up to: {result['backup']}")
    click.echo(f"  New exe installed at: {result['current']}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. Restart any running MCP clients (Claude Code, Cursor, VS Code)")
    click.echo("  2. New sessions will use the updated binary")
    click.echo("  3. The .old backup will be cleaned up automatically on next startup")
    return True
