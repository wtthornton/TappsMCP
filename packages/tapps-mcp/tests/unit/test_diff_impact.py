"""Tests for diff impact ranking (TAP-4054)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.diff_impact import (
    BLAST_RADIUS_GAP_RATE_THRESHOLD,
    analyze_diff_impact,
    build_blast_radius_caveat,
    build_diff_impact_enrichment,
    caveat_from_call_graph_summary,
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
        assert any("tests/test_core.py" in t["test_file"] for t in entry["affected_tests"])

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


class TestBlastRadiusCaveat:
    """Call-graph health → review-verdict caveat (TAP-4528)."""

    def test_healthy_low_gap_region_has_no_caveat(self) -> None:
        """A ready cache with a low gap rate and no parse failures = no caveat."""
        summary = {
            "status": "ready",
            "ready": True,
            "stale": False,
            "degraded": False,
            "in_repo_gap_rate": 0.01,
            "parse_failures": 0,
        }
        assert caveat_from_call_graph_summary(summary) is None

    def test_high_gap_rate_region_raises_caveat(self) -> None:
        """High in-repo gap rate = machine-readable caveat + human-readable note."""
        summary = {
            "status": "ready",
            "ready": True,
            "stale": False,
            "degraded": True,
            "in_repo_gap_rate": 0.42,
            "parse_failures": 0,
        }
        caveat = caveat_from_call_graph_summary(summary)
        assert caveat is not None
        assert caveat["degraded"] is True
        assert caveat["reason"] == "high_in_repo_gap_rate"
        assert caveat["in_repo_gap_rate"] == 0.42
        assert isinstance(caveat["note"], str) and caveat["note"]

    def test_parse_failures_raise_caveat_even_at_low_gap(self) -> None:
        """Any parse failure trips the caveat regardless of gap rate."""
        summary = {
            "status": "ready",
            "in_repo_gap_rate": 0.0,
            "parse_failures": 2,
        }
        caveat = caveat_from_call_graph_summary(summary)
        assert caveat is not None
        assert caveat["reason"] == "parse_failures"
        assert caveat["parse_failures"] == 2

    def test_not_ready_cache_raises_cache_not_ready_caveat(self) -> None:
        """A missing / stale cache means the blast radius is unknown → caveat."""
        summary = {"status": "missing", "hint": "run tapps_call_graph"}
        caveat = caveat_from_call_graph_summary(summary)
        assert caveat is not None
        assert caveat["reason"] == "cache_not_ready"
        assert caveat["note"] == "run tapps_call_graph"

    def test_threshold_boundary_is_inclusive(self) -> None:
        """Gap rate exactly at the threshold raises a caveat; just under does not."""
        at = {"status": "ready", "in_repo_gap_rate": BLAST_RADIUS_GAP_RATE_THRESHOLD}
        under = {
            "status": "ready",
            "in_repo_gap_rate": BLAST_RADIUS_GAP_RATE_THRESHOLD - 0.001,
        }
        assert caveat_from_call_graph_summary(at) is not None
        assert caveat_from_call_graph_summary(under) is None

    def test_build_blast_radius_caveat_missing_cache(self, tmp_path: Path) -> None:
        """End-to-end: no warmed cache → cache_not_ready caveat (no rebuild)."""
        caveat = build_blast_radius_caveat(tmp_path)
        assert caveat is not None
        assert caveat["reason"] == "cache_not_ready"

    def test_build_blast_radius_caveat_healthy_repo(self, tmp_path: Path) -> None:
        """End-to-end: a clean warmed cache produces no caveat (no false alarm)."""
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
        # Warm the cache with a clean, fully-resolvable graph.
        analyze_diff_impact([changed], tmp_path)
        assert build_blast_radius_caveat(tmp_path) is None
