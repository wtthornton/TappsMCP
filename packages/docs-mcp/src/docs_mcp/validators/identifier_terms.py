"""Collect likely project-specific terms from Python source identifiers (Epic 84.3).

Deterministic, bounded scan: no LLM, no network. Used to reduce false positives
in style rules (jargon, heading case) for names that legitimately appear in docs.
"""

from __future__ import annotations

import re
from pathlib import Path

from docs_mcp.constants import SKIP_DIRS

_DEFAULT_MAX_FILES = 120
_DEFAULT_MAX_TERMS = 80
_MIN_TERM_LEN = 3
_MIN_DEF_NAME_LEN = 6

_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")
_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")

# Lowercase tokens to drop (common English / Python noise).
_BLOCKLIST: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "not",
        "with",
        "from",
        "this",
        "that",
        "when",
        "then",
        "else",
        "elif",
        "try",
        "except",
        "finally",
        "raise",
        "pass",
        "import",
        "as",
        "true",
        "false",
        "none",
        "self",
        "cls",
        "args",
        "kwargs",
        "mcs",
        "new",
        "get",
        "set",
        "put",
        "run",
        "main",
        "data",
        "info",
        "item",
        "items",
        "key",
        "keys",
        "val",
        "value",
        "values",
        "list",
        "dict",
        "obj",
        "old",
        "str",
        "int",
        "bool",
        "float",
        "type",
        "types",
        "error",
        "errors",
        "err",
        "helper",
        "helpers",
        "utils",
        "util",
        "base",
        "mixin",
        "meta",
        "abc",
        "impl",
        "factory",
        "mock",
        "patch",
        "test",
        "tests",
        "case",
        "setup",
        "teardown",
        "fixture",
        "config",
        "opts",
        "opt",
        "ctx",
        "req",
        "res",
        "resp",
        "http",
        "url",
        "uri",
        "api",
        "cli",
        "uid",
        "id",
        "idx",
        "num",
        "count",
        "size",
        "len",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "map",
        "filter",
        "open",
        "read",
        "write",
        "path",
        "file",
        "name",
        "names",
        "text",
        "body",
        "head",
        "tail",
        "node",
        "root",
        "child",
        "parent",
        "left",
        "right",
        "next",
        "prev",
        "first",
        "last",
        "start",
        "end",
        "step",
        "init",
        "call",
        "wrap",
        "inner",
        "outer",
    }
)


def _split_camel(name: str) -> list[str]:
    """Split ``MyHTTPClient``-style names into word-ish segments."""
    spaced = _CAMEL_BOUNDARY.sub(" ", name)
    return [p for p in spaced.split() if p]


def _add_term(
    raw: str,
    seen: set[str],
    out: list[str],
    *,
    max_terms: int,
) -> bool:
    """Append *raw* if acceptable. Returns True if *max_terms* reached."""
    t = raw.strip("_")
    if len(t) < _MIN_TERM_LEN:
        return False
    if not t.isascii():
        return False
    lower = t.lower()
    if lower in _BLOCKLIST:
        return False
    if lower in seen:
        return False
    seen.add(lower)
    out.append(t)
    return len(out) >= max_terms


def collect_identifier_terms(
    project_root: Path,
    *,
    max_files: int = _DEFAULT_MAX_FILES,
    max_terms: int = _DEFAULT_MAX_TERMS,
) -> list[str]:
    """Walk Python files under *project_root* and collect identifier tokens.

    - Class names: full name plus CamelCase segments.
    - Function names: full ``snake_case`` name when length ≥ 6 (skips ``test_*``).

    Stops after *max_files* Python files read or *max_terms* terms collected.
    """
    root = project_root.resolve()
    seen: set[str] = set()
    out: list[str] = []
    files_read = 0

    paths = sorted(root.rglob("*.py"))
    for path in paths:
        if files_read >= max_files:
            break
        if any(p in SKIP_DIRS for p in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_read += 1

        for line in text.splitlines():
            if len(out) >= max_terms:
                return out

            cm = _CLASS_RE.match(line)
            if cm:
                name = cm.group(1)
                if name.startswith("_"):
                    continue
                if _add_term(name, seen, out, max_terms=max_terms):
                    return out
                if any(c.isupper() for c in name):
                    for part in _split_camel(name):
                        if _add_term(part, seen, out, max_terms=max_terms):
                            return out
                continue

            dm = _DEF_RE.match(line)
            if dm:
                name = dm.group(1)
                if name.startswith("_") or name.startswith("test"):
                    continue
                if len(name) < _MIN_DEF_NAME_LEN:
                    continue
                if _add_term(name, seen, out, max_terms=max_terms):
                    return out

    return out
