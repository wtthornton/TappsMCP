"""Tests for per-file pass/fail row generation (Story 75.4)."""

from __future__ import annotations

from tapps_mcp.server_pipeline_tools import _build_per_file_results


class TestBuildPerFileResults:
    def test_mixed_pass_fail(self) -> None:
        results = [
            {
                "file_path": "/workspace/sandbox.py",
                "gate_passed": True,
                "score": 7.2,
                "security_issues": 0,
                "errors": [],
            },
            {
                "file_path": "/workspace/processor.py",
                "gate_passed": False,
                "score": 4.1,
                "security_issues": 0,
                "errors": ["low score"],
            },
            {
                "file_path": "/workspace/generator.py",
                "gate_passed": True,
                "score": 6.8,
                "security_issues": 0,
                "errors": [],
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert len(per_file) == 3
        assert per_file[0]["status"] == "PASS"
        assert per_file[0]["file"] == "sandbox.py"
        assert per_file[0]["score"] == 7.2
        assert per_file[1]["status"] == "FAIL"
        assert per_file[1]["file"] == "processor.py"
        assert per_file[2]["status"] == "PASS"

        assert len(rows) == 3
        assert rows[0].startswith("PASS")
        assert rows[1].startswith("FAIL")
        assert "sandbox.py" in rows[0]
        assert "processor.py" in rows[1]

    def test_all_passing(self) -> None:
        results = [
            {
                "file_path": "src/main.py",
                "gate_passed": True,
                "score": 8.5,
                "security_issues": 0,
                "errors": [],
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert len(per_file) == 1
        assert per_file[0]["status"] == "PASS"
        assert per_file[0]["gate_passed"] is True
        assert per_file[0]["security_passed"] is True
        assert "issues=" not in rows[0]

    def test_security_issues_flagged(self) -> None:
        results = [
            {
                "file_path": "src/auth.py",
                "gate_passed": True,
                "score": 7.0,
                "security_issues": 2,
                "errors": [],
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert per_file[0]["security_passed"] is False
        assert per_file[0]["issue_count"] == 2
        assert "security=fail" in rows[0]
        assert "issues=2" in rows[0]

    def test_empty_results(self) -> None:
        per_file, rows = _build_per_file_results([])
        assert per_file == []
        assert rows == []

    def test_error_results(self) -> None:
        results = [
            {
                "file_path": "bad.py",
                "errors": ["timeout"],
                "gate_passed": False,
                "score": 0,
                "security_issues": 0,
            },
        ]
        per_file, rows = _build_per_file_results(results)

        assert per_file[0]["status"] == "FAIL"
        assert per_file[0]["issue_count"] == 1

    def test_grep_friendly_format(self) -> None:
        """Summary rows should be grepable with 'grep FAIL'."""
        results = [
            {
                "file_path": "ok.py",
                "gate_passed": True,
                "score": 8.0,
                "security_issues": 0,
                "errors": [],
            },
            {
                "file_path": "bad.py",
                "gate_passed": False,
                "score": 3.0,
                "security_issues": 1,
                "errors": ["x"],
            },
        ]
        _, rows = _build_per_file_results(results)

        fail_rows = [r for r in rows if r.startswith("FAIL")]
        pass_rows = [r for r in rows if r.startswith("PASS")]
        assert len(fail_rows) == 1
        assert len(pass_rows) == 1

    def test_uses_overall_score_fallback(self) -> None:
        """When 'score' key missing, falls back to 'overall_score'."""
        results = [
            {
                "file_path": "alt.py",
                "gate_passed": True,
                "overall_score": 6.5,
                "security_issues": 0,
                "errors": [],
            },
        ]
        per_file, _ = _build_per_file_results(results)
        assert per_file[0]["score"] == 6.5
