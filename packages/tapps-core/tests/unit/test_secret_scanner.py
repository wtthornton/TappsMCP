"""Tests for security.secret_scanner."""

from __future__ import annotations

import pytest

from tapps_core.security.secret_scanner import (
    SecretFinding,
    SecretScanner,
    SecretScanResult,
)


class TestSecretFinding:
    def test_creation(self) -> None:
        f = SecretFinding(
            file_path="test.py",
            line_number=10,
            secret_type="api_key",
            severity="high",
        )
        assert f.file_path == "test.py"
        assert f.context is None


class TestSecretScanResult:
    def test_defaults(self) -> None:
        r = SecretScanResult()
        assert r.total_findings == 0
        assert r.passed is True
        assert r.findings == []

    def test_with_findings(self) -> None:
        findings = [
            SecretFinding(
                file_path="t.py",
                line_number=1,
                secret_type="api_key",
                severity="high",
            )
        ]
        r = SecretScanResult(
            total_findings=1,
            high_severity=1,
            findings=findings,
            scanned_files=1,
            passed=False,
        )
        assert r.passed is False


class TestSecretScanner:
    def setup_method(self) -> None:
        self.scanner = SecretScanner()

    # --- API key patterns ---

    @pytest.mark.parametrize(
        "code",
        [
            'api_key = "ABCDEF1234567890abcdef"',
            'api_key: "ABCDEF1234567890abcdef"',
            'apikey = "ABCDEF1234567890abcdef"',
        ],
        ids=["equals", "colon", "no-separator"],
    )
    def test_detect_api_key_variants(self, code: str) -> None:
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1

    def test_detect_api_key_type_and_severity(self) -> None:
        code = 'api_key = "ABCDEF1234567890abcdef"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1
        assert findings[0].secret_type == "api_key"
        assert findings[0].severity == "high"

    # --- Secret key patterns ---

    def test_detect_secret_key(self) -> None:
        code = 'secret_key = "mysupersecretkey1234567"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1
        assert any(f.secret_type == "secret_key" for f in findings)

    # --- Password patterns ---

    def test_detect_password(self) -> None:
        code = 'password = "P@ssw0rd!123"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1
        assert any(f.secret_type == "passwd" for f in findings)
        assert any(f.severity == "low" for f in findings)

    # --- Token patterns ---

    @pytest.mark.parametrize(
        "code",
        [
            'token = "ghp_1234567890abcdefghij"',
            'access_token = "eyJhbGciOiJIUzI1NiIsI"',
            'auth_token = "abcdefghijklmnopqrst1234"',
        ],
        ids=["token", "access-token", "auth-token"],
    )
    def test_detect_token_variants(self, code: str) -> None:
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1

    def test_detect_token_type(self) -> None:
        code = 'token = "ghp_1234567890abcdefghij"'
        findings = self.scanner.scan_content(code, "test.py")
        assert any(f.secret_type == "token" for f in findings)

    # --- AWS patterns ---

    def test_detect_aws_access_key(self) -> None:
        code = 'aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1
        assert any(f.secret_type == "aws_key" for f in findings)
        assert any(f.severity == "high" for f in findings)

    # --- Private key patterns ---

    @pytest.mark.parametrize(
        "code",
        [
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
        ],
        ids=["rsa", "ec", "generic"],
    )
    def test_detect_private_key_variants(self, code: str) -> None:
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1

    def test_detect_private_key_type(self) -> None:
        code = "-----BEGIN RSA PRIVATE KEY-----"
        findings = self.scanner.scan_content(code, "test.py")
        assert any(f.secret_type == "private_key" for f in findings)

    # --- OAuth patterns ---

    def test_detect_client_secret(self) -> None:
        code = 'client_secret = "my_super_secret_client_key_123"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1

    # --- Negative cases ---

    def test_clean_code(self) -> None:
        code = """
def hello():
    print("Hello, world!")
    x = 42
    return x
"""
        findings = self.scanner.scan_content(code, "test.py")
        assert findings == []

    def test_comments_ignored(self) -> None:
        code = '# api_key = "ABCDEF1234567890abcdef"'
        findings = self.scanner.scan_content(code, "test.py")
        assert findings == []

    def test_short_values_ignored(self) -> None:
        code = 'api_key = "short"'
        findings = self.scanner.scan_content(code, "test.py")
        assert findings == []

    # --- Redaction ---

    def test_context_redacted(self) -> None:
        code = 'api_key = "ABCDEF1234567890abcdef"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 1
        assert "REDACTED" in (findings[0].context or "")

    # --- scan_file ---

    def test_scan_file(self, tmp_path: object) -> None:
        from pathlib import Path

        p = Path(str(tmp_path))
        f = p / "secret.py"
        f.write_text('api_key = "ABCDEF1234567890abcdef"\n', encoding="utf-8")
        result = self.scanner.scan_file(str(f))
        assert result.total_findings >= 1
        assert result.scanned_files == 1
        assert result.passed is False  # high severity finding

    def test_scan_file_clean(self, tmp_path: object) -> None:
        from pathlib import Path

        p = Path(str(tmp_path))
        f = p / "clean.py"
        f.write_text("x = 42\n", encoding="utf-8")
        result = self.scanner.scan_file(str(f))
        assert result.total_findings == 0
        assert result.passed is True

    def test_scan_nonexistent_file(self) -> None:
        result = self.scanner.scan_file("/nonexistent/path/file.py")
        assert result.scanned_files == 0
        assert result.total_findings == 0

    # --- Line numbers ---

    def test_line_numbers_correct(self) -> None:
        code = 'x = 1\ny = 2\napi_key = "ABCDEF1234567890abcdef"\nz = 3'
        findings = self.scanner.scan_content(code, "test.py")
        assert findings[0].line_number == 3

    # --- Multiple secrets ---

    def test_multiple_secrets(self) -> None:
        code = 'api_key = "ABCDEF1234567890abcdef"\ntoken = "ghp_1234567890abcdefghij"'
        findings = self.scanner.scan_content(code, "test.py")
        assert len(findings) >= 2

    # --- Build result aggregation ---

    def test_build_result_severity_counts(self) -> None:
        findings = [
            SecretFinding(file_path="t.py", line_number=1, secret_type="api_key", severity="high"),
            SecretFinding(
                file_path="t.py", line_number=2, secret_type="token", severity="medium"
            ),
            SecretFinding(
                file_path="t.py", line_number=3, secret_type="password", severity="low"
            ),
        ]
        result = SecretScanner._build_result(findings)
        assert result.high_severity == 1
        assert result.medium_severity == 1
        assert result.low_severity == 1
        assert result.total_findings == 3
        assert result.passed is False  # has high severity
