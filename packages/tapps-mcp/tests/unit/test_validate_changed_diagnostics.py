"""Tests for validate_changed diagnostic enrichment (TAP-3585 / TAP-3589)."""

from __future__ import annotations

from tapps_mcp.server_pipeline_tools import _build_per_file_results
from tapps_mcp.tools.validate_changed_diagnostics import (
    derive_failure_reason,
    enrich_file_entry,
)


class TestDeriveFailureReason:
    def test_unsupported_file(self) -> None:
        reason = derive_failure_reason({"errors": ["Unsupported file type: .yaml"]})
        assert reason == "unsupported_file"

    def test_lint_blocker_on_zero_score(self) -> None:
        reason = derive_failure_reason(
            {
                "overall_score": 0.0,
                "gate_passed": False,
                "lint_issues": [{"code": "F821", "message": "undefined name", "line": 1}],
            }
        )
        assert reason == "lint_blocker"

    def test_gate_threshold(self) -> None:
        reason = derive_failure_reason(
            {
                "overall_score": 65.0,
                "gate_passed": False,
                "gate_failures": [{"category": "overall"}],
            }
        )
        assert reason == "gate_threshold"


class TestBuildPerFileResultsDiagnostics:
    def test_gate_fail_includes_top_findings(self) -> None:
        results = [
            {
                "file_path": "/workspace/styles.py",
                "gate_passed": False,
                "overall_score": 65.0,
                "security_issues": 0,
                "errors": [],
                "lint_issues": [
                    {"code": "F401", "message": "unused import", "line": 3},
                    {"code": "F821", "message": "undefined name x", "line": 10},
                ],
                "failure_reason": "lint_blocker",
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert len(per_file[0]["top_findings"]) == 2
        assert per_file[0]["top_findings"][0]["code"] == "F401"
        assert per_file[0]["failure_reason"] == "lint_blocker"
        assert "top=F401" in rows[0]
        assert "reason=lint_blocker" in rows[0]

    def test_passing_file_unchanged(self) -> None:
        results = [
            {
                "file_path": "ok.py",
                "gate_passed": True,
                "overall_score": 85.0,
                "security_issues": 0,
                "errors": [],
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert "top_findings" not in per_file[0]
        assert "failure_reason" not in per_file[0]
        assert rows[0].startswith("PASS")


class TestEnrichFileEntry:
    def test_zero_score_shows_reason(self) -> None:
        entry: dict[str, object] = {}
        row_parts = ["FAIL", "layout.py"]
        raw = {
            "file_path": "layout.py",
            "gate_passed": False,
            "overall_score": 0.0,
            "lint_issues": [{"code": "E999", "message": "syntax error", "line": 1}],
        }
        enrich_file_entry(entry, row_parts, raw, near_miss_slots_remaining=3)
        assert entry.get("failure_reason") == "lint_blocker"
        assert "reason=lint_blocker" in row_parts


class TestNearMissHints:
    def test_near_miss_includes_improvement_hints(self) -> None:
        results = [
            {
                "file_path": "src/components.py",
                "gate_passed": True,
                "overall_score": 72.0,
                "security_issues": 0,
                "errors": [],
                "improvement_hints": ["Reduce complexity in render()", "Add tests"],
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert per_file[0]["improvement_hints"] == [
            "Reduce complexity in render()",
            "Add tests",
        ]
        assert "near_miss=yes" in rows[0]

    def test_near_miss_capped_at_three_files(self) -> None:
        results = [
            {
                "file_path": f"src/f{i}.py",
                "gate_passed": True,
                "overall_score": 71.0,
                "security_issues": 0,
                "errors": [],
                "improvement_hints": [f"hint {i}"],
            }
            for i in range(5)
        ]
        per_file, _ = _build_per_file_results(results)

        with_hints = [p for p in per_file if "improvement_hints" in p]
        assert len(with_hints) == 3

    def test_score_80_not_near_miss(self) -> None:
        results = [
            {
                "file_path": "src/audit.py",
                "gate_passed": True,
                "overall_score": 80.0,
                "security_issues": 0,
                "errors": [],
                "improvement_hints": ["should not show"],
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert "improvement_hints" not in per_file[0]
        assert "near_miss=yes" not in rows[0]


class TestMultiFileMemoryHint:
    def test_count_src_paths(self) -> None:
        from pathlib import Path

        from tapps_mcp.tools.validate_changed_diagnostics import count_src_paths

        paths = [
            Path("packages/foo/src/a.py"),
            Path("packages/foo/src/b.py"),
            Path("docs/readme.md"),
        ]
        assert count_src_paths(paths) == 2

    def test_hint_when_five_or_more_src_files(self) -> None:
        from tapps_mcp.tools.validate_changed_diagnostics import build_multi_file_memory_hint

        hint = build_multi_file_memory_hint(5)
        assert hint is not None
        assert "tapps-mcp memory" in hint
        assert build_multi_file_memory_hint(4) is None
