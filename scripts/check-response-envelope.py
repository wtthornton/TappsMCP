#!/usr/bin/env python3
"""CLI entry point for the response-envelope lint (TAP-5660).

Fails the build when a tool response reports success while carrying a
best-effort sub-result that nothing branched on — the shape behind the two
defects that reached a consuming project in 3.12.65 (TAP-5656).

The analysis lives in :mod:`scripts.response_envelope_lint`, mirroring the
``check-tool-budget.py`` / ``tool_budget_lint.py`` split already used here.

Usage:
    python3 scripts/check-response-envelope.py                # sweep the repo
    python3 scripts/check-response-envelope.py --paths a.py   # explicit files
    python3 scripts/check-response-envelope.py --test         # self-test

Exit codes:
    0 — no unexamined best-effort sub-results
    1 — at least one response site reports success over an unchecked sub-result
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from response_envelope_lint import iter_target_files, run_sweep
from response_envelope_selftest import self_test


def main() -> int:
    """Parse CLI args and run the requested envelope check."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--test", action="store_true", help="run the self-test and exit")
    parser.add_argument("--paths", nargs="*", default=[], help="explicit files to scan")
    args = parser.parse_args()

    if args.test:
        return self_test()

    findings = run_sweep(iter_target_files(args.paths))

    if not findings:
        print("check-response-envelope: no unexamined best-effort sub-results found")
        return 0

    print(f"check-response-envelope: {len(findings)} finding(s)\n")
    for finding in findings:
        print(f"  {finding.render()}")
    print("\nA success envelope must not contradict a nested failure. See TAP-5656.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
