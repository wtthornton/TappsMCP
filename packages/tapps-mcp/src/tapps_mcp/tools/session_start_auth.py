"""Brain auth-probe failure detection for ``tapps_session_start`` (TAP-6881).

Extracted from ``server_pipeline_tools.py`` to shrink that module toward
the maintainability gate. ``_detect_brain_auth_failure`` is patched by
tests via ``patch("tapps_mcp.server_pipeline_tools._detect_brain_auth_failure")``
-- the façade re-exports it (``as _detect_brain_auth_failure``) so the
patch target keeps resolving to this same function object regardless of
which module physically defines it.
"""

from __future__ import annotations

from typing import Any


def _classify_brain_auth_token(settings: Any) -> str:
    """TAP-1336: Classify the configured brain auth token without leaking it."""
    from tapps_core.brain_auth import classify_brain_auth_token

    return classify_brain_auth_token(settings)


def _detect_brain_auth_failure(
    settings: Any,
    memory_status: dict[str, Any] | None,
    elapsed_ms: int,
) -> dict[str, Any] | None:
    """TAP-1082 / TAP-1257 / TAP-1336: Detect tapps-brain auth-probe failures and return a hard error.

    Returns ``None`` when memory is disabled, when the agent has opted in to
    tolerating auth failures (``memory.tolerate_brain_auth_failure``), or when
    the auth probe did not return a recognised auth/identity failure.

    Recognised failure shapes:
      * HTTP 401 / 403 with literal ``${...}`` token →
        ``code='brain_auth_token_unsubstituted'`` (TAP-1336). The MCP subprocess
        received the unexpanded ``.mcp.json`` template; Claude Code's launching
        shell did not have ``TAPPS_BRAIN_AUTH_TOKEN`` exported.
      * HTTP 401 / 403 with empty/missing token →
        ``code='brain_auth_token_missing'`` (TAP-1336).
      * HTTP 401 / 403 with a present token → ``code='brain_auth_failed'``
        (TAP-1082). The server rejected the token (rotated / revoked / wrong).
      * HTTP 400 with ``X-Project-Id`` in the body → ``code='brain_project_id_missing'``
        (TAP-1257). tapps-brain 3.14.x returns this when the
        ``X-Project-Id`` header is missing on ``/mcp`` requests.
    """
    from tapps_mcp.server_helpers import error_response

    if not getattr(settings.memory, "enabled", True):
        return None
    if getattr(settings.memory, "tolerate_brain_auth_failure", False):
        return None
    if not isinstance(memory_status, dict):
        return None
    auth_probe = memory_status.get("auth_probe")
    if not isinstance(auth_probe, dict):
        return None
    http_status = auth_probe.get("http_status")
    detail_raw = auth_probe.get("detail") or auth_probe.get("error") or ""
    detail = str(detail_raw)

    if http_status == 400 and "X-Project-Id" in detail:
        message = (
            "tapps-brain rejected the /mcp request with HTTP 400 because the "
            "X-Project-Id header is missing. Memory operations cannot proceed."
        )
        return error_response(
            "tapps_session_start",
            "brain_project_id_missing",
            message,
            extra={
                "http_status": http_status,
                "memory_status": memory_status,
                "elapsed_ms": elapsed_ms,
                "next_steps": [
                    (
                        "Set TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID in your env or "
                        ".mcp.json env block to the registered tapps-brain project slug"
                    ),
                    (
                        "Or set memory.brain_project_id (or memory.project_id, "
                        "auto-derived) in .tapps-mcp.yaml"
                    ),
                    (
                        "If running offline / without tapps-brain, set "
                        "memory.tolerate_brain_auth_failure: true in .tapps-mcp.yaml "
                        "to keep the degraded behavior"
                    ),
                ],
            },
        )

    if http_status not in (401, 403):
        return None

    token_state = _classify_brain_auth_token(settings)
    tolerate_step = (
        "If running offline / without tapps-brain, set "
        "memory.tolerate_brain_auth_failure: true in .tapps-mcp.yaml "
        "to keep the degraded behavior"
    )

    if token_state == "unsubstituted":  # noqa: S105  (state label, not a secret)
        code = "brain_auth_token_unsubstituted"
        message = (
            f"tapps-brain auth probe returned HTTP {http_status}, and the MCP "
            "subprocess received the literal ${TAPPS_BRAIN_AUTH_TOKEN} "
            "template instead of an expanded token. Claude Code did not "
            "substitute the env-var reference in .mcp.json — almost always "
            "because TAPPS_BRAIN_AUTH_TOKEN was not exported in the shell "
            "that launched Claude Code."
        )
        next_steps = [
            (
                "Export TAPPS_BRAIN_AUTH_TOKEN in your shell BEFORE launching "
                "Claude Code (e.g. add it to ~/.bashrc / ~/.zshrc), then "
                "restart Claude Code so the MCP subprocess inherits it"
            ),
            (
                "Or replace ${TAPPS_BRAIN_AUTH_TOKEN} in .mcp.json with the "
                "literal token value under the tapps-mcp env block"
            ),
            tolerate_step,
        ]
    elif token_state == "missing":  # noqa: S105  (state label, not a secret)
        code = "brain_auth_token_missing"
        message = (
            f"tapps-brain auth probe returned HTTP {http_status} and no "
            "Bearer token is configured for the MCP subprocess. The "
            "Authorization header was not sent or was empty."
        )
        next_steps = [
            (
                "Set TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN in the tapps-mcp env "
                "block of .mcp.json (recommended — survives shell restarts)"
            ),
            (
                "Or export TAPPS_BRAIN_AUTH_TOKEN in the shell that launches "
                "Claude Code so ${TAPPS_BRAIN_AUTH_TOKEN} substitution works"
            ),
            tolerate_step,
        ]
    else:  # "present"
        code = "brain_auth_failed"
        message = (
            f"tapps-brain auth probe returned HTTP {http_status}: "
            f"{detail or 'unauthorized'}. The configured token was rejected by "
            "the server (rotated, revoked, or wrong). Memory operations "
            "cannot proceed."
        )
        next_steps = [
            (
                "Verify the TAPPS_BRAIN_AUTH_TOKEN value matches the token "
                "tapps-brain is configured to accept (check the brain server's "
                "TAPPS_BRAIN_AUTH_TOKEN env)"
            ),
            "Rotate the token on the brain server and update both sides if compromised",
            tolerate_step,
        ]

    return error_response(
        "tapps_session_start",
        code,
        message,
        extra={
            "http_status": http_status,
            "memory_status": memory_status,
            "elapsed_ms": elapsed_ms,
            "token_state": token_state,
            "next_steps": next_steps,
        },
    )


__all__ = ["_classify_brain_auth_token", "_detect_brain_auth_failure"]
