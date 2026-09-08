"""File-skeleton queries over the existing call-graph index (LANE_ISSUE).

A pure function of ``CallGraphIndex`` (no LLM, no embeddings, ADR-0004):
given a file path, return every indexed symbol in that file with its
def/class header line. Reuses ``build_call_graph_index`` for the lazy
rebuild every other call-graph tool relies on (``tapps_call_graph``,
``tapps_diff_impact``) so a stale on-disk cache never silently produces a
wrong (empty) skeleton — see module docstring in ``call_graph_queries.py``
for the shared honesty-layer rationale.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from tapps_mcp.project.call_graph_gap_classify import degrades_answer, is_external_gap

if TYPE_CHECKING:
    from tapps_mcp.project.call_graph_types import CallGraphIndex

# Cap on lines scanned when joining a multi-line def/class header, so a
# malformed file (unbalanced parens) can't turn signature reading into an
# unbounded scan.
_MAX_SIGNATURE_LINES = 25


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def _dir_of(path: str) -> str:
    normalized = _normalize(path)
    if "/" not in normalized:
        return "."
    return normalized.rsplit("/", maxsplit=1)[0]


def index_is_empty(index: CallGraphIndex) -> bool:
    """True when *index* has nothing at all — the "missing index" trap.

    ``build_call_graph_index`` always returns *some* index (it walks the
    tree fresh when the on-disk cache is missing or stale), so a genuinely
    unusable index looks like zero symbols, zero edges, and zero parse
    failures — i.e. nothing was found to scan at all (empty/nonexistent
    project root). That is the case a caller must not mistake for "this
    file has no symbols".
    """
    return not index.symbols and not index.edges and not index.parse_failures


def index_completeness(index: CallGraphIndex) -> dict[str, Any]:
    """Index-wide completeness block, same shape family as ``tapps_call_graph``."""
    degrading = [g for g in index.resolution_gaps if degrades_answer(g)]
    external = [g for g in index.resolution_gaps if is_external_gap(g)]
    parse_failed = len(index.parse_failures)
    degraded = parse_failed > 0 or bool(degrading)
    edge_count = len(index.edges)
    return {
        "complete": not degraded,
        "authoritative": not degraded,
        "degraded": degraded,
        "parse_failures": parse_failed,
        "gap_count": len(degrading),
        "external_gap_count": len(external),
        "in_repo_gap_rate": round(len(degrading) / max(edge_count, 1), 3),
    }


def resolve_file_in_index(index: CallGraphIndex, file_path: str) -> tuple[str | None, list[str]]:
    """Resolve *file_path* to an index-relative path.

    An exact relative-path match wins. Otherwise, when *file_path* is an
    unambiguous basename, resolve to the single matching file. Multiple
    matches return the candidate list instead of guessing (never silently
    pick one).
    """
    normalized = _normalize(file_path)
    # ``per_file_fingerprints`` covers every scanned file (TAP-4533), including
    # ones with zero symbols — symbols/parse_failures alone would make a
    # legitimately empty file (e.g. constants-only) indistinguishable from
    # "not in the index at all".
    known: set[str] = {_normalize(p) for p in index.per_file_fingerprints}
    known.update(_normalize(s.file_path) for s in index.symbols)
    known.update(_normalize(f.file_path) for f in index.parse_failures)
    if normalized in known:
        return normalized, []
    basename = normalized.rsplit("/", maxsplit=1)[-1]
    candidates = sorted({p for p in known if p.rsplit("/", maxsplit=1)[-1] == basename})
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


def read_signature(project_root: Path, rel_path: str, line: int) -> str:
    """Read the def/class header at *line* from the working tree.

    Never a body line: starts exactly at *line* (the symbol's recorded
    ``lineno``, which for a def/class node is the header line itself, not a
    decorator) and, for a multi-line parameter list, joins forward only
    until parentheses balance — it never reads past the header into the
    body.
    """
    try:
        text = (project_root / rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    if not (1 <= line <= len(lines)):
        return ""
    parts: list[str] = []
    depth = 0
    for raw in lines[line - 1 : line - 1 + _MAX_SIGNATURE_LINES]:
        stripped = raw.strip()
        parts.append(stripped)
        depth += stripped.count("(") - stripped.count(")")
        if depth <= 0:
            break
    return " ".join(p for p in parts if p).strip()


def query_file_skeleton(
    index: CallGraphIndex, project_root: Path, file_path: str
) -> dict[str, Any]:
    """Every indexed symbol in *file_path*: kind, qualified_name, line, signature."""
    completeness = index_completeness(index)
    if index_is_empty(index):
        return {
            "file_path": file_path,
            "index_status": "unavailable",
            "found": False,
            "ambiguous": False,
            "symbols": [],
            "candidates": [],
            "completeness": completeness,
        }

    resolved, candidates = resolve_file_in_index(index, file_path)
    if resolved is None:
        return {
            "file_path": file_path,
            "index_status": "ready",
            "found": False,
            "ambiguous": bool(candidates),
            "symbols": [],
            "candidates": candidates,
            "completeness": completeness,
        }

    parse_failed = any(_normalize(f.file_path) == resolved for f in index.parse_failures)
    if parse_failed:
        return {
            "file_path": resolved,
            "index_status": "unavailable",
            "found": True,
            "ambiguous": False,
            "reason": "parse_failure",
            "symbols": [],
            "candidates": [],
            "completeness": completeness,
        }

    file_symbols = sorted(
        (s for s in index.symbols if _normalize(s.file_path) == resolved),
        key=lambda s: s.line,
    )
    symbols_out = [
        {
            "kind": s.kind,
            "qualified_name": s.qualified_name,
            "line": s.line,
            "language": s.language,
            "signature": read_signature(project_root, resolved, s.line),
        }
        for s in file_symbols
    ]
    return {
        "file_path": resolved,
        "index_status": "ready",
        "found": True,
        "ambiguous": False,
        "symbols": symbols_out,
        "candidates": [],
        "completeness": completeness,
    }
