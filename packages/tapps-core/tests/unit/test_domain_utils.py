"""Unit tests for tapps_core.experts.domain_utils."""

from __future__ import annotations

from tapps_core.experts.domain_utils import sanitize_domain_for_path


class TestSanitizeDomainForPath:
    """Tests for sanitize_domain_for_path."""

    def test_simple_domain(self) -> None:
        assert sanitize_domain_for_path("home-automation") == "home-automation"

    def test_empty_string(self) -> None:
        assert sanitize_domain_for_path("") == "unknown"

    def test_known_mapping_performance(self) -> None:
        assert sanitize_domain_for_path("performance-optimization") == "performance"

    def test_known_mapping_testing(self) -> None:
        assert sanitize_domain_for_path("testing-strategies") == "testing"

    def test_known_mapping_ai(self) -> None:
        assert sanitize_domain_for_path("ai-agent-framework") == "ai-frameworks"

    def test_url_simple(self) -> None:
        result = sanitize_domain_for_path("https://www.home-assistant.io/docs/")
        assert result == "home-assistant.io-docs"

    def test_url_with_path(self) -> None:
        result = sanitize_domain_for_path("https://example.com/api/v1")
        assert result == "example.com-api-v1"

    def test_lowercase(self) -> None:
        result = sanitize_domain_for_path("MyDomain")
        assert result == "mydomain"

    def test_invalid_chars_replaced(self) -> None:
        result = sanitize_domain_for_path("a<b>c:d")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_consecutive_hyphens_collapsed(self) -> None:
        result = sanitize_domain_for_path("a---b")
        assert result == "a-b"

    def test_leading_trailing_dots_stripped(self) -> None:
        result = sanitize_domain_for_path(".hidden.")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_long_domain_truncated(self) -> None:
        long = "a" * 300
        result = sanitize_domain_for_path(long)
        assert len(result) <= 200
