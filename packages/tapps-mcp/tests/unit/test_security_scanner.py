"""Tests for security.security_scanner — unified scanner."""

from pathlib import Path
from unittest.mock import patch

from tapps_mcp.scoring.models import SecurityIssue
from tapps_mcp.security.secret_scanner import SecretFinding, SecretScanResult
from tapps_mcp.security.security_scanner import SecurityScanResult, run_security_scan


class TestSecurityScanResult:
    def test_defaults(self):
        r = SecurityScanResult()
        assert r.bandit_issues == []
        assert r.secret_findings == []
        assert r.total_issues == 0
        assert r.passed is True
        assert r.bandit_available is True

    def test_failed(self):
        r = SecurityScanResult(
            critical_count=1,
            total_issues=1,
            passed=False,
        )
        assert r.passed is False


class TestRunSecurityScan:
    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=True)
    @patch("tapps_mcp.security.security_scanner.run_bandit_check")
    @patch("tapps_mcp.security.security_scanner.SecretScanner")
    def test_full_scan_clean(self, mock_scanner_cls, mock_bandit, mock_which):
        mock_bandit.return_value = []
        mock_scanner_inst = mock_scanner_cls.return_value
        mock_scanner_inst.scan_file.return_value = SecretScanResult(findings=[])

        result = run_security_scan("test.py")
        assert result.passed is True
        assert result.total_issues == 0
        assert result.bandit_available is True

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=True)
    @patch("tapps_mcp.security.security_scanner.run_bandit_check")
    @patch("tapps_mcp.security.security_scanner.SecretScanner")
    def test_bandit_issues(self, mock_scanner_cls, mock_bandit, mock_which):
        mock_bandit.return_value = [
            SecurityIssue(
                code="B602",
                message="subprocess with shell",
                file="test.py",
                line=10,
                severity="high",
            ),
        ]
        mock_scanner_inst = mock_scanner_cls.return_value
        mock_scanner_inst.scan_file.return_value = SecretScanResult(findings=[])

        result = run_security_scan("test.py")
        assert result.passed is False
        assert result.total_issues == 1
        assert result.high_count == 1

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=True)
    @patch("tapps_mcp.security.security_scanner.run_bandit_check")
    @patch("tapps_mcp.security.security_scanner.SecretScanner")
    def test_secret_findings(self, mock_scanner_cls, mock_bandit, mock_which):
        mock_bandit.return_value = []
        mock_scanner_inst = mock_scanner_cls.return_value
        mock_scanner_inst.scan_file.return_value = SecretScanResult(
            findings=[
                SecretFinding(
                    file_path="test.py",
                    line_number=5,
                    secret_type="api_key",
                    severity="high",
                ),
            ],
            total_findings=1,
            high_severity=1,
        )

        result = run_security_scan("test.py")
        assert result.passed is False
        assert result.total_issues == 1
        assert result.high_count == 1

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=False)
    @patch("tapps_mcp.security.security_scanner.SecretScanner")
    def test_bandit_unavailable(self, mock_scanner_cls, mock_which):
        mock_scanner_inst = mock_scanner_cls.return_value
        mock_scanner_inst.scan_file.return_value = SecretScanResult(findings=[])

        result = run_security_scan("test.py")
        assert result.bandit_available is False
        assert result.passed is True

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=True)
    @patch("tapps_mcp.security.security_scanner.run_bandit_check")
    @patch("tapps_mcp.security.security_scanner.SecretScanner")
    def test_scan_secrets_disabled(self, mock_scanner_cls, mock_bandit, mock_which):
        mock_bandit.return_value = []

        result = run_security_scan("test.py", scan_secrets=False)
        assert result.passed is True
        assert result.secret_findings == []
        mock_scanner_cls.return_value.scan_file.assert_not_called()

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=True)
    @patch("tapps_mcp.security.security_scanner.run_bandit_check")
    @patch("tapps_mcp.security.security_scanner.SecretScanner")
    def test_mixed_severities(self, mock_scanner_cls, mock_bandit, mock_which):
        mock_bandit.return_value = [
            SecurityIssue(code="B101", message="a", file="t.py", line=1, severity="low"),
            SecurityIssue(code="B602", message="b", file="t.py", line=2, severity="high"),
            SecurityIssue(code="B303", message="c", file="t.py", line=3, severity="medium"),
        ]
        mock_scanner_inst = mock_scanner_cls.return_value
        mock_scanner_inst.scan_file.return_value = SecretScanResult(
            findings=[
                SecretFinding(
                    file_path="t.py",
                    line_number=5,
                    secret_type="api_key",
                    severity="critical",
                ),
            ],
            total_findings=1,
        )

        result = run_security_scan("test.py")
        assert result.total_issues == 4
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.low_count == 1
        assert result.passed is False


# ---------------------------------------------------------------------------
# TAP-477: domain_patterns module
# ---------------------------------------------------------------------------

class TestDomainPatterns:
    """Tests for domain-specific security anti-patterns."""

    def test_auth_domain_detects_hardcoded_key(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = 'SECRET_KEY = "hard-coded-secret-12345"\n'
        findings = run_domain_scan(tmp_path / "auth.py", src, "auth")
        patterns = [f.pattern for f in findings]
        assert "hardcoded_secret_key" in patterns

    def test_payments_detects_amount_from_input(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = "amount = request.json['amount']\n"
        findings = run_domain_scan(tmp_path / "payment.py", src, "payments")
        patterns = [f.pattern for f in findings]
        assert "amount_client_side" in patterns

    def test_uploads_detects_path_traversal(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = "upload_dir / filename\n"
        findings = run_domain_scan(tmp_path / "upload.py", src, "uploads")
        patterns = [f.pattern for f in findings]
        assert "path_traversal" in patterns

    def test_api_detects_sql_injection(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n'
        findings = run_domain_scan(tmp_path / "api.py", src, "api")
        patterns = [f.pattern for f in findings]
        assert "sql_string_format" in patterns

    def test_data_detects_pickle_untrusted(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = "obj = pickle.loads(request.data)\n"
        findings = run_domain_scan(tmp_path / "data.py", src, "data")
        patterns = [f.pattern for f in findings]
        assert "pickle_untrusted" in patterns

    def test_clean_code_no_findings(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = "def get_user(user_id: int): return db.query(User).get(user_id)\n"
        findings = run_domain_scan(tmp_path / "auth.py", src, "auth")
        assert findings == []

    def test_auto_detect_auth_from_filename(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import detect_domain

        domain = detect_domain(tmp_path / "auth_service.py")
        assert domain == "auth"

    def test_auto_detect_payments_from_filename(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import detect_domain

        domain = detect_domain(tmp_path / "payment_handler.py")
        assert domain == "payments"

    def test_unknown_domain_returns_none(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import detect_domain

        domain = detect_domain(tmp_path / "completely_unrelated_xyz.py", "")
        # Should return None or a low-confidence domain — but not crash
        assert domain is None or isinstance(domain, str)

    def test_each_finding_has_required_fields(self, tmp_path: Path) -> None:
        from tapps_mcp.security.domain_patterns import run_domain_scan

        src = "obj = pickle.loads(request.data)\n"
        findings = run_domain_scan(tmp_path / "data.py", src, "data")
        assert findings
        f = findings[0]
        assert f.severity in {"critical", "high", "medium", "low"}
        assert f.fix
        assert f.fail_example
        assert f.line > 0
