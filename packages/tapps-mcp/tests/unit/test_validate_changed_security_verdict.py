"""TAP-6387 — one security verdict per file, not three.

``tapps_validate_changed`` used to answer "did security pass?" three different
ways in a single response: ``per_file_results[].security_passed`` and the
``summary_rows`` text derived it from a raw issue count, ``results[]`` and
``structuredContent`` carried the authoritative ``sec_result.passed``, and the
orchestrator's full-scan branch hand-counted critical/high itself. A file whose
findings were all low-severity therefore rendered ``security=fail`` in the block
agents quote while reporting ``security_passed=true`` two keys away.

These tests pin the converged behaviour: every rendering of the verdict in one
response agrees, and low-severity findings render as a pass with a non-zero
issue count.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.common.models import SecurityIssue
from tapps_mcp.scoring.models import ScoreResult
from tapps_mcp.security.verdict import (
    count_blocking,
    read_security_verdict,
    security_verdict,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")


def _issue(severity: str) -> SecurityIssue:
    return SecurityIssue(
        code="B101",
        message=f"{severity} finding",
        file="test.py",
        line=1,
        severity=severity,
    )


def _scorer_returning(score: ScoreResult) -> MagicMock:
    scorer = MagicMock()
    scorer.language = "python"
    scorer.score_file = AsyncMock(return_value=score)
    scorer.score_file_quick = MagicMock(return_value=score)
    return scorer


async def _run_validate(
    tmp_path: Path,
    files: dict[str, ScoreResult],
    *,
    gate_passed: bool = True,
) -> dict:
    """Run tapps_validate_changed over ``files`` with stubbed scoring.

    Runs in full mode with a clean secret scan so the orchestrator's full-scan
    branch — the one that used to hand-count critical/high — is the producer
    under test.
    """
    from tapps_mcp.security.secret_scanner import SecretScanResult
    from tapps_mcp.server_pipeline_tools import tapps_validate_changed

    paths: list[Path] = []
    for name in files:
        f = tmp_path / name
        f.write_text("x = 1\n", encoding="utf-8")
        paths.append(f)

    by_path = {str(tmp_path / name): score for name, score in files.items()}

    def _pick_scorer(path: Path) -> MagicMock:
        return _scorer_returning(by_path[str(path)])

    mock_gate = MagicMock(passed=gate_passed, failures=[])
    scanner_instance = MagicMock()
    scanner_instance.scan_file.return_value = SecretScanResult(scanned_files=1)

    with (
        patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
        patch("tapps_mcp.server._validate_file_path", side_effect=Path),
        patch("tapps_mcp.server_helpers._get_scorer_for_file", side_effect=_pick_scorer),
        patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        patch(
            "tapps_mcp.security.secret_scanner.SecretScanner",
            return_value=scanner_instance,
        ),
    ):
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.tool_timeout = 30
        mock_settings.return_value.dependency_scan_enabled = False

        return await tapps_validate_changed(
            file_paths=",".join(str(p) for p in paths),
            quick=False,
            include_security=True,
        )


class TestSecurityVerdictHelper:
    """The one definition every call site now shares."""

    def test_low_severity_findings_do_not_block(self) -> None:
        assert count_blocking([_issue("low"), _issue("medium")]) == 0
        assert security_verdict(blocking_findings=0) is True

    def test_critical_and_high_block(self) -> None:
        assert count_blocking([_issue("critical"), _issue("high"), _issue("low")]) == 2
        assert security_verdict(blocking_findings=2) is False

    def test_scan_error_fails_even_with_no_findings(self) -> None:
        """TAP-1794: an unreadable file is not a clean file."""
        assert security_verdict(blocking_findings=0, scan_error="Permission denied") is False

    def test_read_verdict_defaults_to_fail_when_absent(self) -> None:
        assert read_security_verdict({"security_passed": True}) is True
        assert read_security_verdict({"security_passed": False}) is False
        # No producer ran — report conservatively, matching structuredContent.
        assert read_security_verdict({"security_issues": 0}) is False


class TestScannerUsesSharedVerdict:
    """``SecurityScanResult.passed`` is the shared definition, not a copy of it."""

    def test_low_severity_bandit_findings_still_pass(self) -> None:
        from tapps_mcp.security.security_scanner import run_security_scan

        with (
            patch(
                "tapps_mcp.security.security_scanner._run_bandit_scan",
                return_value=([_issue("low") for _ in range(12)], True),
            ),
            patch(
                "tapps_mcp.security.security_scanner._run_secret_scan",
                return_value=([], None),
            ),
        ):
            result = run_security_scan("test.py")

        assert result.total_issues == 12
        assert result.passed is True


class TestOrchestratorVerdictConvergence:
    """The full-scan branch answers the same question as the scanner."""

    @pytest.mark.asyncio
    async def test_secret_scan_read_error_fails_the_file(self) -> None:
        """Definition 3 used to drop ``secret_result.error`` and report clean."""
        from tapps_mcp.security.secret_scanner import SecretScanResult
        from tapps_mcp.tools.validate_changed_orchestrator import _run_security_scan

        score = MagicMock()
        score.security_issues = []
        unreadable = SecretScanResult(passed=False, error="Permission denied", scanned_files=0)

        with patch("tapps_mcp.security.secret_scanner.SecretScanner") as scanner_cls:
            scanner_cls.return_value.scan_file.return_value = unreadable
            sec = await _run_security_scan(
                Path("test.py"), score, True, True, quick=False, quick_sec=None
            )

        assert sec["security_passed"] is False

    @pytest.mark.asyncio
    async def test_low_severity_bandit_findings_pass_full_scan(self) -> None:
        from tapps_mcp.security.secret_scanner import SecretScanResult
        from tapps_mcp.tools.validate_changed_orchestrator import _run_security_scan

        score = MagicMock()
        score.security_issues = [_issue("low") for _ in range(12)]

        with patch("tapps_mcp.security.secret_scanner.SecretScanner") as scanner_cls:
            scanner_cls.return_value.scan_file.return_value = SecretScanResult(scanned_files=1)
            sec = await _run_security_scan(
                Path("test.py"), score, True, True, quick=False, quick_sec=None
            )

        assert sec["security_issues"] == 12
        assert sec["security_passed"] is True


class TestBatchResponseAgreesWithItself:
    """Acceptance 2 and 3 — one verdict across every block of one response."""

    @pytest.mark.asyncio
    async def test_low_severity_file_renders_pass_with_nonzero_issue_count(
        self, tmp_path: Path
    ) -> None:
        """The reproduced defect: ``security=fail`` on a file that passed."""
        score = ScoreResult(
            file_path=str(tmp_path / "low.py"),
            categories={},
            overall_score=85.0,
            security_issues=[_issue("low") for _ in range(12)],
        )

        result = await _run_validate(tmp_path, {"low.py": score})

        data = result["data"]
        entry = data["per_file_results"][0]
        row = data["summary_rows"][0]

        assert entry["security_passed"] is True
        assert "security=pass" in row
        assert entry["issue_count"] == 12
        assert "issues=12" in row

    @pytest.mark.asyncio
    async def test_per_file_results_match_results_for_every_file(self, tmp_path: Path) -> None:
        """Acceptance 3 — the batch-wide equality invariant."""
        severities = {
            "clean.py": [],
            "low.py": [_issue("low"), _issue("medium")],
            "high.py": [_issue("high")],
            "critical.py": [_issue("critical"), _issue("low")],
        }
        files = {
            name: ScoreResult(
                file_path=str(tmp_path / name),
                categories={},
                overall_score=85.0,
                security_issues=issues,
            )
            for name, issues in severities.items()
        }

        result = await _run_validate(tmp_path, files)

        data = result["data"]
        per_file = data["per_file_results"]
        results = data["results"]
        rows = data["summary_rows"]
        structured = result["structuredContent"]["files"]

        assert len(per_file) == len(results) == len(rows) == len(structured) == len(files)

        for entry, raw, row, struct in zip(per_file, results, rows, structured, strict=True):
            verdict = read_security_verdict(raw)
            assert entry["security_passed"] == verdict, entry["file"]
            assert struct["security_passed"] == verdict, entry["file"]
            assert f"security={'pass' if verdict else 'fail'}" in row, entry["file"]

        by_name = {e["file"]: e["security_passed"] for e in per_file}
        assert by_name == {
            "clean.py": True,
            "low.py": True,
            "high.py": False,
            "critical.py": False,
        }
