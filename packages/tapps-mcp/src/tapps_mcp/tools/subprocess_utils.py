"""Cross-platform subprocess helpers.

Handles Windows ``.cmd``/``.bat`` shim wrapping and provides both sync
and async command execution with structured output.
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass


def wrap_windows_cmd_shim(argv: list[str]) -> list[str]:
    """Wrap a command for Windows ``.cmd``/``.bat`` shim compatibility.

    On Windows, tools installed via ``pip`` or ``npm`` are often wrapped
    in ``.cmd`` scripts.  These fail when invoked directly via
    ``subprocess`` without routing through ``cmd.exe``.

    Args:
        argv: Command and arguments.

    Returns:
        Possibly-wrapped command list.
    """
    if not argv:
        return argv
    if platform.system() != "Windows":
        return argv

    exe = argv[0]
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", *argv]

    resolved = shutil.which(exe)
    if resolved and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", *argv]

    return argv


@dataclass
class CommandResult:
    """Structured output from a subprocess execution."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    command: list[str] | None = None
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """Whether the command exited with return code 0."""
        return self.returncode == 0
