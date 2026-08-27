"""Version bumping and drift checking for the TappsMCP monorepo.

The bump rewrites `pyproject.toml` and `package.json` for every workspace
package and refreshes the AGENTS.md / CLAUDE.md `<!-- tapps-agents-version:
X.Y.Z -->` stamps, so one commit ships everything atomically (TAP-1372). The
canonical hook manifest in `pipeline/upgrade.py` is verified — not
auto-rewritten — and the bump refuses if the manifest references a hook with
no template, the root cause of the 79ef6e3 / 2e2f378 churn.

`run_check` (TAP-1378) reports drift: AGENTS.md lagging the tapps-mcp
pyproject, or a phantom hook in the manifest. The pre-push hook and CI run it
on every push to master.

`scripts/bump-versions.py` is the CLI entry point. The logic lives here so it
is importable under a valid module name and testable from pytest (TAP-5621).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Package definitions: (pyproject_path, npm_package_json_path_or_None)
PACKAGES: list[tuple[str, str | None]] = [
    ("packages/tapps-core/pyproject.toml", None),
    ("packages/tapps-mcp/pyproject.toml", "npm/package.json"),
    ("packages/docs-mcp/pyproject.toml", "npm-docs-mcp/package.json"),
]

# tapps-mcp's pyproject is the source of truth for the AGENTS.md / CLAUDE.md stamps.
TAPPS_MCP_PYPROJECT = "packages/tapps-mcp/pyproject.toml"

# TAP-5876: internal-package dependency specs that must stay exact-pinned
# (`"<dep>==<version>"`) to the unified workspace version. `[tool.uv.sources]
# workspace = true` is a uv-only override — plain pip resolves these lines
# straight from public PyPI, where a same-named unrelated project can exist
# ("docs-mcp" already does). An exact pin can only ever match this
# workspace's own version, so a public-package mismatch makes pip fail
# loudly instead of silently substituting. Each entry is
# ``(pyproject_rel, dependency_name)``.
INTERNAL_PINS: tuple[tuple[str, str], ...] = (
    ("packages/tapps-mcp/pyproject.toml", "tapps-core"),
    ("packages/tapps-mcp/pyproject.toml", "docs-mcp"),
    ("packages/docs-mcp/pyproject.toml", "tapps-core"),
)

_PIN_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _internal_pin_regex(dep_name: str) -> re.Pattern[str]:
    """Return (and cache) a regex matching ``"<dep_name>==X.Y.Z"``."""
    if dep_name not in _PIN_RE_CACHE:
        _PIN_RE_CACHE[dep_name] = re.compile(rf'"{re.escape(dep_name)}==([\d.]+)"')
    return _PIN_RE_CACHE[dep_name]


def read_internal_pin(path: Path, dep_name: str) -> str | None:
    """Return the exact-pinned version for *dep_name* in *path*, or None if absent."""
    if not path.exists():
        return None
    match = _internal_pin_regex(dep_name).search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None

# Files containing a TappsMCP version stamp that must match tapps-mcp pyproject.
# Each entry is ``(relative_path, stamp_key)`` where stamp_key is the HTML
# comment marker name (without surrounding ``<!-- ... -->``).
# TAP-2334 added the CLAUDE.md stamp alongside the AGENTS.md stamp so both
# refresh atomically per bump.
STAMPED_FILES: tuple[tuple[str, str], ...] = (
    ("AGENTS.md", "tapps-agents-version"),
    ("CLAUDE.md", "tapps-claude-version"),
)

_STAMP_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _stamp_regex(key: str) -> re.Pattern[str]:
    """Return (and cache) a regex matching ``<!-- <key>: X.Y.Z -->``."""
    if key not in _STAMP_RE_CACHE:
        _STAMP_RE_CACHE[key] = re.compile(rf"<!--\s*{re.escape(key)}:\s*([\d.]+)\s*-->")
    return _STAMP_RE_CACHE[key]


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


def read_npm_version(path: Path) -> str:
    """Read version from a package.json file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["version"]


def update_npm_version(path: Path, new_version: str) -> str:
    """Update version in package.json. Returns updated content."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = new_version
    return json.dumps(data, indent=2) + "\n"


def read_stamp(path: Path, stamp_key: str) -> str | None:
    """Return the ``<!-- <stamp_key>: X.Y.Z -->`` value, or None."""
    if not path.exists():
        return None
    match = _stamp_regex(stamp_key).search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def rewrite_stamp(path: Path, stamp_key: str, new_version: str) -> tuple[str | None, str]:
    """Rewrite the named version stamp in *path*. Returns (old_stamp, new_content).

    Raises ValueError if *path* has no matching stamp.
    """
    content = path.read_text(encoding="utf-8")
    regex = _stamp_regex(stamp_key)
    match = regex.search(content)
    if not match:
        raise ValueError(f"No {stamp_key} stamp found in {path}")
    old = match.group(1)
    new_content = regex.sub(f"<!-- {stamp_key}: {new_version} -->", content, count=1)
    return old, new_content


def all_template_hook_names() -> set[str]:
    """Return every hook script name registered in the templates module.

    Parses the source rather than importing — keeps this script standalone
    so the CI gate runs without `uv sync`.
    """
    src = (
        REPO_ROOT / "packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py"
    ).read_text(encoding="utf-8")
    return set(re.findall(r'^    "(tapps-[a-z-]+\.sh)"\s*:', src, flags=re.MULTILINE))


def actual_hook_manifest() -> set[str]:
    """Read the current `_CANONICAL_HOOK_MANIFEST` from pipeline/upgrade.py."""
    src_path = REPO_ROOT / "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py"
    src = src_path.read_text(encoding="utf-8")
    match = re.search(
        # Tolerate ruff's formatting: frozenset( <newline+indent> { ... } <newline> )
        r"_CANONICAL_HOOK_MANIFEST:\s*frozenset\[str\]\s*=\s*frozenset\(\s*\{(.*?)\}\s*\)",
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

    for rel, stamp_key in STAMPED_FILES:
        path = REPO_ROOT / rel
        stamp = read_stamp(path, stamp_key)
        if stamp is None:
            findings.append(f"{rel}: missing {stamp_key} stamp")
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
            findings.append(f"{pyproject_rel}: {ver} != tapps-mcp {target_version} (run --sync)")
        if npm_rel:
            npm_path = REPO_ROOT / npm_rel
            if npm_path.exists():
                npm_ver = read_npm_version(npm_path)
                if npm_ver != target_version:
                    findings.append(
                        f"{npm_rel}: {npm_ver} != tapps-mcp {target_version} (run --sync)"
                    )

    # TAP-5876: internal-package pins must exact-match the unified version —
    # a stale pin either breaks `uv sync` (pin behind the workspace member's
    # actual version) or, worse, silently re-widens the window in which a
    # plain `pip install` could land on a same-named public PyPI package.
    for pin_rel, dep_name in INTERNAL_PINS:
        path = REPO_ROOT / pin_rel
        if not path.exists():
            continue
        pin_ver = read_internal_pin(path, dep_name)
        if pin_ver is None:
            findings.append(
                f'{pin_rel}: no "{dep_name}==..." exact pin found '
                f"(TAP-5876 dependency-confusion guard missing)"
            )
        elif pin_ver != target_version:
            findings.append(
                f"{pin_rel}: {dep_name} pin {pin_ver} != tapps-mcp {target_version} (run --sync)"
            )

    templates = all_template_hook_names()
    actual = actual_hook_manifest()
    phantom = sorted(actual - templates)
    if phantom:
        findings.append(f"_CANONICAL_HOOK_MANIFEST lists {phantom} but no template exists for them")

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
        content = pyproject_path.read_text(encoding="utf-8")
        file_changed = False
        if old_ver != target_version:
            updated = content.replace(f'version = "{old_ver}"', f'version = "{target_version}"', 1)
            if updated == content:
                raise ValueError(f"Failed to replace version in {pyproject_path}")
            content = updated
            file_changed = True
            print(f"  {pyproject_rel}: {old_ver} -> {target_version}")
        else:
            print(f"  {pyproject_rel}: {old_ver} (already at target)")

        # TAP-5876: keep internal-package exact pins in lockstep with the
        # unified version in the same file write — a separate write to this
        # path would clobber whichever change ran last.
        for pin_rel, dep_name in INTERNAL_PINS:
            if pin_rel != pyproject_rel:
                continue
            pin_regex = _internal_pin_regex(dep_name)
            pin_match = pin_regex.search(content)
            if not pin_match:
                raise ValueError(f'No "{dep_name}==..." pin found in {pyproject_path}')
            old_pin = pin_match.group(1)
            if old_pin != target_version:
                content = pin_regex.sub(f'"{dep_name}=={target_version}"', content, count=1)
                file_changed = True
                print(f"  {pyproject_rel}: {dep_name} pin {old_pin} -> {target_version}")

        if file_changed:
            changes.append((pyproject_path, old_ver, target_version, content))

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

    # Refresh derived files: AGENTS.md + CLAUDE.md stamps + canonical hook manifest.
    for stamped_rel, stamp_key in STAMPED_FILES:
        stamped_path = REPO_ROOT / stamped_rel
        if not stamped_path.exists():
            print(f"  SKIP {stamped_rel} (not found)")
            continue
        try:
            old_stamp, new_content = rewrite_stamp(stamped_path, stamp_key, new_tapps_mcp_version)
        except ValueError:
            print(f"  SKIP {stamped_rel} ({stamp_key} stamp not found)")
            continue
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
