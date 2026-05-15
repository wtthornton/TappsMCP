"""Unit tests for the doc-source URL SSRF guard (TAP-1791)."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from tapps_core.knowledge.url_guard import (
    UrlGuardConfig,
    UrlGuardError,
    validate_doc_source_url,
)


def _make_config(
    *,
    allow_http: bool = False,
    allow_private_hosts: tuple[str, ...] = (),
    max_bytes: int = 5 * 1024 * 1024,
) -> UrlGuardConfig:
    return UrlGuardConfig(
        allow_http=allow_http,
        allow_private_hosts=frozenset(h.lower() for h in allow_private_hosts),
        max_bytes=max_bytes,
    )


class TestSchemeGuard:
    def test_https_passes(self) -> None:
        with patch(
            "tapps_core.knowledge.url_guard.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
        ):
            assert (
                validate_doc_source_url("https://example.com/docs.md", _make_config())
                == "https://example.com/docs.md"
            )

    def test_http_rejected_by_default(self) -> None:
        with pytest.raises(UrlGuardError, match="http:// scheme not allowed"):
            validate_doc_source_url("http://example.com/docs.md", _make_config())

    def test_http_allowed_when_opted_in(self) -> None:
        with patch(
            "tapps_core.knowledge.url_guard.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
        ):
            assert (
                validate_doc_source_url(
                    "http://example.com/docs.md", _make_config(allow_http=True)
                )
                == "http://example.com/docs.md"
            )

    def test_file_scheme_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="unsupported scheme"):
            validate_doc_source_url("file:///etc/passwd", _make_config())

    def test_missing_host_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="missing host"):
            validate_doc_source_url("https:///path", _make_config())


class TestSsrfGuard:
    def test_imds_literal_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="blocked address"):
            validate_doc_source_url(
                "http://169.254.169.254/latest/meta-data/",
                _make_config(allow_http=True),
            )

    def test_loopback_literal_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="blocked address"):
            validate_doc_source_url(
                "http://127.0.0.1:8080/admin",
                _make_config(allow_http=True),
            )

    def test_localhost_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="blocked address"):
            validate_doc_source_url(
                "http://localhost:8080/admin",
                _make_config(allow_http=True),
            )

    def test_private_rfc1918_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="blocked address"):
            validate_doc_source_url(
                "http://10.0.0.5/admin",
                _make_config(allow_http=True),
            )

    def test_ipv6_loopback_rejected(self) -> None:
        with pytest.raises(UrlGuardError, match="blocked address"):
            validate_doc_source_url(
                "http://[::1]/admin",
                _make_config(allow_http=True),
            )

    def test_allowlisted_host_passes(self) -> None:
        assert (
            validate_doc_source_url(
                "http://localhost:8080/admin",
                _make_config(allow_http=True, allow_private_hosts=("localhost",)),
            )
            == "http://localhost:8080/admin"
        )

    def test_allowlist_is_case_insensitive(self) -> None:
        assert (
            validate_doc_source_url(
                "http://INTERNAL-DOCS/path",
                _make_config(allow_http=True, allow_private_hosts=("internal-docs",)),
            )
            == "http://INTERNAL-DOCS/path"
        )

    def test_dns_resolution_failure_propagates(self) -> None:
        with patch(
            "tapps_core.knowledge.url_guard.socket.getaddrinfo",
            side_effect=socket.gaierror("no such host"),
        ), pytest.raises(UrlGuardError, match="unable to resolve"):
            validate_doc_source_url(
                "https://does-not-exist.invalid/docs",
                _make_config(),
            )

    def test_dns_resolved_private_address_rejected(self) -> None:
        # Public-looking hostname resolves to a private IP — DNS-rebind defence.
        with patch(
            "tapps_core.knowledge.url_guard.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("10.0.0.5", 0))],
        ), pytest.raises(UrlGuardError, match="blocked address"):
            validate_doc_source_url(
                "https://looks-public.example/docs",
                _make_config(),
            )
