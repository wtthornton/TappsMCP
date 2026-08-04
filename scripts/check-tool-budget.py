#!/usr/bin/env python3
"""CLI entry point for the MCP tool-budget lint.

Two checks, both implemented in :mod:`scripts.tool_budget_lint`:

* new MCP tool registrations must come with a ``docs/architecture/tool-budget.md``
  update (TAP-2029);
* the per-server tool counts printed in the front-door docs must match the
  registry (TAP-5611).

Usage:
    python3 scripts/check-tool-budget.py [--diff-range RANGE] [--commit-msg MSG]
    python3 scripts/check-tool-budget.py --check-counts   # docs vs registry
    python3 scripts/check-tool-budget.py --test           # self-test fixtures

Exit codes:
    0 — OK (no new tools, or budget doc updated, or bypass token present)
    1 — New MCP tool registered without updating the tool-budget doc, or a
        documented tool count disagrees with the registry

Bypass:
    Add "Tool-Budget: deferred" or "Tool-Budget: skip" to the commit message
    (or the $TOOL_BUDGET_BYPASS env var) to skip the registration check.
    Document the reason in the issue / PR for the record.

Example CI usage (GitHub Actions, single-commit push):
    python3 scripts/check-tool-budget.py \
        --diff-range "${{ github.event.before }}..${{ github.sha }}" \
        --commit-msg "$(git log -1 --format='%B')"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tool_budget_lint import (
    check_documented_counts,
    check_new_registrations,
    get_changed_files,
    get_diff,
    run_self_tests,
)


def main() -> int:
    """Parse CLI args and run the requested tool-budget check."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
        "--check-counts",
        action="store_true",
        help="Verify documented per-server tool counts match the registry",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run self-tests and exit",
    )
    args = parser.parse_args()

    if args.test:
        run_self_tests()
        return 0

    if args.check_counts:
        ok, reason = check_documented_counts()
        if ok:
            print(f"tool-count check: OK — {reason}")
            return 0
        print(f"tool-count check: FAIL\n\n{reason}", file=sys.stderr)
        return 1

    try:
        diff_text = get_diff(args.diff_range)
        changed_files = get_changed_files(args.diff_range)
    except subprocess.CalledProcessError as exc:
        print(f"git error: {exc}", file=sys.stderr)
        return 1

    ok, reason = check_new_registrations(diff_text, changed_files, args.commit_msg)
    if ok:
        print(f"tool-budget check: OK — {reason}")
        return 0

    print(f"tool-budget check: FAIL\n\n{reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
