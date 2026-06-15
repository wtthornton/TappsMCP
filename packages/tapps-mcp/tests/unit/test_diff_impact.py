"""Tests for diff impact ranking (TAP-4054)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.diff_impact import analyze_diff_impact


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
