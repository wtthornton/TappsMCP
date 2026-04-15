"""Federation UX: explain where recalled insights came from (STORY-102.6).

When tapps-brain federation returns results from remote projects, the LLM
needs to know where each insight originated so it can:
1. Weight the insight appropriately (local vs. remote)
2. Display the provenance to the user when asked
3. Avoid blindly applying remote patterns that may not fit the local project

This module provides:
- :class:`ProvenanceAnnotation` — structured provenance metadata
- :func:`annotate_provenance` — attach provenance to a list of InsightEntry records
- :func:`format_provenance_summary` — human-readable one-liner per annotation

Provenance annotation is a VIEW operation — it does not modify the stored
InsightEntry records. It adds a ``_provenance`` dict to a serialised entry
dict for LLM consumption.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tapps_core.insights.models import InsightEntry, InsightOrigin


class ProvenanceAnnotation(BaseModel):
    """Provenance metadata for a recalled InsightEntry.

    Attached as ``_provenance`` to the serialised entry dict returned by
    :func:`annotate_provenance`.
    """

    key: str = Field(description="Key of the InsightEntry being annotated.")
    origin_server: InsightOrigin = Field(
        default=InsightOrigin.unknown,
        description="Which MCP server produced this insight.",
    )
    origin_project: str = Field(
        default="",
        description="Project name where the insight was written (empty = local).",
    )
    origin_scope: str = Field(
        default="project",
        description="Scope of the original entry (project/shared/branch).",
    )
    recalled_from: str = Field(
        default="local",
        description=(
            "Where this insight was recalled from: 'local' or a federation "
            "project identifier (e.g. 'tapps-brain:my-other-project')."
        ),
    )
    is_federated: bool = Field(
        default=False,
        description="True when recalled from a remote federated project.",
    )

    def summary_line(self) -> str:
        """Return a one-line human-readable provenance string."""
        source = self.recalled_from if self.is_federated else "this project"
        server = self.origin_server if self.origin_server != InsightOrigin.unknown else "unknown"
        return f"[{self.key}] from {source} via {server}"


def annotate_provenance(
    entries: list[InsightEntry],
    *,
    federation_source: str = "local",
    origin_project: str = "",
) -> list[dict[str, Any]]:
    """Serialise InsightEntry records and attach ``_provenance`` metadata.

    Args:
        entries: InsightEntry records to annotate.
        federation_source: Where the entries were recalled from.
            ``"local"`` for the current project; a federation identifier
            (e.g. ``"tapps-brain:other-project"``) for remote sources.
        origin_project: Human-readable project name. Empty = current project.

    Returns:
        List of dicts, each being the entry's ``model_dump()`` with a
        ``_provenance`` key containing a serialised :class:`ProvenanceAnnotation`.
    """
    is_federated = federation_source != "local"
    result: list[dict[str, Any]] = []

    for entry in entries:
        annotation = ProvenanceAnnotation(
            key=entry.key,
            origin_server=entry.server_origin,
            origin_project=origin_project or ("" if not is_federated else federation_source),
            origin_scope=str(entry.scope),
            recalled_from=federation_source,
            is_federated=is_federated,
        )
        data = entry.model_dump()
        data["_provenance"] = annotation.model_dump()
        result.append(data)

    return result


def format_provenance_summary(annotated: list[dict[str, Any]]) -> str:
    """Produce a human-readable recall provenance block.

    Args:
        annotated: Output of :func:`annotate_provenance`.

    Returns:
        Markdown-formatted block listing each recalled insight's provenance.
        Empty string when no entries are provided.

    Example output::

        ## Recalled insight provenance
        - [arch.myproject.structure] from this project via docs-mcp
        - [arch.other.pkg.core] from tapps-brain:other-project via tapps-mcp
    """
    if not annotated:
        return ""

    lines: list[str] = ["## Recalled insight provenance"]
    for item in annotated:
        prov = item.get("_provenance", {})
        key = prov.get("key", item.get("key", "unknown"))
        source = prov.get("recalled_from", "local")
        server = prov.get("origin_server", "unknown")
        source_label = "this project" if source == "local" else source
        lines.append(f"- [{key}] from {source_label} via {server}")

    return "\n".join(lines)
