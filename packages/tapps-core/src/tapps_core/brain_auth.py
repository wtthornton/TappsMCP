"""Header builder for authenticated tapps-brain HTTP calls (TAP-521 / TAP-596).

:func:`build_brain_headers` is called by :func:`tapps_core.brain_bridge._create_http_bridge`
to produce the ``Authorization``, ``X-Project-Id``, and ``X-Agent-Id`` headers
passed to every outgoing :class:`~tapps_core.brain_bridge.HttpBrainBridge` request.

Auth scheme (tapps-brain v3.8.0, ADR-010):

- ``Authorization: Bearer <token>`` on every non-health endpoint.
- ``X-Project-Id: <project_slug>`` on every data-plane (``/v1/*``, ``/snapshot``,
  ``/info``) and MCP (``POST /mcp``) request.
- ``X-Agent-Id: <agent_id>`` on MCP transport — sourced from
  :func:`tapps_core.agent_identity.get_stable_agent_id`.
- ``/admin/*`` reuses the same Bearer token; there is no separate system token.

Strict vs. best-effort resolution:

- ``TAPPS_BRAIN_STRICT=1`` → raise :class:`BrainAuthConfigError` when any
  required value is missing. Use in CI / production where a misconfigured
  tenant must fail loudly.
- Otherwise → emit a ``structlog.warning`` and return a best-effort dict with
  missing keys omitted. Back-compat during the migration window.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog

from tapps_core.agent_identity import get_stable_agent_id

if TYPE_CHECKING:
    from tapps_core.config.settings import TappsMCPSettings

logger = structlog.get_logger(__name__)

_STRICT_ENV_VAR = "TAPPS_BRAIN_STRICT"


class BrainAuthConfigError(Exception):
    """Raised in strict mode when required tapps-brain auth config is missing."""


def _strict_mode() -> bool:
    """Return True when ``TAPPS_BRAIN_STRICT`` is set to a truthy value."""
    raw = os.environ.get(_STRICT_ENV_VAR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def build_brain_headers(
    settings: TappsMCPSettings,
    *,
    admin: bool = False,
) -> dict[str, str]:
    """Build headers for an outgoing tapps-brain HTTP call.

    Returns a dict containing up to three keys: ``Authorization``,
    ``X-Project-Id``, ``X-Agent-Id``. The Bearer token is read from
    ``settings.memory.brain_auth_token`` (a :class:`pydantic.SecretStr`), the
    project slug from ``settings.memory.brain_project_id``, and the agent id
    from :func:`tapps_core.agent_identity.get_stable_agent_id`.

    Args:
        settings: The root TappsMCP settings object.
        admin: Reserved for future symmetry between data-plane and ``/admin/*``
            requests. Currently ignored — tapps-brain v3.8.0 reuses the same
            Bearer token for both, so callers do not need to swap tokens.

    Returns:
        A header dict suitable for ``httpx.AsyncClient`` requests. Keys are
        only present when the corresponding value is configured.

    Raises:
        BrainAuthConfigError: When ``TAPPS_BRAIN_STRICT`` is truthy and any
            required value is missing.
    """
    del admin  # Reserved for future per-endpoint token scoping.

    memory = settings.memory
    token_secret = memory.brain_auth_token
    project_id = memory.brain_project_id
    agent_id = get_stable_agent_id(settings)

    headers: dict[str, str] = {}
    missing: list[str] = []

    if token_secret is not None:
        headers["Authorization"] = f"Bearer {token_secret.get_secret_value()}"
    else:
        missing.append("brain_auth_token")

    if project_id:
        headers["X-Project-Id"] = project_id
    else:
        missing.append("brain_project_id")

    if agent_id:
        headers["X-Agent-Id"] = agent_id
    else:
        # ``get_stable_agent_id`` always returns a non-empty string in
        # practice, but guard against the degenerate case for completeness.
        missing.append("agent_id")

    if missing:
        if _strict_mode():
            # Never include the token value in the error message.
            raise BrainAuthConfigError(
                f"tapps-brain auth config incomplete (strict mode): missing={sorted(missing)}"
            )
        logger.warning(
            "brain_auth.incomplete_config",
            missing=sorted(missing),
        )

    return headers


__all__ = ["BrainAuthConfigError", "build_brain_headers"]
