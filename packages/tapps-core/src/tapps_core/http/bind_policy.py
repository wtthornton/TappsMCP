"""Startup bind guard for the HTTP MCP fleet (ADR-0024, TAP-6062).

Story ordering here is structural, not documentary: binding a fleet server to
anything other than loopback is only meaningful once bearer auth exists, so a
non-loopback bind with auth disabled must not start at all. Enforcing it in
prose (\"remember to set a token first\") would leave an unauthenticated MCP
server -- one that can run scans and read files -- listening on a routable
interface the moment somebody sets ``TAPPS_FLEET_HOST``.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Final

from tapps_core.http.auth import (
    FLEET_AUTH_ENV,
    FLEET_RUNTIME_ENV,
    FleetAuthConfig,
)

#: Hostnames that resolve to loopback without a DNS round-trip.
LOOPBACK_HOST_NAMES: Final[frozenset[str]] = frozenset({"localhost", "localhost.localdomain"})


class NonLoopbackBindRefusedError(RuntimeError):
    """Raised when a fleet server would bind off-loopback without auth."""


def is_loopback_host(host: str) -> bool:
    """True when *host* can only be reached from this machine.

    Wildcards (``0.0.0.0``, ``::``) are explicitly not loopback: they bind
    every interface, which is the case this guard exists for.
    """
    candidate = (host or "").strip()
    if not candidate:
        # An empty bind host is uvicorn's "all interfaces" default.
        return False
    if candidate.lower() in LOOPBACK_HOST_NAMES:
        return True
    stripped = candidate.strip("[]")
    try:
        address = ipaddress.ip_address(stripped)
    except ValueError:
        # A real hostname we cannot classify offline. Refuse to call it
        # loopback -- unknown refuses, never skips.
        return False
    return bool(address.is_loopback)


def require_safe_bind(host: str, *, auth: FleetAuthConfig) -> None:
    """Refuse to start an unauthenticated server on a non-loopback address."""
    if is_loopback_host(host) or auth.enabled:
        return
    msg = (
        f"Refusing to start: HTTP fleet bind host {host!r} is not loopback and "
        f"bearer auth is disabled. Set {FLEET_AUTH_ENV} (and optionally "
        f"{FLEET_RUNTIME_ENV} for agent-runtime callers) before exposing the "
        "fleet off 127.0.0.1, or bind to 127.0.0.1."
    )
    raise NonLoopbackBindRefusedError(msg)


def resolve_fleet_auth(
    host: str,
    *,
    allow_runtime_scope: bool = False,
    env: Mapping[str, str] | None = None,
) -> FleetAuthConfig:
    """Resolve a fleet server's auth policy and enforce its bind guard.

    One call rather than two so a server cannot wire up auth and forget the
    guard: reading the tokens and deciding whether this bind is permitted are
    the same decision, and splitting them is how the unauthenticated
    off-loopback listener gets shipped.
    """
    auth = FleetAuthConfig.from_env(env, allow_runtime_scope=allow_runtime_scope)
    require_safe_bind(host, auth=auth)
    return auth
