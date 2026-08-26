#!/usr/bin/env python3
"""CLI entry point for regenerating docs/SPRINT_BOARD.md from Linear.

Usage:
    python3 scripts/gen-sprint-board.py --input snapshot.json
    python3 scripts/gen-sprint-board.py --check          # CI gate: is the file stale?

The logic lives in :mod:`scripts.gen_sprint_board` — see that module for the
render/grouping rules.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_sprint_board import (
    OUTPUT_PATH,
    is_fresh,
    load_issues,
    render,
    resolve_input_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to a Linear open-issue snapshot JSON file "
        "(default: newest file under .tapps-mcp-cache/linear-snapshots/)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if regenerating would change docs/SPRINT_BOARD.md",
    )
    args = parser.parse_args()

    try:
        input_path = resolve_input_path(args.input)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    issues = load_issues(input_path)
    content = render(issues, date.today())

    if args.check:
        existing = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if not is_fresh(content, existing):
            print(f"stale: {OUTPUT_PATH} does not match regeneration from {input_path}")
            return 1
        print(f"fresh: {OUTPUT_PATH} matches regeneration from {input_path}")
        return 0

    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} from {input_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
