"""Resolution gap classification: in-repo vs external (TAP-4269)."""

from __future__ import annotations

import builtins
import sys
from collections.abc import Iterable
from dataclasses import replace
from functools import lru_cache

from tapps_mcp.project.call_graph_types import ResolutionGap

_EXTERNAL_REASONS = frozenset(
    {
        "dynamic_dispatch",
        "callback_opaque",
        "framework_hof",
        "import_unresolved",
        # TAP-6439: proven to have no in-repo target (see
        # ``reclassify_external_attr_gaps``) — not resolution debt.
        "external_attr_call",
    }
)

# TAP-6439. Gaps that could still be hiding an in-repo edge, so a query answer
# that contains one is genuinely incomplete even though the gap is not
# *resolvable* debt. Distinct from ``_EXTERNAL_REASONS``: these are excluded
# from ``in_repo_gap_rate`` (nothing to fix) but must keep ``degraded=True`` on
# a per-symbol answer (something may be missing). See ``degrades_answer``.
_UNRESOLVABLE_BUT_INCOMPLETE = frozenset(
    {
        "dynamic_dispatch",
        "callback_opaque",
        "framework_hof",
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


def called_name(expr: str) -> str:
    """Final called identifier of a call expression (``a.b.foo`` -> ``foo``)."""
    head = expr.split("(", maxsplit=1)[0].strip()
    return head.rsplit(".", maxsplit=1)[-1] if head else ""


def _is_attribute_call(expr: str) -> bool:
    """True when the call target is an attribute access (``recv.attr``)."""
    return "." in expr.split("(", maxsplit=1)[0]


def reclassify_external_attr_gaps(
    gaps: list[ResolutionGap],
    symbol_names: Iterable[str],
) -> list[ResolutionGap]:
    """Re-label attribute-call gaps that provably cannot be in-repo edges (TAP-6439).

    ``is_external_gap`` decides in-repo vs external from the *root* token of the
    call expression (``os.getcwd`` -> ``os``). That only works for
    module-qualified calls. It cannot see the dominant form in real Python —
    an instance-method call on a local whose type is unknown (``lines.append``,
    ``path.read_text``, ``logger.info``). Those all took the in-repo branch, so
    stdlib/builtin/third-party receivers inflated ``in_repo_gap_rate`` (measured
    on this repo: 12,720 of 18,184 such gaps, rate 0.471).

    The classifier lacks one piece of information the index has: the set of
    names the repo actually defines. An unresolved ``recv.attr()`` can only ever
    become an in-repo edge if *some* in-repo function or method is named
    ``attr``. When no such symbol exists, no sound resolver could ever draw that
    edge, so counting it as resolution debt is simply wrong — it is re-labelled
    ``external_attr_call``.

    Sound in the direction that matters: it never fabricates an edge, and a name
    collision (``dict.get`` vs an in-repo ``get``) keeps the gap counted as
    in-repo — over-counting debt, never under-counting it.

    Returns a NEW list; input gaps are not mutated, so the per-file raw material
    that ``update_call_graph_index`` persists stays at its original reason and the
    derived label is recomputed on every finalize (byte-equivalence, ADR-0004).
    """
    simple_names = {name.rsplit(".", maxsplit=1)[-1] for name in symbol_names}
    out: list[ResolutionGap] = []
    for gap in gaps:
        if (
            getattr(gap, "language", "python") == "python"
            and gap.reason == "unresolved_static_call"
            and _is_attribute_call(gap.expr)
            and called_name(gap.expr) not in simple_names
        ):
            out.append(replace(gap, reason="external_attr_call"))
            continue
        out.append(gap)
    return out


def degrades_answer(gap: ResolutionGap) -> bool:
    """True when *gap* could be hiding an in-repo edge from a query answer.

    Deliberately not the same question as ``is_external_gap`` (TAP-6439):

    * ``is_external_gap`` answers "is this resolution debt we could fix?" — it
      drives ``in_repo_gap_rate``, so inherently unresolvable call forms
      (``getattr(obj, name)()``) are excluded: there is nothing to fix.
    * this answers "may the callers/callees list for this symbol be missing an
      in-repo edge?" — it drives per-query ``degraded``. A ``getattr`` call
      site *might* have targeted an in-repo method, so the answer is incomplete
      even though the gap is not fixable.

    Collapsing the two is what made ``tapps_call_graph`` report ``degraded`` on
    89% of calls: every gap degraded the answer, and almost every function calls
    ``len()`` or ``lines.append()``.
    """
    if gap.reason in _UNRESOLVABLE_BUT_INCOMPLETE:
        return True
    return not is_external_gap(gap)
