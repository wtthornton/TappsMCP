"""Read-only call graph adapter for DocsMCP (TAP-4271).

Loads ``.tapps-mcp/call-graph-index.json`` without importing tapps-mcp so
doc generators can include used-by / depends-on sections from CALLS edges.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

CALL_GRAPH_CACHE_REL = ".tapps-mcp/call-graph-index.json"


@dataclass(frozen=True)
class CallGraphSnapshot:
    symbols: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    stale: bool = False
    missing: bool = False


def load_call_graph_snapshot(project_root: Path) -> CallGraphSnapshot | None:
    """Load call graph index JSON; return None when unreadable."""
    path = project_root / CALL_GRAPH_CACHE_REL
    if not path.is_file():
        return CallGraphSnapshot(symbols=(), edges=(), missing=True)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.debug("call_graph_adapter_read_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    symbols = tuple(
        str(s.get("qualified_name", ""))
        for s in raw.get("symbols", [])
        if isinstance(s, dict) and s.get("qualified_name")
    )
    edges = tuple(
        (str(e.get("caller", "")), str(e.get("callee", "")))
        for e in raw.get("edges", [])
        if isinstance(e, dict) and e.get("caller") and e.get("callee")
    )
    return CallGraphSnapshot(symbols=symbols, edges=edges)


def _symbols_for_module(snapshot: CallGraphSnapshot, module: str) -> set[str]:
    prefix = f"{module}."
    return {name for name in snapshot.symbols if name == module or name.startswith(prefix)}


def module_used_by(project_root: Path, module: str, *, limit: int = 20) -> dict[str, Any]:
    """Compact callers of symbols defined in *module*."""
    snapshot = load_call_graph_snapshot(project_root)
    if snapshot is None:
        return {"available": False, "reason": "unreadable"}
    if snapshot.missing:
        return {"available": False, "reason": "missing_index"}
    module_symbols = _symbols_for_module(snapshot, module)
    if not module_symbols:
        return {"available": True, "module": module, "used_by": []}
    used_by: list[dict[str, str]] = []
    seen: set[str] = set()
    for caller, callee in snapshot.edges:
        if callee not in module_symbols:
            continue
        if caller in seen:
            continue
        seen.add(caller)
        used_by.append({"caller": caller, "callee": callee})
        if len(used_by) >= limit:
            break
    return {"available": True, "module": module, "used_by": used_by}


def module_depends_on(project_root: Path, module: str, *, limit: int = 20) -> dict[str, Any]:
    """Compact callees invoked from symbols defined in *module*."""
    snapshot = load_call_graph_snapshot(project_root)
    if snapshot is None:
        return {"available": False, "reason": "unreadable"}
    if snapshot.missing:
        return {"available": False, "reason": "missing_index"}
    module_symbols = _symbols_for_module(snapshot, module)
    if not module_symbols:
        return {"available": True, "module": module, "depends_on": []}
    depends_on: list[dict[str, str]] = []
    seen: set[str] = set()
    for caller, callee in snapshot.edges:
        if caller not in module_symbols:
            continue
        if callee in seen:
            continue
        seen.add(callee)
        depends_on.append({"caller": caller, "callee": callee})
        if len(depends_on) >= limit:
            break
    return {"available": True, "module": module, "depends_on": depends_on}


def symbol_used_by(project_root: Path, symbol: str, *, limit: int = 20) -> dict[str, Any]:
    """Direct callers of a qualified or short symbol name."""
    snapshot = load_call_graph_snapshot(project_root)
    if snapshot is None:
        return {"available": False, "reason": "unreadable"}
    if snapshot.missing:
        return {"available": False, "reason": "missing_index"}
    trimmed = symbol.strip()
    matches = {name for name in snapshot.symbols if name == trimmed or name.endswith(f".{trimmed}")}
    if len(matches) > 1:
        exact = [name for name in matches if name.rsplit(".", maxsplit=1)[-1] == trimmed]
        if len(exact) == 1:
            matches = {exact[0]}
    if not matches:
        return {"available": True, "symbol": symbol, "used_by": [], "found": False}
    qualified = next(iter(matches))
    used_by: list[str] = []
    for caller, callee in snapshot.edges:
        if callee != qualified:
            continue
        if caller not in used_by:
            used_by.append(caller)
        if len(used_by) >= limit:
            break
    return {
        "available": True,
        "symbol": symbol,
        "qualified_name": qualified,
        "found": True,
        "used_by": used_by,
    }
