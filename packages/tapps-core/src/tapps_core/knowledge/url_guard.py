"""URL validation guard for custom doc-source fetches (TAP-1791).

Prevents SSRF, scheme abuse, and uncontrolled response sizes when the MCP server
fetches a user-controlled URL from ``settings.doc_sources``.

Guards applied:
- Scheme must be https:// (or http:// only when ``allow_http`` is True).
- Host must resolve to a non-private/non-loopback/non-link-local IP, unless the
  hostname is explicitly listed in ``allow_private_hosts``.
- The fetch helper streams the response with an explicit max-bytes ceiling and
  aborts early on Content-Length over-budget.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


class UrlGuardError(ValueError):
    """Raised when a doc-source URL fails the SSRF guard."""


@dataclass(frozen=True)
class UrlGuardConfig:
    allow_http: bool
    allow_private_hosts: frozenset[str]
    max_bytes: int


def validate_doc_source_url(url: str, config: UrlGuardConfig) -> str:
    """Validate a doc-source URL against the SSRF guard.

    Returns the URL unchanged if valid. Raises :class:`UrlGuardError` otherwise.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme == "https":
        pass
    elif scheme == "http":
        if not config.allow_http:
            raise UrlGuardError(f"http:// scheme not allowed: {url}")
    else:
        raise UrlGuardError(f"unsupported scheme {scheme!r}: {url}")

    host = (parsed.hostname or "").strip()
    if not host:
        raise UrlGuardError(f"missing host: {url}")

    host_lower = host.lower()
    if host_lower in config.allow_private_hosts:
        return url

    for address in _resolve_addresses(host):
        if _is_blocked_address(address):
            raise UrlGuardError(
                f"host {host!r} resolves to blocked address {address}: {url}",
            )
    return url


def _resolve_addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Return parsed IP addresses for *host* (literal or resolved via DNS)."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlGuardError(f"unable to resolve host {host!r}: {exc}") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        try:
            addresses.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    if not addresses:
        raise UrlGuardError(f"no usable addresses for host {host!r}")
    return addresses


def _is_blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified,
    )
