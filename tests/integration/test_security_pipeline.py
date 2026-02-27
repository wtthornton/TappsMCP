"""Integration test: security scanning pipeline.

Tests the unified security scanner combining bandit + secret detection.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.security.security_scanner import run_security_scan
from tapps_mcp.tools.subprocess_utils import CommandResult


@pytest.mark.integration
class TestSecurityPipeline:
    @pytest.fixture
    def clean_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "clean.py"
        f.write_text(
            '"""Clean module."""\n\ndef hello() -> str:\n    return "hi"\n',
            encoding="utf-8",
        )
        return f

    @pytest.fixture
    def secret_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "secrets.py"
        f.write_text(
            'api_key = "ABCDEF1234567890abcdef"\n',
            encoding="utf-8",
        )
        return f

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=False)
    def test_clean_file_no_bandit(self, mock_which, clean_file: Path):
        """Clean file passes even without bandit."""
        result = run_security_scan(str(clean_file))
        assert result.passed is True
        assert result.total_issues == 0
        assert result.bandit_available is False

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=False)
    def test_secret_detected(self, mock_which, secret_file: Path):
        """Secret scanner catches hardcoded API key."""
        result = run_security_scan(str(secret_file))
        assert result.passed is False
        assert result.total_issues >= 1
        assert result.high_count >= 1
        assert any(f.secret_type == "api_key" for f in result.secret_findings)

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=True)
    @patch("tapps_mcp.tools.bandit.run_command")
    def test_bandit_plus_secrets(self, mock_cmd, mock_which, secret_file: Path):
        """Both bandit and secret scanning results are combined."""
        import json

        mock_cmd.return_value = CommandResult(
            returncode=1,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "test_id": "B105",
                            "issue_text": "Hardcoded password string",
                            "filename": str(secret_file),
                            "line_number": 1,
                            "issue_severity": "LOW",
                            "issue_confidence": "MEDIUM",
                        }
                    ]
                }
            ),
            stderr="",
        )

        result = run_security_scan(str(secret_file))
        assert result.bandit_available is True
        # Should have both bandit issues and secret findings
        assert len(result.bandit_issues) >= 1
        assert len(result.secret_findings) >= 1
        assert result.total_issues == len(result.bandit_issues) + len(result.secret_findings)

    @patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=False)
    def test_secrets_disabled(self, mock_which, secret_file: Path):
        """With scan_secrets=False, only bandit runs."""
        result = run_security_scan(str(secret_file), scan_secrets=False)
        assert result.secret_findings == []
        assert result.bandit_available is False


@pytest.mark.integration
class TestSecretScannerIntegration:
    """Integration tests for the SecretScanner standalone."""

    def test_scan_real_file(self, tmp_path: Path):
        """Scan a real file on disk."""
        from tapps_mcp.security.secret_scanner import SecretScanner

        f = tmp_path / "config.py"
        f.write_text(
            'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n'
            'password = "hunter2!xyz"\n'
            '# token = "not_detected_in_comment"\n'
            'safe_var = "hello"\n',
            encoding="utf-8",
        )

        scanner = SecretScanner()
        result = scanner.scan_file(str(f))
        assert result.scanned_files == 1
        assert result.total_findings >= 1  # AWS key at minimum
        # Comment should be ignored
        assert all(f.line_number != 3 for f in result.findings)
