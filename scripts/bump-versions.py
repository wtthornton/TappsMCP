#!/usr/bin/env python3
"""Bump versions across all packages in the TappsMCP monorepo atomically.

Usage:
    python scripts/bump-versions.py --patch   # 0.8.0 -> 0.8.1
    python scripts/bump-versions.py --minor   # 0.8.0 -> 0.9.0
    python scripts/bump-versions.py --major   # 0.8.0 -> 1.0.0
    python scripts/bump-versions.py --dry-run --patch  # preview only
    python scripts/bump-versions.py --check   # CI gate: derived files in sync?

The bump bumps `pyproject.toml` and `package.json` for every workspace
package. It ALSO refreshes the AGENTS.md `<!-- tapps-agents-version: X.Y.Z -->`
stamp so a single commit ships everything atomically (TAP-1372). The
canonical hook manifest in `pipeline/upgrade.py` is verified — not
auto-rewritten — and the bump refuses if the manifest references a hook
that has no template, the root cause of the 79ef6e3 / 2e2f378 churn.

`--check` mode (TAP-1378) exits non-zero if AGENTS.md lags tapps-mcp
pyproject or if the manifest references a phantom hook. CI runs this on
every push to master.
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

# tapps-mcp's pyproject is the source of truth for the AGENTS.md stamp.
TAPPS_MCP_PYPROJECT = "packages/tapps-mcp/pyproject.toml"

# Files containing a `<!-- tapps-agents-version: X.Y.Z -->` stamp that must
# match tapps-mcp pyproject. AGENTS.md is the canonical consumer-facing one.
STAMPED_FILES: tuple[str, ...] = ("AGENTS.md",)

_STAMP_RE = re.compile(r"<!--\s*tapps-agents-version:\s*([\d.]+)\s*-->")


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


def read_stamp(path: Path) -> str | None:
    """Return the `<!-- tapps-agents-version: X.Y.Z -->` value, or None."""
    if not path.exists():
        return None
    match = _STAMP_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def rewrite_stamp(path: Path, new_version: str) -> tuple[str | None, str]:
    """Rewrite the version stamp in `path`. Returns (old_stamp, new_content).

    Raises ValueError if `path` has no recognised stamp.
    """
    content = path.read_text(encoding="utf-8")
    match = _STAMP_RE.search(content)
    if not match:
        raise ValueError(f"No tapps-agents-version stamp found in {path}")
    old = match.group(1)
    new_content = _STAMP_RE.sub(f"<!-- tapps-agents-version: {new_version} -->", content, count=1)
    return old, new_content


def all_template_hook_names() -> set[str]:
    """Return every hook script name registered in the templates module.

    Parses the source rather than importing — keeps this script standalone
    so the CI gate runs without `uv sync`.
    """
    src = (
        REPO_ROOT
        / "packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py"
    ).read_text(encoding="utf-8")
    return set(re.findall(r'^    "(tapps-[a-z-]+\.sh)"\s*:', src, flags=re.MULTILINE))


def actual_hook_manifest() -> set[str]:
    """Read the current `_CANONICAL_HOOK_MANIFEST` from pipeline/upgrade.py."""
    src_path = REPO_ROOT / "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py"
    src = src_path.read_text(encoding="utf-8")
    match = re.search(
        r"_CANONICAL_HOOK_MANIFEST:\s*frozenset\[str\]\s*=\s*frozenset\(\{(.*?)\}\)",
        src,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"Could not locate _CANONICAL_HOOK_MANIFEST in {src_path}")
    return set(re.findall(r'"(tapps-[a-z-]+\.sh)"', match.group(1)))


def collect_drift(target_version: str) -> list[str]:
    """Return human-readable drift findings against `target_version`.

    Empty list = in sync. Non-empty = drift; --check exits 1.

    Surfaces:
      - AGENTS.md (and any future stamped file) lagging the tapps-mcp
        pyproject version.
      - `_CANONICAL_HOOK_MANIFEST` containing a phantom hook name that has
        no template (the 79ef6e3 / 2e2f378 root cause). Hook ADDITIONS to
        the templates registry are not flagged automatically — those are
        deliberate and the manifest edit happens in the same commit.
    """
    findings: list[str] = []

    for rel in STAMPED_FILES:
        path = REPO_ROOT / rel
        stamp = read_stamp(path)
        if stamp is None:
            findings.append(f"{rel}: missing tapps-agents-version stamp")
        elif stamp != target_version:
            findings.append(f"{rel}: stamp {stamp} != pyproject {target_version}")

    # Unified-versioning gate: every workspace pyproject must match
    # tapps-mcp's version. Per-package independent bumps drift every
    # release (this script's previous behaviour produced a 3.10.9 vs
    # 3.10.1 split between tapps-mcp and tapps-core / docs-mcp); the
    # gate forces a future re-sync rather than letting the gap grow.
    for pyproject_rel, npm_rel in PACKAGES:
        if pyproject_rel == TAPPS_MCP_PYPROJECT:
            continue
        path = REPO_ROOT / pyproject_rel
        if not path.exists():
            continue
        ver = read_pyproject_version(path)
        if ver != target_version:
            findings.append(
                f"{pyproject_rel}: {ver} != tapps-mcp {target_version} (run --sync)"
            )
        if npm_rel:
            npm_path = REPO_ROOT / npm_rel
            if npm_path.exists():
                npm_ver = read_npm_version(npm_path)
                if npm_ver != target_version:
                    findings.append(
                        f"{npm_rel}: {npm_ver} != tapps-mcp {target_version} (run --sync)"
                    )

    templates = all_template_hook_names()
    actual = actual_hook_manifest()
    phantom = sorted(actual - templates)
    if phantom:
        findings.append(
            f"_CANONICAL_HOOK_MANIFEST lists {phantom} but no template exists for them"
        )

    return findings


def run_check() -> int:
    """CI gate: exit 0 if all derived files match tapps-mcp pyproject."""
    target = read_pyproject_version(REPO_ROOT / TAPPS_MCP_PYPROJECT)
    findings = collect_drift(target)
    if not findings:
        print(f"OK: all derived files in sync with tapps-mcp {target}")
        return 0
    print(f"DRIFT against tapps-mcp {target}:")
    for f in findings:
        print(f"  - {f}")
    print(
        "\nFix: run `python scripts/bump-versions.py --patch` (or rerun the "
        "appropriate bump) so derived files are refreshed in the same commit."
    )
    return 1


def _max_current_version() -> str:
    """Return the highest version currently set across all packages.

    Used as the bump origin so all packages converge on a single new
    version, not an independent per-package bump that drifts each release.
    """
    versions: list[tuple[int, int, int]] = []
    for pyproject_rel, _ in PACKAGES:
        path = REPO_ROOT / pyproject_rel
        if path.exists():
            versions.append(parse_version(read_pyproject_version(path)))
    if not versions:
        raise SystemExit("No pyproject.toml files found.")
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch}"


def collect_bump_changes(part: str | None) -> list[tuple[Path, str, str, str]]:
    """Compute every (path, old, new, content) needed for an atomic bump.

    Unified versioning: all three packages converge on a single new version.
    The bump is computed once from `max(current versions)` and applied to
    every pyproject + npm package + the AGENTS.md stamp. With `part=None`
    (the --sync mode) we just align everything to the current max without
    bumping — used when the packages have drifted to different versions
    and need to re-synchronise.
    """
    changes: list[tuple[Path, str, str, str]] = []
    target_version = _max_current_version() if part is None else bump(_max_current_version(), part)
    new_tapps_mcp_version: str | None = None

    for pyproject_rel, npm_rel in PACKAGES:
        pyproject_path = REPO_ROOT / pyproject_rel
        if not pyproject_path.exists():
            print(f"  SKIP {pyproject_rel} (not found)")
            continue

        old_ver = read_pyproject_version(pyproject_path)
        if old_ver != target_version:
            content = update_pyproject_version(pyproject_path, old_ver, target_version)
            changes.append((pyproject_path, old_ver, target_version, content))
            print(f"  {pyproject_rel}: {old_ver} -> {target_version}")
        else:
            print(f"  {pyproject_rel}: {old_ver} (already at target)")

        if pyproject_rel == TAPPS_MCP_PYPROJECT:
            new_tapps_mcp_version = target_version

        if npm_rel:
            npm_path = REPO_ROOT / npm_rel
            if npm_path.exists():
                npm_old = read_npm_version(npm_path)
                if npm_old != target_version:
                    npm_content = update_npm_version(npm_path, target_version)
                    changes.append((npm_path, npm_old, target_version, npm_content))
                    print(f"  {npm_rel}: {npm_old} -> {target_version}")
                else:
                    print(f"  {npm_rel}: {npm_old} (already at target)")
            else:
                print(f"  SKIP {npm_rel} (not found)")

    if new_tapps_mcp_version is None:
        return changes

    # Refresh derived files: AGENTS.md stamp + canonical hook manifest.
    for stamped_rel in STAMPED_FILES:
        stamped_path = REPO_ROOT / stamped_rel
        if not stamped_path.exists():
            print(f"  SKIP {stamped_rel} (not found)")
            continue
        old_stamp, new_content = rewrite_stamp(stamped_path, new_tapps_mcp_version)
        changes.append((stamped_path, old_stamp or "<none>", new_tapps_mcp_version, new_content))
        print(f"  {stamped_rel} stamp: {old_stamp} -> {new_tapps_mcp_version}")

    # Manifest verification (TAP-1378): refuse the bump if the manifest
    # references a hook name with no template — that's the 79ef6e3 /
    # 2e2f378 root cause. Force the human to fix the manifest in the
    # same commit so the bump is still atomic.
    templates = all_template_hook_names()
    actual = actual_hook_manifest()
    phantom = sorted(actual - templates)
    if phantom:
        raise SystemExit(
            f"BUMP REFUSED: _CANONICAL_HOOK_MANIFEST in pipeline/upgrade.py "
            f"lists {phantom} but no template exists for them. Fix the "
            f"manifest first, then re-run the bump so the change ships in "
            f"a single commit."
        )

    return changes


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
