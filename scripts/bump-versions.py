#!/usr/bin/env python3
"""Bump versions across all packages in the TappsMCP monorepo atomically.

Usage:
    python scripts/bump-versions.py --patch   # 0.8.0 -> 0.8.1
    python scripts/bump-versions.py --minor   # 0.8.0 -> 0.9.0
    python scripts/bump-versions.py --major   # 0.8.0 -> 1.0.0
    python scripts/bump-versions.py --dry-run --patch  # preview only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Package definitions: (pyproject_path, npm_package_json_path_or_None)
PACKAGES: list[tuple[str, str | None]] = [
    ("packages/tapps-core/pyproject.toml", None),
    ("packages/tapps-mcp/pyproject.toml", "npm/package.json"),
    ("packages/docs-mcp/pyproject.toml", "npm-docs-mcp/package.json"),
]


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch)."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Invalid version: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump(version: str, part: str) -> str:
    """Bump a semver version string by the given part."""
    major, minor, patch = parse_version(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def read_pyproject_version(path: Path) -> str:
    """Read version from a pyproject.toml file."""
    content = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"No version found in {path}")
    return match.group(1)


def update_pyproject_version(path: Path, old_version: str, new_version: str) -> str:
    """Update version in pyproject.toml. Returns updated content."""
    content = path.read_text(encoding="utf-8")
    updated = content.replace(f'version = "{old_version}"', f'version = "{new_version}"', 1)
    if updated == content:
        raise ValueError(f"Failed to replace version in {path}")
    return updated


def read_npm_version(path: Path) -> str:
    """Read version from a package.json file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["version"]


def update_npm_version(path: Path, new_version: str) -> str:
    """Update version in package.json. Returns updated content."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = new_version
    return json.dumps(data, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump versions across TappsMCP monorepo")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--major", action="store_true", help="Bump major version")
    group.add_argument("--minor", action="store_true", help="Bump minor version")
    group.add_argument("--patch", action="store_true", help="Bump patch version")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    part = "major" if args.major else "minor" if args.minor else "patch"

    print(f"Bumping {part} version across all packages...\n")

    changes: list[tuple[Path, str, str, str]] = []  # (path, old, new, content)

    for pyproject_rel, npm_rel in PACKAGES:
        pyproject_path = REPO_ROOT / pyproject_rel
        if not pyproject_path.exists():
            print(f"  SKIP {pyproject_rel} (not found)")
            continue

        old_ver = read_pyproject_version(pyproject_path)
        new_ver = bump(old_ver, part)
        content = update_pyproject_version(pyproject_path, old_ver, new_ver)
        changes.append((pyproject_path, old_ver, new_ver, content))
        print(f"  {pyproject_rel}: {old_ver} -> {new_ver}")

        if npm_rel:
            npm_path = REPO_ROOT / npm_rel
            if npm_path.exists():
                npm_old = read_npm_version(npm_path)
                npm_content = update_npm_version(npm_path, new_ver)
                changes.append((npm_path, npm_old, new_ver, npm_content))
                print(f"  {npm_rel}: {npm_old} -> {new_ver}")
            else:
                print(f"  SKIP {npm_rel} (not found)")

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
