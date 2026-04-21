"""Tests for tools.pip_audit -- parsing, filtering, and async execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.tools.pip_audit import (
    DependencyAuditResult,
    VulnerabilityFinding,
    _build_pip_audit_args,
    _parse_pip_audit_json,
    _severity_meets_threshold,
    run_pip_audit_async,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

SAMPLE_PIP_AUDIT_JSON = """{
  "dependencies": [
    {"name": "requests", "version": "2.25.0", "vulns": [
      {"id": "PYSEC-2023-74", "fix_versions": ["2.31.0"],
       "description": "Session fixation vuln",
       "aliases": ["CVE-2023-32681"]}
    ]},
    {"name": "cryptography", "version": "39.0.0", "vulns": [
      {"id": "CVE-2024-26130", "fix_versions": ["42.0.0"],
       "description": "NULL pointer deref", "aliases": []}
    ]},
    {"name": "flask", "version": "3.0.0", "vulns": []}
  ]
}"""

SAMPLE_MULTIPLE_VULNS_JSON = """{
  "dependencies": [
    {"name": "cryptography", "version": "39.0.0", "vulns": [
      {"id": "CVE-2024-26130", "fix_versions": ["42.0.0"],
       "description": "NULL pointer deref", "aliases": []},
      {"id": "CVE-2024-12345", "fix_versions": ["41.0.0"],
       "description": "Buffer overflow", "aliases": ["PYSEC-2024-99"]}
    ]}
  ]
}"""


class TestSeverityMeetsThreshold:
    """Tests for the _severity_meets_threshold helper."""

    def test_critical_meets_any_threshold(self) -> None:
        assert _severity_meets_threshold("critical", "critical")
        assert _severity_meets_threshold("critical", "high")
        assert _severity_meets_threshold("critical", "medium")
        assert _severity_meets_threshold("critical", "low")
        assert _severity_meets_threshold("critical", "unknown")

    def test_medium_meets_medium_threshold(self) -> None:
        assert _severity_meets_threshold("medium", "medium")

    def test_medium_does_not_meet_high_threshold(self) -> None:
        assert not _severity_meets_threshold("medium", "high")

    def test_low_does_not_meet_medium_threshold(self) -> None:
        assert not _severity_meets_threshold("low", "medium")

    def test_unknown_meets_unknown_threshold(self) -> None:
        assert _severity_meets_threshold("unknown", "unknown")

    def test_unknown_does_not_meet_low_threshold(self) -> None:
        assert not _severity_meets_threshold("unknown", "low")

    def test_case_insensitive(self) -> None:
        assert _severity_meets_threshold("HIGH", "medium")
        assert _severity_meets_threshold("Medium", "LOW")


class TestParsePipAuditJson:
    """Tests for _parse_pip_audit_json."""

    def test_parse_json_success(self) -> None:
        result = _parse_pip_audit_json(SAMPLE_PIP_AUDIT_JSON)
        assert result.error is None
        assert len(result.findings) == 2
        assert result.scanned_packages == 3
        assert result.vulnerable_packages == 2

        # Check first finding (PYSEC -> medium severity)
        req_finding = result.findings[0]
        assert req_finding.package == "requests"
        assert req_finding.installed_version == "2.25.0"
        assert req_finding.fixed_version == "2.31.0"
        assert req_finding.vulnerability_id == "PYSEC-2023-74"
        assert req_finding.severity == "medium"
        assert req_finding.aliases == ["CVE-2023-32681"]

        # Check second finding (CVE -> high severity)
        crypto_finding = result.findings[1]
        assert crypto_finding.package == "cryptography"
        assert crypto_finding.severity == "high"

    def test_parse_json_empty_vulns(self) -> None:
        json_str = '{"dependencies": [{"name": "flask", "version": "3.0.0", "vulns": []}]}'
        result = _parse_pip_audit_json(json_str)
        assert result.error is None
        assert len(result.findings) == 0
        assert result.scanned_packages == 1
        assert result.vulnerable_packages == 0

    def test_parse_json_invalid(self) -> None:
        result = _parse_pip_audit_json("not valid json {{{")
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_parse_json_empty_string(self) -> None:
        result = _parse_pip_audit_json("")
        assert result.error is not None
        assert "Empty" in result.error

    def test_parse_json_whitespace(self) -> None:
        result = _parse_pip_audit_json("   \n  ")
        assert result.error is not None

    def test_parse_json_not_dict(self) -> None:
        result = _parse_pip_audit_json("[1, 2, 3]")
        assert result.error is not None
        assert "Unexpected" in result.error

    def test_parse_json_no_dependencies_key(self) -> None:
        result = _parse_pip_audit_json('{"other": []}')
        assert result.error is None
        assert len(result.findings) == 0
        assert result.scanned_packages == 0

    def test_parse_json_dependencies_not_list(self) -> None:
        result = _parse_pip_audit_json('{"dependencies": "bad"}')
        assert result.error is not None

    def test_multiple_vulns_per_package(self) -> None:
        result = _parse_pip_audit_json(SAMPLE_MULTIPLE_VULNS_JSON)
        assert result.error is None
        assert len(result.findings) == 2
        assert result.scanned_packages == 1
        assert result.vulnerable_packages == 1
        assert result.findings[0].vulnerability_id == "CVE-2024-26130"
        assert result.findings[1].vulnerability_id == "CVE-2024-12345"
        assert result.findings[1].aliases == ["PYSEC-2024-99"]

    def test_parse_json_non_dict_dep_skipped(self) -> None:
        json_str = '{"dependencies": ["not-a-dict", {"name": "ok", "version": "1.0", "vulns": []}]}'
        result = _parse_pip_audit_json(json_str)
        assert result.error is None
        assert result.scanned_packages == 1

    def test_parse_json_non_dict_vuln_skipped(self) -> None:
        json_str = '{"dependencies": [{"name": "pkg", "version": "1.0", "vulns": ["not-a-dict"]}]}'
        result = _parse_pip_audit_json(json_str)
        assert result.error is None
        assert len(result.findings) == 0

    def test_missing_fix_versions(self) -> None:
        json_str = (
            '{"dependencies": [{"name": "pkg", "version": "1.0", '
            '"vulns": [{"id": "CVE-2024-1", "description": "bad"}]}]}'
        )
        result = _parse_pip_audit_json(json_str)
        assert len(result.findings) == 1
        assert result.findings[0].fixed_version == ""


class TestRunPipAuditAsync:
    """Tests for run_pip_audit_async."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value=None)
    async def test_run_not_installed(self, mock_which: object) -> None:
        result = await run_pip_audit_async()
        assert result.error is not None
        assert "not installed" in result.error

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_run_timeout(self, mock_which: object, mock_cmd: object) -> None:
        assert mock_which  # suppress unused warnings in strict typing
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=-1,
            stdout="",
            stderr="Timed out after 60s",
            command=["pip-audit"],
            timed_out=True,
        )
        result = await run_pip_audit_async(timeout=60)
        assert result.error is not None
        assert "timed out" in result.error

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_run_success(self, mock_which: object, mock_cmd: object) -> None:
        assert mock_which
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=1,  # non-zero = vulns found
            stdout=SAMPLE_PIP_AUDIT_JSON,
            stderr="",
        )
        result = await run_pip_audit_async(severity_threshold="unknown")
        assert result.error is None
        assert len(result.findings) == 2
        assert result.scanned_packages == 3

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_severity_threshold_filter(self, mock_which: object, mock_cmd: object) -> None:
        assert mock_which
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=1,
            stdout=SAMPLE_PIP_AUDIT_JSON,
            stderr="",
        )
        # "high" threshold should filter out PYSEC (medium), keep CVE (high)
        result = await run_pip_audit_async(severity_threshold="high")
        assert result.error is None
        assert len(result.findings) == 1
        assert result.findings[0].package == "cryptography"
        assert result.vulnerable_packages == 1

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_ignore_ids_filter(self, mock_which: object, mock_cmd: object) -> None:
        assert mock_which
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=1,
            stdout=SAMPLE_PIP_AUDIT_JSON,
            stderr="",
        )
        result = await run_pip_audit_async(
            severity_threshold="unknown",
            ignore_ids=["CVE-2024-26130"],
        )
        assert result.error is None
        assert len(result.findings) == 1
        assert result.findings[0].vulnerability_id == "PYSEC-2023-74"

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_run_failure_no_output(self, mock_which: object, mock_cmd: object) -> None:
        assert mock_which
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=2,
            stdout="",
            stderr="Some error occurred",
        )
        result = await run_pip_audit_async()
        assert result.error is not None
        assert "failed" in result.error

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_run_clean_no_vulns(self, mock_which: object, mock_cmd: object) -> None:
        assert mock_which
        clean_json = '{"dependencies": [{"name": "flask", "version": "3.0.0", "vulns": []}]}'
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=0,
            stdout=clean_json,
            stderr="",
        )
        result = await run_pip_audit_async(severity_threshold="unknown")
        assert result.error is None
        assert len(result.findings) == 0
        assert result.scanned_packages == 1

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.pip_audit.run_command_async")
    @patch("tapps_mcp.tools.pip_audit.shutil.which", return_value="/usr/bin/pip-audit")
    async def test_run_empty_stdout_success(self, mock_which: object, mock_cmd: object) -> None:
        """Exit 0 with empty stdout is treated as clean scan."""
        assert mock_which
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=0,
            stdout="",
            stderr="",
        )
        result = await run_pip_audit_async()
        assert result.error is None
        assert len(result.findings) == 0


class TestVulnerabilityFindingDefaults:
    """Tests for VulnerabilityFinding dataclass defaults."""

    def test_defaults(self) -> None:
        finding = VulnerabilityFinding(
            package="test-pkg",
            installed_version="1.0.0",
        )
        assert finding.fixed_version == ""
        assert finding.vulnerability_id == ""
        assert finding.description == ""
        assert finding.severity == "unknown"
        assert finding.aliases == []

    def test_aliases_independence(self) -> None:
        """Ensure mutable default (aliases) is independent across instances."""
        f1 = VulnerabilityFinding(package="a", installed_version="1.0")
        f2 = VulnerabilityFinding(package="b", installed_version="2.0")
        f1.aliases.append("CVE-1")
        assert f2.aliases == []


class TestBuildPipAuditArgs:
    """Tests for _build_pip_audit_args — covers monorepo/editable install handling."""

    def test_auto_no_requirements_uses_skip_editable(self, tmp_path: Path) -> None:
        args, source = _build_pip_audit_args("auto", str(tmp_path))
        assert source == "environment"
        assert "--skip-editable" in args

    def test_environment_uses_skip_editable(self, tmp_path: Path) -> None:
        args, source = _build_pip_audit_args("environment", str(tmp_path))
        assert source == "environment"
        assert "--skip-editable" in args

    def test_auto_with_requirements_txt_no_skip_editable(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")
        args, source = _build_pip_audit_args("auto", str(tmp_path))
        assert source == "requirements"
        assert "--skip-editable" not in args
        assert "-r" in args
        assert "requirements.txt" in args

    def test_requirements_source_no_skip_editable(self, tmp_path: Path) -> None:
        args, source = _build_pip_audit_args("requirements", str(tmp_path))
        assert source == "requirements"
        assert "--skip-editable" not in args

    def test_pyproject_source_no_skip_editable(self, tmp_path: Path) -> None:
        args, source = _build_pip_audit_args("pyproject", str(tmp_path))
        assert source == "pyproject"
        assert "--skip-editable" not in args


class TestDependencyAuditResultDefaults:
    """Tests for DependencyAuditResult dataclass defaults."""

    def test_defaults(self) -> None:
        result = DependencyAuditResult()
        assert result.findings == []
        assert result.scanned_packages == 0
        assert result.vulnerable_packages == 0
        assert result.scan_source == "environment"
        assert result.error is None

    def test_findings_independence(self) -> None:
        """Ensure mutable default (findings) is independent across instances."""
        r1 = DependencyAuditResult()
        r2 = DependencyAuditResult()
        r1.findings.append(VulnerabilityFinding(package="x", installed_version="1.0"))
        assert r2.findings == []
