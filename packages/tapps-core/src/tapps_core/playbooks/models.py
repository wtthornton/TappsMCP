"""Domain playbook models (ADR-0025)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LookupHint(BaseModel):
    """Library documentation lookup suggestion for a domain playbook."""

    library: str
    topic: str = ""


class DomainPlaybook(BaseModel):
    """Static domain playbook metadata — deterministic, no RAG."""

    domain_id: str
    display_name: str
    playbook_file: str
    lookup_hints: list[LookupHint] = Field(default_factory=list)
    recommended_tools: list[str] = Field(default_factory=list)
    checklist_task_type: str = "feature"
    epic_keywords: list[str] = Field(default_factory=list)
