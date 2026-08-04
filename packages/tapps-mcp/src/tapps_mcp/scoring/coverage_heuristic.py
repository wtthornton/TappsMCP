"""Test-coverage heuristic for the code scorer.

Resolves which test files exercise a scored module, by filename match and
by import scan. Test roots are discovered project-locally and across uv
workspace members — without the second half every top-level file in a
monorepo scores zero coverage no matter how well tested it is (TAP-5619).

Split out of ``scorer.py`` under TAP-5619; ``scorer.py`` re-exports these
names so existing imports keep resolving.
"""

from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from pathlib import Path


def _stem_token_in_name(name: str, stem: str) -> bool:
    """True when *stem* appears as a full underscore-delimited token in *name*."""
    base = name.removesuffix(".py")
    return stem in base.split("_")


_TEST_DIR_NAMES = ("tests", "test", "tests/unit", "tests/integration")


def _workspace_members(root: Path) -> tuple[Path, ...]:
    """Expand `[tool.uv.workspace] members` globs under *root*.

    Returns an empty tuple for a single-package project, which keeps test-root
    discovery exactly as it was before TAP-5619.
    """
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return ()
    try:
        config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ()
    patterns = config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    if not isinstance(patterns, list):
        return ()
    members: list[Path] = []
    for pattern in patterns:
        if not isinstance(pattern, str) or pattern.startswith("/") or ".." in pattern:
            continue
        members.extend(path for path in sorted(root.glob(pattern)) if path.is_dir())
    return tuple(members)


@lru_cache(maxsize=64)
def _test_roots(root: Path) -> tuple[Path, ...]:
    """Directories that may hold tests for code under *root*.

    Project-local `tests/` first, then the same directories under each uv
    workspace member. A monorepo keeps its tests inside the members, so
    without the second half every top-level file — every `scripts/` entry —
    scores zero coverage no matter how well tested it is (TAP-5619).
    """
    bases = [root, *_workspace_members(root)]
    return tuple(
        candidate
        for base in bases
        for name in _TEST_DIR_NAMES
        if (candidate := base / name).is_dir()
    )


def _count_test_files(root: Path, stem: str) -> tuple[int, int]:
    """Count exact and fuzzy test file matches for a module stem.

    Returns (exact_count, fuzzy_count).
    """
    exact_patterns = [f"test_{stem}.py", f"{stem}_test.py"]
    exact_count = 0
    fuzzy_count = 0
    for td_path in _test_roots(root):
        for pat in exact_patterns:
            if (td_path / pat).exists():
                exact_count += 1
        for match in td_path.glob(f"test_*{stem}*.py"):
            if match.name not in exact_patterns and _stem_token_in_name(match.name, stem):
                fuzzy_count += 1
    return exact_count, fuzzy_count


def _import_module_candidates(root: Path, file_path: Path) -> set[str]:
    """Return import names that could refer to *file_path* from tests."""
    stem = file_path.stem
    candidates: set[str] = {stem}
    try:
        rel = file_path.resolve().relative_to(root.resolve())
    except ValueError:
        return candidates
    parts = list(rel.with_suffix("").parts)
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    if len(parts) >= 2 and parts[0] == parts[1]:
        # e.g. packages/tapps_mcp/... unusual; keep as-is
        pass
    if parts:
        candidates.add(".".join(parts))
        candidates.add(parts[-1])
    return candidates


def _text_imports_module(text: str, module: str) -> bool:
    """Return True when *text* contains an import of *module* (cheap regex)."""
    # Match: import mod / import pkg.mod / from mod import X / from pkg.mod import X
    # Also: from pkg import mod (when module is a single token)
    escaped = re.escape(module)
    patterns = (
        rf"(?m)^\s*import\s+{escaped}\b",
        rf"(?m)^\s*from\s+{escaped}\s+import\b",
    )
    if "." not in module:
        patterns = (
            *patterns,
            rf"(?m)^\s*from\s+[\w.]+\s+import\s+\(.*?\b{escaped}\b",
            rf"(?m)^\s*from\s+[\w.]+\s+import\s+[^\n]*\b{escaped}\b",
        )
    return any(re.search(pat, text) for pat in patterns)


def _tests_import_module(root: Path, file_path: Path) -> bool:
    """Return True when any test file imports the module under *file_path*."""
    candidates = _import_module_candidates(root, file_path)
    seen: set[Path] = set()
    for td in _test_roots(root):
        for py in td.rglob("*.py"):
            resolved = py.resolve()
            if resolved in seen or py.name == "__init__.py":
                continue
            seen.add(resolved)
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Fast reject before regex.
            if not any(c in text for c in candidates):
                continue
            if any(_text_imports_module(text, cand) for cand in candidates):
                return True
    return False


def _test_count_to_score(exact_count: int, fuzzy_count: int) -> float:
    """Convert test file counts to a coverage heuristic score."""
    total = exact_count + fuzzy_count
    multi_test_threshold = 2
    if total >= multi_test_threshold:
        return 7.0
    if exact_count >= 1:
        return 5.0
    if fuzzy_count >= 1:
        return 3.0
    return 0.0


def _find_project_root(file_path: Path) -> Path | None:
    """Walk up from *file_path* looking for project markers."""
    current = file_path.resolve().parent
    markers = [".git", "pyproject.toml", "setup.py", "requirements.txt", "package.json"]
    for _ in range(10):
        if any((current / m).exists() for m in markers):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
