#!/usr/bin/env python3
"""CLI entry point for the monorepo version bumper.

Usage:
    python3 scripts/bump-versions.py --patch    # 3.12.65 -> 3.12.66
    python3 scripts/bump-versions.py --minor    # 3.12.65 -> 3.13.0
    python3 scripts/bump-versions.py --major    # 3.12.65 -> 4.0.0
    python3 scripts/bump-versions.py --dry-run --patch   # preview only
    python3 scripts/bump-versions.py --sync     # re-align drifted versions
    python3 scripts/bump-versions.py --check    # CI gate: derived files in sync?

The logic lives in :mod:`scripts.bump_versions` — see that module for what a
bump rewrites and why the hook manifest is verified rather than regenerated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bump_versions import (
    _max_current_version,
    collect_bump_changes,
    run_check,
)


def main() -> int:
    """Bump pyproject + npm + derived files atomically, or run --check."""
    parser = argparse.ArgumentParser(description="Bump versions across TappsMCP monorepo")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--major", action="store_true", help="Bump major version")
    group.add_argument("--minor", action="store_true", help="Bump minor version")
    group.add_argument("--patch", action="store_true", help="Bump patch version")
    group.add_argument(
        "--sync",
        action="store_true",
        help="Re-align all packages to the current max version (no bump). "
        "Used when packages have drifted out of sync.",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="CI gate: exit 1 if any derived file lags pyproject. No writes.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    if args.check:
        return run_check()

    part: str | None = (
        "major" if args.major else "minor" if args.minor else "patch" if args.patch else None
    )

    if part is None:
        print(f"Syncing all packages to {_max_current_version()}...\n")
    else:
        print(f"Bumping {part} version across all packages (unified)...\n")

    changes = collect_bump_changes(part)

    if not changes:
        print("\nNo files to update.")
        return 1

    if args.dry_run:
        print("\n[dry-run] No files were modified.")
        return 0

    for path, _old, _new, content in changes:
        path.write_text(content, encoding="utf-8")

    print(f"\nUpdated {len(changes)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
