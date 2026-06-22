"""Resolution gap classification: in-repo vs external (TAP-4269)."""

from __future__ import annotations

import builtins
import sys
from functools import lru_cache

from tapps_mcp.project.call_graph_types import ResolutionGap

_EXTERNAL_REASONS = frozenset(
    {
        "dynamic_dispatch",
        "callback_opaque",
        "framework_hof",
        "import_unresolved",
    }
)


@lru_cache(maxsize=1)
def _stdlib_module_names() -> frozenset[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return frozenset(names)
    return frozenset(
        {
            "abc",
            "argparse",
            "ast",
            "asyncio",
            "collections",
            "contextlib",
            "dataclasses",
            "enum",
            "functools",
            "importlib",
            "io",
            "itertools",
            "json",
            "logging",
            "os",
            "pathlib",
            "re",
            "sys",
            "tempfile",
            "time",
            "typing",
            "urllib",
        }
    )


@lru_cache(maxsize=1)
def _builtin_names() -> frozenset[str]:
    return frozenset(name for name in dir(builtins) if not name.startswith("_"))


def expr_root(expr: str) -> str:
    """First identifier token from a call expression string."""
    trimmed = expr.strip()
    if not trimmed or trimmed == "<expr>":
        return ""
    token = trimmed.split("(", maxsplit=1)[0].strip()
    if not token:
        return ""
    return token.split(".", maxsplit=1)[0]


def is_external_gap(gap: ResolutionGap) -> bool:
    """True when the gap is stdlib/builtin/third-party or expected dynamic dispatch."""
    if gap.reason in _EXTERNAL_REASONS:
        return True
    root = expr_root(gap.expr)
    if not root:
        return True
    if root in _builtin_names():
        return True
    if root in _stdlib_module_names():
        return True
    return False


def split_gap_counts(gaps: list[ResolutionGap]) -> tuple[int, int, dict[str, int]]:
    """Return (external_count, in_repo_count, in_repo_reasons)."""
    external = 0
    in_repo = 0
    in_repo_reasons: dict[str, int] = {}
    for gap in gaps:
        if is_external_gap(gap):
            external += 1
            continue
        in_repo += 1
        in_repo_reasons[gap.reason] = in_repo_reasons.get(gap.reason, 0) + 1
    return external, in_repo, dict(sorted(in_repo_reasons.items()))
