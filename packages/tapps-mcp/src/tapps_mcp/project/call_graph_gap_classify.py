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

# TypeScript (TAP-4539). A TS gap must NOT be run through the Python
# stdlib/builtin name checks: `fs`/`lodash` are not in Python's stdlib set (so
# they would wrongly count as in-repo), and Python stdlib names like `os`/`time`
# are not TS externals. The reason field alone decides external vs in-repo:
#  - external: an unresolvable import from outside the repo (`fs`, `lodash`) or
#    an inherently non-static call.
#  - in-repo (deferred to S4): default-export / re-export / path-alias / typed-
#    receiver gaps — real in-repo edges we cannot draw yet. Counting them
#    in-repo keeps `in_repo_gap_rate` honest about resolution debt.
_TS_EXTERNAL_REASONS = frozenset(
    {
        "import_unresolved",
        "dynamic_dispatch",
        "callback_opaque",
        "framework_hof",
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
    """True when the gap is stdlib/builtin/third-party or expected dynamic dispatch.

    Language-aware (TAP-4539): a TypeScript gap is classified purely on its
    ``reason`` — the Python stdlib/builtin name heuristics do not transfer to
    TS and would misclassify both directions (see ``_TS_EXTERNAL_REASONS``).
    """
    language = getattr(gap, "language", "python")
    if language == "typescript":
        return gap.reason in _TS_EXTERNAL_REASONS
    if gap.reason in _EXTERNAL_REASONS:
        return True
    root = expr_root(gap.expr)
    if not root:
        return True
    if root in _builtin_names():
        return True
    return root in _stdlib_module_names()


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
