"""Static domain playbooks (ADR-0025) — deterministic guidance, not RAG experts."""

from tapps_core.playbooks.loader import load_playbook_markdown, load_playbook_markdown_by_domain
from tapps_core.playbooks.models import DomainPlaybook, LookupHint
from tapps_core.playbooks.registry import (
    DOMAIN_ALIASES,
    DOMAIN_PLAYBOOKS,
    did_you_mean_domain,
    get_playbook,
    list_domain_ids,
    resolve_domain_id,
    suggest_domains_for_text,
)

__all__ = [
    "DOMAIN_ALIASES",
    "DOMAIN_PLAYBOOKS",
    "DomainPlaybook",
    "LookupHint",
    "did_you_mean_domain",
    "get_playbook",
    "list_domain_ids",
    "load_playbook_markdown",
    "load_playbook_markdown_by_domain",
    "resolve_domain_id",
    "suggest_domains_for_text",
]
