"""Load bundled domain playbook markdown from package data."""

from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_core.playbooks.models import DomainPlaybook

_PLAYBOOKS_PACKAGE = "tapps_core.playbooks.data"


def load_playbook_markdown(meta: DomainPlaybook) -> str:
    """Return playbook markdown for *meta*; raises FileNotFoundError if missing."""
    filename = meta.playbook_file
    traversable = resources.files(_PLAYBOOKS_PACKAGE)
    path = traversable.joinpath(filename)
    if not path.is_file():
        msg = f"Playbook file not found: {filename}"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")


def load_playbook_markdown_by_domain(domain: str) -> tuple[DomainPlaybook, str]:
    """Resolve *domain* and return (metadata, markdown body)."""
    from tapps_core.playbooks.registry import get_playbook

    meta = get_playbook(domain)
    if meta is None:
        msg = f"Unknown domain playbook: {domain}"
        raise KeyError(msg)
    return meta, load_playbook_markdown(meta)
