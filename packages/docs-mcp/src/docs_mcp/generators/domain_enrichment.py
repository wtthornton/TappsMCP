"""Deterministic domain enrichment for DocsMCP generators (ADR-0025)."""

from __future__ import annotations

from typing import Any

from tapps_core.playbooks.loader import load_playbook_markdown
from tapps_core.playbooks.registry import get_playbook, suggest_domains_for_text


def _playbook_excerpt(markdown: str, *, max_length: int = 400) -> str:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    body: list[str] = []
    for line in lines:
        if line.startswith("#"):
            continue
        body.append(line)
        if len(" ".join(body)) >= max_length:
            break
    text = " ".join(body).strip()
    if len(text) > max_length:
        return text[: max_length - 3].rsplit(" ", 1)[0] + "..."
    return text


def build_domain_guidance(
    context: str,
    *,
    limit: int = 3,
    max_excerpt_chars: int = 400,
) -> list[dict[str, str]]:
    """Return expert_guidance-shaped entries from bundled playbooks."""
    guidance: list[dict[str, str]] = []
    for domain_id in suggest_domains_for_text(context, limit=limit):
        meta = get_playbook(domain_id)
        if meta is None:
            continue
        try:
            markdown = load_playbook_markdown(meta)
        except FileNotFoundError:
            continue
        advice = _playbook_excerpt(markdown, max_length=max_excerpt_chars)
        if not advice:
            continue
        guidance.append(
            {
                "domain": meta.display_name,
                "expert": meta.display_name,
                "advice": advice,
                "confidence": "100%",
                "source": "domain_playbook",
            }
        )
    return guidance


def enrich_expert_guidance(
    config_text: str,
    enrichment: dict[str, Any],
    *,
    limit: int = 3,
) -> None:
    """Populate ``enrichment['expert_guidance']`` from static domain playbooks."""
    existing: list[dict[str, str]] = enrichment.get("expert_guidance", [])
    if existing:
        return
    guidance = build_domain_guidance(config_text, limit=limit)
    if guidance:
        enrichment["expert_guidance"] = guidance
