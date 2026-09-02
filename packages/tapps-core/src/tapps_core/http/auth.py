"""Bearer-token auth for the shared HTTP MCP fleet (ADR-0024, TAP-6062).

The fleet was designed as a loopback-only convenience: six long-lived
``serve --transport http`` processes that any local Cursor window can reach.
Making it consumable by an out-of-process agent runtime (AgentForge) means a
request can arrive from something other than the operator's own desktop, so
the endpoint needs an identity check before it will answer.

Two credential kinds, deliberately distinct:

``operator``
    The operator's own token (:data:`FLEET_AUTH_ENV`). Accepted by every
    fleet server; the request sees the server's normal registered profile.

``runtime``
    A credential handed to an agent runtime (:data:`FLEET_RUNTIME_ENV`).
    Accepted **only** by a server that declares ``allow_runtime_scope`` -- in
    practice ``nlt-build`` -- and the tools it may reach are narrowed further
    by the caller (see ``tapps_mcp.http_fleet_scope``). Presenting it to any
    other fleet server is a 401, not a downgrade: the other five servers are
    not exposed to this token type at all.

Auth is *off* until the operator supplies at least one token, which keeps the
existing loopback-only local workflow unchanged. Once any token is set, an
unauthenticated request is rejected.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

FLEET_AUTH_ENV: Final[str] = "TAPPS_FLEET_AUTH_TOKEN"
FLEET_RUNTIME_ENV: Final[str] = "TAPPS_FLEET_RUNTIME_TOKEN"

#: Standard bearer header. Used by curl/ops and any client that can build a
#: ``Bearer <token>`` value.
AUTHORIZATION_HEADER: Final[str] = "Authorization"

#: Whole-value token header. AgentForge's publish-time validator requires a
#: credential header to be *entirely* a ``${vault:...}`` template, so a
#: ``Bearer ${vault:...}`` value is rejected there; this header carries the
#: bare token so the vault reference can stand alone.
FLEET_CREDENTIAL_HEADER: Final[str] = "X-Tapps-Fleet-Token"

_BEARER_PREFIX: Final[str] = "bearer "

SCOPE_OPERATOR: Final[str] = "operator"
SCOPE_RUNTIME: Final[str] = "runtime"


@dataclass(frozen=True)
class FleetAuthConfig:
    """Resolved bearer-token policy for one fleet server process."""

    operator_token: str | None = None
    runtime_token: str | None = None
    allow_runtime_scope: bool = False

    @property
    def enabled(self) -> bool:
        """True when at least one token is configured (auth is then required)."""
        return bool(self.operator_token or self.runtime_token)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        allow_runtime_scope: bool = False,
    ) -> FleetAuthConfig:
        """Build the policy from ``TAPPS_FLEET_*`` variables."""
        source = os.environ if env is None else env
        return cls(
            operator_token=_clean(source.get(FLEET_AUTH_ENV)),
            runtime_token=_clean(source.get(FLEET_RUNTIME_ENV)),
            allow_runtime_scope=allow_runtime_scope,
        )

    def authenticate(self, presented: str | None) -> str | None:
        """Return the scope for *presented*, or ``None`` when it is rejected.

        A rejected credential is indistinguishable from a missing one on the
        wire (both 401) so the response never confirms which token was close.
        """
        if not self.enabled:
            return SCOPE_OPERATOR
        if not presented:
            return None
        if self.operator_token and secrets.compare_digest(presented, self.operator_token):
            return SCOPE_OPERATOR
        if (
            self.allow_runtime_scope
            and self.runtime_token
            and secrets.compare_digest(presented, self.runtime_token)
        ):
            return SCOPE_RUNTIME
        return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def extract_presented_token(headers: Mapping[str, str]) -> str | None:
    """Pull the bearer token out of a case-insensitive header mapping."""
    lowered = {str(k).lower(): v for k, v in headers.items()}
    direct = _clean(lowered.get(FLEET_CREDENTIAL_HEADER.lower()))
    if direct:
        return direct
    raw = _clean(lowered.get(AUTHORIZATION_HEADER.lower()))
    if raw is None:
        return None
    if raw.lower().startswith(_BEARER_PREFIX):
        return _clean(raw[len(_BEARER_PREFIX) :])
    return None
