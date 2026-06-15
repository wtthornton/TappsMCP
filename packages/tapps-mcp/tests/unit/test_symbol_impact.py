"""Tests for symbol-level impact analysis (TAP-4051)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.impact_analyzer import analyze_symbol_impact


def _write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


class TestSymbolImpact:
    def test_symbol_callers_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "svc/flow.py",
            """
def leaf():
    return 0

def caller():
    leaf()
""",
        )
        result = analyze_symbol_impact("svc.flow.leaf", tmp_path)
        assert result["found"] is True
        assert len(result["callers"]) == 1
        assert result["severity"] in {"low", "medium", "high", "critical"}
