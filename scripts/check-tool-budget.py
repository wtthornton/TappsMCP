#!/usr/bin/env python3
"""TAP-2029: Reject commits that add new @mcp.tool() registrations without
updating docs/architecture/tool-budget.md.

Usage:
    python3 scripts/check-tool-budget.py [--diff-range RANGE] [--commit-msg MSG]
    python3 scripts/check-tool-budget.py --test   # self-test pass/fail fixtures

Exit codes:
    0 — OK (no new tools, or budget doc updated, or bypass token present)
    1 — New MCP tool registered without updating the tool-budget doc

Bypass:
    Add "Tool-Budget: deferred" or "Tool-Budget: skip" to the commit message
    (or the $TOOL_BUDGET_BYPASS env var) to skip the check. Document the
    reason in the issue / PR for the record.

Example CI usage (GitHub Actions, single-commit push):
    python3 scripts/check-tool-budget.py \
        --diff-range "${{ github.event.before }}..${{ github.sha }}" \
        --commit-msg "$(git log -1 --format='%B')"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import os
import textwrap

# Pattern that marks a new MCP tool registration line in a diff.
# Matches added lines (+...) containing @mcp.tool( (with or without arguments).
_NEW_TOOL_RE = re.compile(r"^\+[^+].*@mcp\.tool\s*\(", re.MULTILINE)

# The budget doc that must be touched when a new tool is added.
_BUDGET_DOC = "docs/architecture/tool-budget.md"

# Bypass token in commit message (case-insensitive).
_BYPASS_RE = re.compile(r"Tool-Budget\s*:\s*(deferred|skip)", re.IGNORECASE)


def _get_diff(diff_range: str) -> str:
    """Return the unified diff text for diff_range."""
    result = subprocess.run(
        ["git", "diff", diff_range],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _get_changed_files(diff_range: str) -> list[str]:
    """Return list of file paths touched in diff_range."""
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _check(diff_text: str, changed_files: list[str], commit_msg: str) -> tuple[bool, str]:
    """Return (ok, reason).

    ok=True  → no action needed
    ok=False → fail with reason
    """
    # 1. Bypass via commit message or env var.
    bypass_env = os.environ.get("TOOL_BUDGET_BYPASS", "")
    if _BYPASS_RE.search(commit_msg) or _BYPASS_RE.search(bypass_env):
        return True, "bypass token found — skipping check"

    # 2. Find new @mcp.tool( lines in the diff.
    new_tool_lines = _NEW_TOOL_RE.findall(diff_text)
    if not new_tool_lines:
        return True, "no new @mcp.tool registrations found"

    count = len(new_tool_lines)
    noun = "tool" if count == 1 else "tools"

    # 3. Verify the budget doc was also updated.
    if _BUDGET_DOC in changed_files:
        return True, f"{count} new {noun} added and tool-budget.md updated"

    # 4. Fail.
    reason = textwrap.dedent(f"""\
        {count} new MCP {noun} registered but {_BUDGET_DOC} was not updated.

        When adding a new @mcp.tool() handler, update docs/architecture/tool-budget.md
        to document whether the tool is eager (counts against the 20-tool budget) or
        deferred (tool_search only). See the "Known server tool counts" table.

        To bypass for exceptional cases, add to your commit message:
            Tool-Budget: deferred   # or: Tool-Budget: skip
    """)
    return False, reason


def _run_tests() -> None:
    """Self-test: verify pass/fail paths with synthetic fixtures."""
    print("Running self-tests…")

    # --- PASS fixtures ---

    # Pass: no new tools in diff
    ok, msg = _check("", [], "")
    assert ok, f"Expected PASS for empty diff, got: {msg}"
    print("  PASS: empty diff → ok")

    # Pass: new tool BUT budget doc updated
    diff_with_tool = "+    @mcp.tool()\n+    async def my_new_tool() -> None: ...\n"
    ok, msg = _check(diff_with_tool, [_BUDGET_DOC, "packages/tapps-mcp/src/server.py"], "")
    assert ok, f"Expected PASS when budget doc updated, got: {msg}"
    print(f"  PASS: new tool + budget doc updated → ok")

    # Pass: bypass token in commit message
    ok, msg = _check(diff_with_tool, [], "feat: add tool\n\nTool-Budget: deferred\n")
    assert ok, f"Expected PASS with bypass token, got: {msg}"
    print("  PASS: bypass token in commit message → ok")

    # Pass: bypass env var
    os.environ["TOOL_BUDGET_BYPASS"] = "Tool-Budget: skip"
    ok, msg = _check(diff_with_tool, [], "")
    del os.environ["TOOL_BUDGET_BYPASS"]
    assert ok, f"Expected PASS with bypass env var, got: {msg}"
    print("  PASS: bypass env var → ok")

    # --- FAIL fixtures ---

    # Fail: new tool, budget doc NOT updated, no bypass
    ok, msg = _check(diff_with_tool, ["packages/tapps-mcp/src/server.py"], "")
    assert not ok, "Expected FAIL when budget doc not updated"
    assert _BUDGET_DOC in msg, "Expected budget doc path in failure message"
    print("  FAIL: new tool, budget doc missing → correctly rejected")

    # Fail: two new tools, no budget doc
    two_tools = (
        "+    @mcp.tool()\n+    async def tool_one() -> None: ...\n"
        "+    @mcp.tool(description='...')\n+    async def tool_two() -> None: ...\n"
    )
    ok, msg = _check(two_tools, [], "")
    assert not ok, "Expected FAIL for two tools without budget update"
    assert "2 new" in msg, f"Expected '2 new' in message, got: {msg}"
    print("  FAIL: two new tools, no budget doc → correctly rejected")

    print("All self-tests passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--diff-range",
        default="HEAD~1..HEAD",
        help="Git diff range (default: HEAD~1..HEAD)",
    )
    parser.add_argument(
        "--commit-msg",
        default="",
        help="Commit message to scan for bypass token",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run self-tests and exit",
    )
    args = parser.parse_args()

    if args.test:
        _run_tests()
        return 0

    try:
        diff_text = _get_diff(args.diff_range)
        changed_files = _get_changed_files(args.diff_range)
    except subprocess.CalledProcessError as exc:
        print(f"git error: {exc}", file=sys.stderr)
        return 1

    ok, reason = _check(diff_text, changed_files, args.commit_msg)
    if ok:
        print(f"tool-budget check: OK — {reason}")
        return 0

    print(f"tool-budget check: FAIL\n\n{reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
