"""Tests for diff impact ranking (TAP-4054)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.diff_impact import (
    analyze_diff_impact,
    build_diff_impact_enrichment,
)


def _write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


class TestDiffImpact:
    def test_ranks_linked_tests(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/core.py",
            """
def compute():
    return 42
""",
        )
        _write(
            tmp_path,
            "tests/test_core.py",
            """
from app.core import compute

def test_compute():
    assert compute() == 42
""",
        )
        changed = tmp_path / "app/core.py"
        result = analyze_diff_impact([changed], tmp_path)
        assert result["total_affected_tests"] >= 1
        top = result["affected_tests"][0]
        assert "tests/test_core.py" in top["test_file"]
        assert top["score"] >= 10.0

    def test_max_tests_cap(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/core.py",
            """
def compute():
    return 42
""",
        )
        for i in range(5):
            _write(
                tmp_path,
                f"tests/test_core_{i}.py",
                f"""
from app.core import compute

def test_compute_{i}():
    assert compute() == 42
""",
            )
        changed = tmp_path / "app/core.py"
        result = analyze_diff_impact([changed], tmp_path, max_tests=2)
        assert len(result["affected_tests"]) == 2
        assert result["total_affected_tests"] >= 2

    def test_doc_drift_hint_for_high_caller_symbol(self, tmp_path: Path) -> None:
        callers = "\n".join(
            f"""
def caller_{i}():
    from app.core import compute
    return compute()
"""
            for i in range(6)
        )
        _write(
            tmp_path,
            "app/core.py",
            """
def compute():
    return 42
""",
        )
        _write(tmp_path, "app/callers.py", callers)
        changed = tmp_path / "app/core.py"
        result = analyze_diff_impact([changed], tmp_path, doc_drift_caller_threshold=5)
        hints = result.get("doc_drift_hints")
        assert isinstance(hints, list)
        assert len(hints) >= 1
        assert hints[0]["direct_callers"] >= 5
        assert hints[0]["suggested_doc_paths"]


class TestDiffImpactEnrichment:
    """Per-changed-symbol callers + affected tests for the review path (TAP-4526)."""

    def test_enrichment_reports_callers_and_tests(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/core.py",
            """
def compute():
    return 42
""",
        )
        _write(
            tmp_path,
            "app/caller.py",
            """
def do_work():
    from app.core import compute
    return compute()
""",
        )
        _write(
            tmp_path,
            "tests/test_core.py",
            """
from app.core import compute

def test_compute():
    assert compute() == 42
""",
        )
        changed = tmp_path / "app/core.py"
        # Warm the cache first so the enrichment has a ready index to read.
        analyze_diff_impact([changed], tmp_path)

        result = build_diff_impact_enrichment([changed], tmp_path)

        assert result["degraded"] is False
        assert result["cache_status"] == "ready"
        symbols = result["symbols"]
        assert isinstance(symbols, dict)
        # The changed symbol is keyed by its qualified name.
        key = next(k for k in symbols if k.endswith("compute"))
        entry = symbols[key]
        assert any("do_work" in c for c in entry["callers"])
        assert any(
            "tests/test_core.py" in t["test_file"] for t in entry["affected_tests"]
        )

    def test_degrades_when_cache_missing(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/core.py",
            """
def compute():
    return 42
""",
        )
        changed = tmp_path / "app/core.py"
        # No cache warmed — enrichment must degrade gracefully, not raise.
        result = build_diff_impact_enrichment([changed], tmp_path)

        assert result["degraded"] is True
        assert result["cache_status"] == "missing"
        assert result["symbols"] == {}
        assert result["note"]
