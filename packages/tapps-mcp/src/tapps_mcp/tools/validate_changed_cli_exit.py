"""CLI exit-code policy for ``tapps-mcp validate-changed``.

MCP keeps ``all_gates_passed=False`` when zero files were gated (inconclusive —
no validate-ok marker). CLI/CI must not treat that empty gate as failure for
stamp/docs/version-bump PRs.
"""

from __future__ import annotations

from collections.abc import Mapping


def validate_changed_cli_exit_code(
    data: Mapping[str, object], *, explicit_paths: bool = False
) -> int:
    """Map validate-changed tool data to a process exit code.

    Returns 0 when auto-detect finds nothing to gate (and judges passed).
    Returns 1 when judges failed, explicit paths resolved to nothing, or any
    gated file failed the quality gate.
    """
    if not data.get("judges_passed", True):
        return 1
    files_validated = int(data.get("files_validated", 0) or 0)
    if files_validated == 0:
        if explicit_paths or data.get("path_hint"):
            return 1
        return 0
    if not data.get("all_gates_passed", False):
        return 1
    return 0
