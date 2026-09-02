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
# Runs `tapps-mcp validate-changed --quick` on staged Python files,
# ratcheted against HEAD (TAP-6904).
# Bypass with TAPPS_SKIP_GATE=1, logged to .tapps-mcp/.bypass-log.jsonl.

set -e

# Resolve the ledger dir to the primary checkout, not a linked worktree's own
# cwd (TAP-6931) -- --git-common-dir is identical across a repo's primary
# checkout and all its linked worktrees, so bypasses taken from a worktree
# land in the one ledger the operator actually audits.
_common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "$_common" ]; then
  COMMIT_LOG_DIR="$_common/../.tapps-mcp"
else
  COMMIT_LOG_DIR=".tapps-mcp"
fi

if [ "${TAPPS_SKIP_GATE:-}" = "1" ]; then
  mkdir -p "$COMMIT_LOG_DIR" 2>/dev/null || true
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  staged="$(git diff --cached --name-only --diff-filter=ACM | paste -sd, - || true)"
  printf '{"ts":"%s","hook":"pre-commit","reason":"TAPPS_SKIP_GATE=1","staged":"%s"}\\n' \\
    "$ts" "$staged" \\
    >> "$COMMIT_LOG_DIR/.bypass-log.jsonl" 2>/dev/null || true
  echo "tapps-mcp pre-commit: bypassed via TAPPS_SKIP_GATE=1. Logged to $COMMIT_LOG_DIR/.bypass-log.jsonl" >&2
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
# Validate exactly the staged files -- without --file-paths the CLI
# auto-detects all branch-changed files and can trip the validation cap.
STAGED_CSV=$(echo "$STAGED_PY" | paste -sd, -)
# TAP-6904: ratchet against HEAD so a commit that holds or improves a file
# already below the threshold passes, instead of deadlocking on a bar no
# honest commit could clear. CI ratchets against the PR base; HEAD is the
# hook's equivalent and asks the question a hook should: does THIS commit
# make the file worse? Absent on the very first commit, where nothing to
# compare against means the ratchet stays off.
BASELINE_ARGS=()
if git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
  BASELINE_ARGS=(--baseline-ref HEAD)
fi
if ! "${RUNNER[@]}" validate-changed --quick --file-paths "$STAGED_CSV" ${BASELINE_ARGS+"${BASELINE_ARGS[@]}"}; then
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
