"""Git pre-commit hook installer (TAP-979).

Closes the git boundary so commits made outside Claude Code (human shell,
non-Claude tools, scripts) still go through the quality pipeline. Ships a
``.githooks/pre-commit`` script that runs ``tapps-mcp validate-changed
--quick`` on staged Python files and fails the commit on a quality-gate
failure. ``TAPPS_SKIP_GATE=1`` is the documented bypass.

The hook is opt-in via the ``install_git_hooks`` setting in
``.tapps-mcp.yaml`` (default ``False``). When enabled, ``tapps_init`` writes
the script and points ``core.hooksPath`` at ``.githooks``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

GIT_PRE_COMMIT_SCRIPT: str = """\
#!/usr/bin/env bash
# TappsMCP git pre-commit hook (TAP-979)
# Runs `tapps-mcp validate-changed --quick` on staged Python files.
# Bypass with TAPPS_SKIP_GATE=1 (logged to stderr).

set -e

if [ "${TAPPS_SKIP_GATE:-}" = "1" ]; then
  echo "tapps-mcp pre-commit: bypassed via TAPPS_SKIP_GATE=1" >&2
  exit 0
fi

# Collect staged .py files (added/copied/modified).
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.py$' || true)
if [ -z "$STAGED_PY" ]; then
  exit 0
fi

# Resolve the tapps-mcp CLI: prefer `uv run`, fall back to PATH.
if command -v uv >/dev/null 2>&1; then
  RUNNER=(uv run tapps-mcp)
elif command -v tapps-mcp >/dev/null 2>&1; then
  RUNNER=(tapps-mcp)
else
  echo "tapps-mcp pre-commit: no `uv` or `tapps-mcp` on PATH; skipping (install tapps-mcp or set TAPPS_SKIP_GATE=1 to silence)" >&2
  exit 0
fi

echo "tapps-mcp pre-commit: validating $(echo \"$STAGED_PY\" | wc -l | tr -d ' ') staged Python file(s)..." >&2
if ! "${RUNNER[@]}" validate-changed --quick; then
  echo "" >&2
  echo "tapps-mcp pre-commit: quality gate failed. Fix the issues above, or bypass with TAPPS_SKIP_GATE=1 git commit ..." >&2
  exit 1
fi
"""


def install_git_pre_commit(
    project_root: Path,
    *,
    dry_run: bool = False,
    content_return: bool = False,
) -> dict[str, Any]:
    """Write ``.githooks/pre-commit`` and point ``core.hooksPath`` at it.

    Args:
        project_root: Repository root that owns the working tree.
        dry_run: When True, return what would happen without writing.
        content_return: When True, return the file content for an external
            writer (Docker / read-only FS) instead of writing directly.

    Returns:
        Dict with ``installed`` (bool), ``hook_path`` (str, relative),
        ``hooks_path_set`` (bool, whether ``core.hooksPath`` was configured),
        ``skipped_reason`` (str, when not installed), and optional
        ``content`` (str, in content_return mode).
    """
    result: dict[str, Any] = {
        "installed": False,
        "hook_path": ".githooks/pre-commit",
        "hooks_path_set": False,
        "skipped_reason": "",
    }

    if not (project_root / ".git").exists():
        result["skipped_reason"] = "not a git repository (no .git directory)"
        return result

    if dry_run:
        result["skipped_reason"] = "dry_run"
        result["installed"] = True  # would have installed
        return result

    if content_return:
        result["content"] = GIT_PRE_COMMIT_SCRIPT
        result["installed"] = True
        return result

    githooks_dir = project_root / ".githooks"
    githooks_dir.mkdir(exist_ok=True)
    hook_path = githooks_dir / "pre-commit"
    hook_path.write_text(GIT_PRE_COMMIT_SCRIPT, encoding="utf-8")
    hook_path.chmod(0o755)
    result["installed"] = True

    try:
        subprocess.run(
            ["git", "config", "core.hooksPath", ".githooks"],
            cwd=project_root,
            check=True,
            capture_output=True,
            timeout=10,
        )
        result["hooks_path_set"] = True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        result["skipped_reason"] = f"git config core.hooksPath failed: {exc}"

    return result
