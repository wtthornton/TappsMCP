"""Shared scan-filter helpers for documentation validators.

Pure, deterministic helpers for excluding paths from recursive filesystem
scans. Provides:

- A small internal ``.gitignore`` reader (root-level only -- see module
  notes below) that returns a raw pattern list.
- A predicate that decides whether a relative path should be excluded,
  taking a baseline of always-skipped dirs (``.venv``, ``node_modules``,
  ``dist``, ...) plus gitignore patterns plus caller-supplied extras.

The matcher uses :mod:`fnmatch` / :func:`pathlib.PurePosixPath.match` --
we did NOT add ``pathspec`` as a dependency because the common cases the
callers care about (``.venv-release-smoke/``, ``vendored/**/*``) are
trivially expressible with glob patterns.

Supported pattern syntax (best-effort subset of ``.gitignore``):

- ``pattern`` -- matches any file/dir segment equal to ``pattern`` in any
  location (e.g. ``*.log``, ``__pycache__``).
- ``pattern/`` -- matches directories only (we match both the directory
  and everything beneath it).
- ``/pattern`` -- anchored to the root (matches only at the project root,
  not in nested dirs).
- ``dir/sub`` / ``dir/**/file`` -- multi-segment globs via
  :meth:`pathlib.PurePosixPath.match`.

Not supported (documented so callers don't silently rely on it):

- Negation patterns (``!foo``) -- ignored.
- Nested ``.gitignore`` files below the project root -- only the
  root-level file is read. For most projects this is enough; nested
  support can be added later without a breaking API change.
- Character classes beyond what :mod:`fnmatch` natively supports.

All functions here are pure and take no I/O beyond the single gitignore
read in :func:`load_gitignore_patterns`. No logging in hot loops --
callers that want structured logs should add it at the boundary.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

__all__ = [
    "BASELINE_EXCLUDE_DIRS",
    "load_gitignore_patterns",
    "should_exclude",
]

# Always-excluded directory names. These apply regardless of whether
# ``respect_gitignore`` is True or False -- scanning inside a virtualenv
# or build artifact directory is never what a documentation validator
# wants, even if the caller forgot to list them.
BASELINE_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".venv-*",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".eggs",
)


def load_gitignore_patterns(project_root: Path) -> list[str]:
    """Read the project-root ``.gitignore`` and return its patterns.

    Only the root-level ``.gitignore`` is read; nested ``.gitignore``
    files inside subdirectories are currently ignored. Comments (lines
    starting with ``#``), blank lines, and negation lines (``!...``) are
    skipped. Leading/trailing whitespace is stripped.

    If the file does not exist or cannot be read, an empty list is
    returned -- this is not an error.
    """
    gitignore = project_root / ".gitignore"
    if not gitignore.is_file():
        return []

    patterns: list[str] = []
    try:
        raw = gitignore.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            # Negation not supported -- skip rather than confusing the
            # matcher. Documented in the module docstring.
            continue
        patterns.append(stripped)

    return patterns


def _pattern_matches(rel_path: str, pattern: str) -> bool:
    """Return True if ``rel_path`` matches ``pattern``.

    ``rel_path`` is expected to use forward slashes. ``pattern`` follows
    the subset of ``.gitignore`` syntax documented at module level.
    """
    if not pattern:
        return False

    # Anchored to project root: strip leading / and require a match
    # only at the start of the path.
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern.lstrip("/")

    # Directory-only pattern: trailing slash means "match this dir and
    # everything beneath it".
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern.rstrip("/")

    if not pattern:
        return False

    posix = PurePosixPath(rel_path)
    parts = posix.parts

    # Case 1: anchored match -- only look at the root of rel_path.
    # Use fnmatch against the full path rather than PurePosixPath.match
    # (which is right-anchored and would match ``pkg/special`` against
    # ``special``).
    if anchored:
        if fnmatch.fnmatchcase(rel_path, pattern):
            return True
        if dir_only and _under_prefix(rel_path, pattern):
            return True
        return False

    # Case 2: pattern contains a slash -- treat as a path-style glob.
    if "/" in pattern:
        if _glob_match(rel_path, pattern):
            return True
        # ``foo/**/*`` and similar should also match ``foo/x`` (any
        # descendant of ``foo/``). Use prefix matching on the pattern's
        # literal prefix (everything up to the first ``*``).
        if _prefix_match(rel_path, pattern):
            return True
        if dir_only and _under_prefix(rel_path, pattern):
            return True
        return False

    # Case 3: simple segment pattern -- match any path component.
    for part in parts:
        if fnmatch.fnmatchcase(part, pattern):
            return True
    return False


def _glob_match(rel_path: str, pattern: str) -> bool:
    """Match ``rel_path`` against a slash-aware glob pattern."""
    posix = PurePosixPath(rel_path)
    try:
        if posix.match(pattern):
            return True
    except ValueError:
        # PurePosixPath.match rejects some patterns; fall back.
        pass
    # fnmatch with forward-slash preserved gives us ``**`` support via
    # literal ``*`` expansion. It's not perfect but covers the cases
    # we care about (e.g. ``vendored/**/*``).
    return fnmatch.fnmatchcase(rel_path, pattern)


def _prefix_match(rel_path: str, pattern: str) -> bool:
    """Match when the pattern's literal prefix covers ``rel_path``.

    Used for patterns like ``vendored/**/*`` that should also catch
    direct children of the prefix (``vendored/x.md``), which strict
    pathlib matching rejects. The literal prefix is everything up to
    the first glob metachar (``*`` or ``?``).
    """
    literal_end = len(pattern)
    for i, ch in enumerate(pattern):
        if ch in ("*", "?", "["):
            literal_end = i
            break
    literal = pattern[:literal_end].rstrip("/")
    if not literal:
        return False
    return _under_prefix(rel_path, literal) or rel_path == literal


def _under_prefix(rel_path: str, prefix: str) -> bool:
    """Return True if ``rel_path`` is within the directory ``prefix``.

    Both arguments use forward slashes. Matching is glob-aware at the
    first segment of ``prefix`` so that patterns like ``.venv-*`` work
    as directory prefixes.
    """
    prefix_parts = PurePosixPath(prefix).parts
    path_parts = PurePosixPath(rel_path).parts
    if len(path_parts) <= len(prefix_parts):
        return False
    for pp, ap in zip(prefix_parts, path_parts, strict=False):
        if not fnmatch.fnmatchcase(ap, pp):
            return False
    return True


def should_exclude(
    rel_path: str,
    patterns: list[str],
    extra_exclude: list[str],
) -> bool:
    """Return True if ``rel_path`` should be skipped.

    Args:
        rel_path: Forward-slash relative path from the project root
            (e.g. ``".venv-release-smoke/lib/README.md"``).
        patterns: Gitignore-style patterns (typically from
            :func:`load_gitignore_patterns`).
        extra_exclude: Caller-supplied glob patterns, applied on top of
            baseline + gitignore.

    The baseline :data:`BASELINE_EXCLUDE_DIRS` is always applied, even
    when ``patterns`` and ``extra_exclude`` are both empty.
    """
    if not rel_path or rel_path in (".", ""):
        return False

    # Normalize to forward slashes -- callers on Windows may pass
    # backslashes.
    normalized = rel_path.replace("\\", "/")

    # Baseline: any path segment matching an always-skip name.
    parts = PurePosixPath(normalized).parts
    for part in parts:
        for base in BASELINE_EXCLUDE_DIRS:
            if fnmatch.fnmatchcase(part, base):
                return True

    for pattern in patterns:
        if _pattern_matches(normalized, pattern):
            return True

    for pattern in extra_exclude:
        if _pattern_matches(normalized, pattern):
            return True

    return False
