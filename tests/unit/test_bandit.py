"""Tests for tools.bandit — parsing, scoring, and OWASP mapping."""

import json
from unittest.mock import patch

from tapps_mcp.scoring.models import SecurityIssue
from tapps_mcp.tools.bandit import (
    _map_owasp,
    calculate_security_score,
    parse_bandit_json,
    run_bandit_check,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

SAMPLE_BANDIT_JSON = json.dumps(
    {
        "results": [
            {
                "test_id": "B101",
                "issue_text": "Use of assert detected.",
                "filename": "test.py",
                "line_number": 5,
                "issue_severity": "LOW",
                "issue_confidence": "HIGH",
            },
            {
                "test_id": "B602",
                "issue_text": "subprocess call with shell=True",
                "filename": "app.py",
                "line_number": 20,
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
            },
        ]
    }
)


class TestMapOwasp:
    def test_known_mapping(self):
        assert _map_owasp("B101") == "A05:2021-Security Misconfiguration"
        assert _map_owasp("B602") == "A03:2021-Injection"
        assert _map_owasp("B303") == "A02:2021-Cryptographic Failures"

    def test_unknown_code(self):
        assert _map_owasp("B999") is None

    def test_empty_code(self):
        assert _map_owasp("") is None


class TestParseBanditJson:
    def test_valid_output(self):
        issues = parse_bandit_json(SAMPLE_BANDIT_JSON)
        assert len(issues) == 2
        assert issues[0].code == "B101"
        assert issues[0].severity == "low"
        assert issues[0].confidence == "high"
        assert issues[0].owasp is not None
        assert issues[1].code == "B602"
        assert issues[1].severity == "high"

    def test_empty_string(self):
        assert parse_bandit_json("") == []

    def test_whitespace_string(self):
        assert parse_bandit_json("   ") == []

    def test_invalid_json(self):
        assert parse_bandit_json("not json") == []

    def test_no_results_key(self):
        assert parse_bandit_json('{"errors": []}') == []

    def test_empty_results(self):
        assert parse_bandit_json('{"results": []}') == []

    def test_owasp_mapping_applied(self):
        issues = parse_bandit_json(SAMPLE_BANDIT_JSON)
        assert issues[0].owasp == "A05:2021-Security Misconfiguration"
        assert issues[1].owasp == "A03:2021-Injection"


class TestCalculateSecurityScore:
    def test_no_issues(self):
        assert calculate_security_score([]) == 10.0

    def test_high_severity(self):
        issues = [
            SecurityIssue(
                code="B602", message="shell", file="t.py", line=1, severity="high"
            ),
        ]
        # high costs 3.0
        assert calculate_security_score(issues) == 7.0

    def test_critical_severity(self):
        issues = [
            SecurityIssue(
                code="B602", message="bad", file="t.py", line=1, severity="critical"
            ),
        ]
        assert calculate_security_score(issues) == 7.0

    def test_medium_severity(self):
        issues = [
            SecurityIssue(
                code="B101", message="assert", file="t.py", line=1, severity="medium"
            ),
        ]
        # medium costs 1.0
        assert calculate_security_score(issues) == 9.0

    def test_low_severity_no_penalty(self):
        issues = [
            SecurityIssue(
                code="B101", message="assert", file="t.py", line=1, severity="low"
            ),
        ]
        assert calculate_security_score(issues) == 10.0

    def test_mixed_severities(self):
        issues = [
            SecurityIssue(code="B1", message="h", file="t.py", line=1, severity="high"),
            SecurityIssue(code="B2", message="m", file="t.py", line=2, severity="medium"),
            SecurityIssue(code="B3", message="l", file="t.py", line=3, severity="low"),
        ]
        # 3.0 + 1.0 = 4.0 penalty
        assert calculate_security_score(issues) == 6.0

    def test_clamps_to_zero(self):
        issues = [
            SecurityIssue(code="B1", message="h", file="t.py", line=i, severity="high")
            for i in range(10)
        ]
        assert calculate_security_score(issues) == 0.0


class TestRunBanditCheck:
    @patch("tapps_mcp.tools.bandit.run_command")
    def test_with_issues(self, mock_cmd):
        mock_cmd.return_value = CommandResult(
            returncode=1, stdout=SAMPLE_BANDIT_JSON, stderr=""
        )
        issues = run_bandit_check("test.py")
        assert len(issues) == 2

    @patch("tapps_mcp.tools.bandit.run_command")
    def test_clean_file(self, mock_cmd):
        mock_cmd.return_value = CommandResult(
            returncode=0, stdout='{"results": []}', stderr=""
        )
        issues = run_bandit_check("test.py")
        assert issues == []

    @patch("tapps_mcp.tools.bandit.run_command")
    def test_empty_output(self, mock_cmd):
        mock_cmd.return_value = CommandResult(
            returncode=0, stdout="", stderr=""
        )
        issues = run_bandit_check("test.py")
        assert issues == []
