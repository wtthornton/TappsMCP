"""Domain playbook MCP tool handler (ADR-0025)."""

from __future__ import annotations

import time
from typing import Any

from tapps_core.playbooks.loader import load_playbook_markdown_by_domain
from tapps_core.playbooks.registry import (
    did_you_mean_domain,
    list_domain_ids,
    resolve_domain_id,
)


def build_domain_playbook_payload(
    domain: str,
    *,
    include_tool_sequence: bool = True,
) -> dict[str, Any]:
    """Return deterministic playbook payload for *domain*."""
    resolved = resolve_domain_id(domain)
    if resolved is None:
        suggestions = did_you_mean_domain(domain)
        return {
            "ok": False,
            "domain": domain,
            "error": "unknown_domain",
            "available_domains": list_domain_ids(),
            "did_you_mean": suggestions,
        }

    meta, markdown = load_playbook_markdown_by_domain(resolved)
    payload: dict[str, Any] = {
        "ok": True,
        "domain": meta.domain_id,
        "display_name": meta.display_name,
        "playbook_markdown": markdown,
        "lookup_hints": [hint.model_dump() for hint in meta.lookup_hints],
        "checklist_task_type": meta.checklist_task_type,
        "source": "bundled",
    }
    if include_tool_sequence:
        payload["recommended_tools"] = list(meta.recommended_tools)
        payload["tool_sequence"] = [
            "tapps_session_start",
            *meta.recommended_tools,
            "tapps_validate_changed",
            "tapps_checklist",
        ]
    return payload


async def run_tapps_domain_playbook(
    domain: str,
    include_tool_sequence: bool = True,
) -> dict[str, Any]:
    """Async wrapper for MCP registration."""
    return build_domain_playbook_payload(
        domain,
        include_tool_sequence=include_tool_sequence,
    )


async def tapps_domain_playbook(
    domain: str,
    include_tool_sequence: bool = True,
) -> dict[str, Any]:
    """Return a bundled domain checklist and suggested TAPPS tool order.

    Deterministic: same domain input returns the same playbook markdown.
    Use before domain-specific work (testing, security, frontend) when a skill
    is not loaded. Does not call external APIs or LLMs.

    Args:
        domain: Domain id or alias (e.g. ``testing-strategies``, ``security``,
            ``frontend``, ``ux``).
        include_tool_sequence: When true (default), include ``recommended_tools``
            and a suggested ``tool_sequence`` list.
    """
    from tapps_mcp.server_helpers import error_response, success_response

    start = time.perf_counter_ns()
    from tapps_mcp.server import _record_call, _record_execution

    _record_call("tapps_domain_playbook")

    domain = domain.strip()
    if not domain:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_domain_playbook", start)
        return error_response(
            "tapps_domain_playbook",
            "MISSING_DOMAIN",
            "domain is required",
        )

    data = await run_tapps_domain_playbook(
        domain,
        include_tool_sequence=include_tool_sequence,
    )
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_domain_playbook", start)

    if not data.get("ok"):
        return error_response(
            "tapps_domain_playbook",
            "UNKNOWN_DOMAIN",
            f"Unknown domain playbook: {domain}",
            extra={"details": data},
        )

    return success_response("tapps_domain_playbook", elapsed_ms, data)
