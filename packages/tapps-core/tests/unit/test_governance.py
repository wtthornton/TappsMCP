"""Tests for security.governance."""

from __future__ import annotations

from tapps_core.security.governance import (
    GovernanceLayer,
    GovernancePolicy,
)


class TestGovernanceLayer:
    def test_clean_content_passes(self) -> None:
        gl = GovernanceLayer()
        result = gl.filter_content("This is clean content")
        assert result.allowed is True
        assert result.detected_issues == []
        assert result.filtered_content is None

    def test_api_key_detected_and_redacted(self) -> None:
        gl = GovernanceLayer()
        content = 'api_key = "sk_test_1234567890abcdefghij"'
        result = gl.filter_content(content)
        assert result.allowed is False
        assert any("Secret" in issue for issue in result.detected_issues)
        assert result.filtered_content is not None
        assert "sk_test_1234567890" not in result.filtered_content

    def test_private_key_detected(self) -> None:
        gl = GovernanceLayer()
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        result = gl.filter_content(content)
        assert result.allowed is False

    def test_ssn_detected_when_multiple(self) -> None:
        gl = GovernanceLayer()
        content = "SSN: 123-45-6789 and 987-65-4321"
        result = gl.filter_content(content)
        assert result.allowed is False
        assert any("PII" in issue for issue in result.detected_issues)

    def test_single_ssn_flagged(self) -> None:
        """Even a single SSN should be redacted to avoid data leakage."""
        gl = GovernanceLayer()
        content = "SSN: 123-45-6789"
        result = gl.filter_content(content)
        assert result.allowed is False
        assert result.filtered_content is not None
        assert "123-45-6789" not in result.filtered_content

    def test_connection_string_detected(self) -> None:
        gl = GovernanceLayer()
        content = 'connection_string = "Server=db;Database=prod;User=admin;Password=secret"'
        result = gl.filter_content(content)
        assert result.allowed is False

    def test_disabled_filters_allow_all(self) -> None:
        policy = GovernancePolicy(
            filter_secrets=False,
            filter_tokens=False,
            filter_credentials=False,
            filter_pii=False,
        )
        gl = GovernanceLayer(policy)
        content = 'api_key = "sk_test_1234567890abcdefghij"'
        result = gl.filter_content(content)
        assert result.allowed is True
