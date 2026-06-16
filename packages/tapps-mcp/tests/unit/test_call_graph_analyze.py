"""Unit tests for per-file call graph AST analysis."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph_analyze import analyze_file


def test_analyze_file_extracts_module_function(tmp_path: Path) -> None:
    src = tmp_path / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        """
def helper():
    pass

def caller():
    helper()
""",
        encoding="utf-8",
    )
    symbols, edges, gaps = analyze_file(src, "pkg.mod", tmp_path)[:3]
    names = {s.qualified_name for s in symbols}
    assert "pkg.mod.helper" in names
    assert "pkg.mod.caller" in names
    assert ("pkg.mod.caller", "pkg.mod.helper") in [(e.caller, e.callee) for e in edges]
    assert gaps == []
