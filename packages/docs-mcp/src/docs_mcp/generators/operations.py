"""Operational documentation generators (runbooks, postmortems)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from docs_mcp.generators.writing_principles import append_writing_principles

if TYPE_CHECKING:
    from pathlib import Path

    from docs_mcp.generators.metadata import ProjectMetadata

logger = structlog.get_logger(__name__)


class RunbookGenerator:
    """Generate an operational runbook from structured inputs."""

    def generate(
        self,
        project_root: Path,
        *,
        title: str,
        service: str = "",
        when_to_use: str = "",
        prerequisites: str = "",
        procedure: str = "",
        rollback_steps: str = "",
        escalation: str = "",
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Build a runbook markdown document."""
        try:
            return self._generate_impl(
                project_root,
                title=title,
                service=service,
                when_to_use=when_to_use,
                prerequisites=prerequisites,
                procedure=procedure,
                rollback_steps=rollback_steps,
                escalation=escalation,
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("runbook_generation_failed", reason=str(exc))
            return ""

    def _generate_impl(
        self,
        project_root: Path,
        *,
        title: str,
        service: str,
        when_to_use: str,
        prerequisites: str,
        procedure: str,
        rollback_steps: str,
        escalation: str,
        metadata: ProjectMetadata | None,
    ) -> str:
        from docs_mcp.generators.metadata import MetadataExtractor

        project_root = project_root.resolve()
        if metadata is None:
            metadata = MetadataExtractor().extract(project_root)

        project_name = metadata.name or project_root.name
        runbook_title = title.strip() or f"{project_name} runbook"
        service_name = service.strip() or project_name
        updated = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        lines: list[str] = [
            f"# Runbook: {runbook_title}",
            "",
            f"**Service:** {service_name}  ",
            f"**Last updated:** {updated}",
            "",
            "## When to use this runbook",
            "",
        ]
        lines.extend(
            self._paragraph_or_placeholder(when_to_use, "Describe the symptoms or triggers.")
        )
        lines.extend(["", "## Prerequisites and access", ""])
        lines.extend(
            self._paragraph_or_placeholder(
                prerequisites,
                "List credentials, dashboards, on-call rotation, and required tooling.",
            )
        )
        lines.extend(["", "## Procedure", ""])
        lines.extend(self._procedure_lines(procedure))
        lines.extend(["", "## Rollback", ""])
        lines.extend(
            self._paragraph_or_placeholder(
                rollback_steps,
                "Document how to revert changes safely if the procedure fails.",
            )
        )
        lines.extend(["", "## Escalation", ""])
        lines.extend(
            self._paragraph_or_placeholder(
                escalation,
                "Who to page, severity thresholds, and communication channels.",
            )
        )
        lines.extend(["", "## Related documentation", ""])
        lines.extend(self._related_links(project_root))

        return append_writing_principles("\n".join(lines))

    @staticmethod
    def _paragraph_or_placeholder(text: str, placeholder: str) -> list[str]:
        body = text.strip()
        if body:
            return [body]
        return [f"<!-- {placeholder} -->"]

    @staticmethod
    def _procedure_lines(procedure: str) -> list[str]:
        body = procedure.strip()
        if not body:
            return [
                "1. <!-- Step 1: verify service health -->",
                "2. <!-- Step 2: apply fix -->",
                "3. <!-- Step 3: validate recovery -->",
            ]
        if any(line.strip().startswith(("1.", "- ", "* ", "1)")) for line in body.splitlines()):
            return [body]
        steps = [s.strip() for s in body.split("\n") if s.strip()]
        return [f"{idx}. {step}" for idx, step in enumerate(steps, start=1)]

    @staticmethod
    def _related_links(project_root: Path) -> list[str]:
        links: list[str] = []
        if (project_root / "docs" / "TROUBLESHOOTING.md").exists():
            links.append("- [Troubleshooting](docs/TROUBLESHOOTING.md)")
        if (project_root / "docs" / "operations").is_dir():
            links.append("- [Operations docs](docs/operations/)")
        if (project_root / "README.md").exists():
            links.append("- [README](README.md)")
        if not links:
            links.append("- <!-- Link architecture docs, on-call playbooks, and dashboards -->")
        return links


class PostmortemGenerator:
    """Generate an incident postmortem document."""

    def generate(
        self,
        project_root: Path,
        *,
        title: str,
        incident_date: str = "",
        summary: str = "",
        timeline: str = "",
        impact: str = "",
        root_cause: str = "",
        action_items: str = "",
        metadata: ProjectMetadata | None = None,
    ) -> str:
        """Build a postmortem markdown document."""
        try:
            return self._generate_impl(
                project_root,
                title=title,
                incident_date=incident_date,
                summary=summary,
                timeline=timeline,
                impact=impact,
                root_cause=root_cause,
                action_items=action_items,
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("postmortem_generation_failed", reason=str(exc))
            return ""

    def _generate_impl(
        self,
        project_root: Path,
        *,
        title: str,
        incident_date: str,
        summary: str,
        timeline: str,
        impact: str,
        root_cause: str,
        action_items: str,
        metadata: ProjectMetadata | None,
    ) -> str:
        from docs_mcp.generators.metadata import MetadataExtractor

        project_root = project_root.resolve()
        if metadata is None:
            metadata = MetadataExtractor().extract(project_root)

        project_name = metadata.name or project_root.name
        doc_title = title.strip() or f"{project_name} incident postmortem"
        date_line = incident_date.strip() or datetime.now(tz=UTC).strftime("%Y-%m-%d")

        sections: list[tuple[str, str, str]] = [
            ("Summary", summary, "What happened in 2-3 sentences."),
            ("Impact", impact, "Users affected, duration, SLO breach, revenue risk."),
            ("Timeline", timeline, "UTC timestamps for detection, mitigation, recovery."),
            ("Root cause", root_cause, "Technical and process causes — blameless."),
            ("Action items", action_items, "Owner + due date per follow-up."),
        ]

        lines: list[str] = [
            f"# Postmortem: {doc_title}",
            "",
            f"**Date:** {date_line}  ",
            "**Status:** Draft",
            "",
        ]

        for heading, body, placeholder in sections:
            lines.append(f"## {heading}")
            lines.append("")
            text = body.strip()
            lines.append(text or f"<!-- {placeholder} -->")
            lines.append("")

        lines.extend(["## Lessons learned", "", "<!-- What went well / what to improve -->", ""])

        return append_writing_principles("\n".join(lines))
