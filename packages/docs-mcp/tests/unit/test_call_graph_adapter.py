"""Tests for DocsMCP call graph adapter (TAP-4271)."""

from __future__ import annotations

import json
from pathlib import Path

from docs_mcp.integrations.call_graph import (
    module_depends_on,
    module_used_by,
    symbol_used_by,
)


def _write_index(root: Path) -> None:
    payload = {
        "version": 2,
        "symbols": [
            {"qualified_name": "app.core.compute", "module": "app.core", "file_path": "app/core.py", "line": 1, "kind": "function"},
            {"qualified_name": "app.api.run", "module": "app.api", "file_path": "app/api.py", "line": 1, "kind": "function"},
        ],
        "edges": [
            {"caller": "app.api.run", "callee": "app.core.compute", "callee_expr": "compute()", "line": 2, "resolved": True},
        ],
        "resolution_gaps": [],
        "parse_failures": [],
    }
    cache_dir = root / ".tapps-mcp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "call-graph-index.json").write_text(json.dumps(payload), encoding="utf-8")


def test_module_used_by(tmp_path: Path) -> None:
    _write_index(tmp_path)
    result = module_used_by(tmp_path, "app.core")
    assert result["available"] is True
    assert result["used_by"][0]["caller"] == "app.api.run"


def test_module_depends_on(tmp_path: Path) -> None:
    _write_index(tmp_path)
    result = module_depends_on(tmp_path, "app.api")
    assert result["available"] is True
    assert result["depends_on"][0]["callee"] == "app.core.compute"


def test_symbol_used_by_short_name(tmp_path: Path) -> None:
    _write_index(tmp_path)
    result = symbol_used_by(tmp_path, "compute")
    assert result["found"] is True
    assert result["used_by"] == ["app.api.run"]


def test_missing_index_graceful(tmp_path: Path) -> None:
    result = module_used_by(tmp_path, "app.core")
    assert result["available"] is False
    assert result["reason"] == "missing_index"
