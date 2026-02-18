"""Knowledge ingestion pipeline for project documentation.

Scans project documentation (architecture docs, ADRs, runbooks, etc.)
and ingests them into the knowledge base as domain-tagged markdown files.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

if TYPE_CHECKING:
    from pathlib import Path
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class IngestionResult(BaseModel):
    """Result of a knowledge ingestion run."""

    source_type: str = Field(description="Type of sources ingested.")
    entries_ingested: int = Field(default=0, ge=0, description="Successful entries.")
    entries_failed: int = Field(default=0, ge=0, description="Failed entries.")
    errors: list[str] = Field(default_factory=list, description="Error messages.")


class KnowledgeEntry(BaseModel):
    """A single knowledge entry to be ingested."""

    title: str = Field(description="Entry title.")
    content: str = Field(description="Markdown content.")
    domain: str = Field(description="Target domain.")
    source: str = Field(description="Source file path or identifier.")
    source_type: str = Field(description="Source type (e.g. architecture, adr).")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata.")


class KnowledgeIngestionPipeline:
    """Ingests project documentation into the knowledge base.

    Scans for architecture docs, ADRs, runbooks, and other documentation
    patterns, then creates knowledge markdown files in domain subdirectories.
    """

    PROJECT_SOURCE_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "architecture": [
            "docs/**/architecture*.md",
            "ARCHITECTURE.md",
            "docs/design/**/*.md",
        ],
        "adr": [
            "docs/adr/**/*.md",
            "docs/decisions/**/*.md",
        ],
        "runbook": [
            "docs/runbook*.md",
            "docs/ops/**/*.md",
        ],
        "requirements": [
            "docs/requirements*.md",
            "docs/specs/**/*.md",
        ],
    }

    DEFAULT_DOMAIN_MAP: ClassVar[dict[str, list[str]]] = {
        "architecture": ["general", "api-design"],
        "adr": ["general"],
        "runbook": ["devops", "monitoring"],
        "requirements": ["general"],
    }

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def ingest_project_sources(self) -> IngestionResult:
        """Scan project for documentation and ingest into knowledge base."""
        entries: list[KnowledgeEntry] = []
        errors: list[str] = []

        for source_type, patterns in self.PROJECT_SOURCE_PATTERNS.items():
            domains = self.DEFAULT_DOMAIN_MAP.get(source_type, ["general"])
            try:
                found = self._ingest_source_type(source_type, patterns, domains)
                entries.extend(found)
            except Exception as exc:
                errors.append(f"{source_type}: {exc}")

        # Store entries.
        stored = 0
        for entry in entries:
            try:
                self._store_knowledge_entry(entry)
                stored += 1
            except Exception as exc:
                errors.append(f"store {entry.title}: {exc}")

        return IngestionResult(
            source_type="project",
            entries_ingested=stored,
            entries_failed=len(entries) - stored,
            errors=errors,
        )

    def _ingest_source_type(
        self,
        source_type: str,
        patterns: list[str],
        domains: list[str],
    ) -> list[KnowledgeEntry]:
        """Find and parse files matching *patterns*."""
        entries: list[KnowledgeEntry] = []

        for pattern in patterns:
            for file_path in self._project_root.glob(pattern):
                if not file_path.is_file():
                    continue
                try:
                    parsed = self._parse_source_file(file_path, source_type, domains)
                    entries.extend(parsed)
                except (OSError, UnicodeDecodeError, ValueError) as e:
                    logger.debug(
                        "ingestion_parse_failed",
                        file=str(file_path),
                        error=str(e),
                    )

        return entries

    def _parse_source_file(
        self,
        file_path: Path,
        source_type: str,
        domains: list[str],
    ) -> list[KnowledgeEntry]:
        """Parse a single source file into knowledge entries."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            return []

        if not content.strip():
            return []

        title = self._extract_title(file_path, content)
        domain = domains[0] if domains else "general"

        return [
            KnowledgeEntry(
                title=title,
                content=content,
                domain=domain,
                source=str(file_path),
                source_type=source_type,
                metadata={"original_path": str(file_path.relative_to(self._project_root))},
            )
        ]

    @staticmethod
    def _extract_title(file_path: Path, content: str) -> str:
        """Extract title from markdown H1 header, or fall back to filename."""
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("##"):
                return stripped[2:].strip()
        return file_path.stem.replace("-", " ").replace("_", " ").title()

    def _store_knowledge_entry(self, entry: KnowledgeEntry) -> None:
        """Write a knowledge entry as a markdown file."""
        domain_dir = self._project_root / ".tapps-mcp" / "knowledge" / entry.domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        # Sanitise filename.
        safe_name = re.sub(r"[^\w\s-]", "", entry.title.lower())
        safe_name = re.sub(r"[\s]+", "-", safe_name.strip())
        if not safe_name:
            safe_name = "untitled"

        target = domain_dir / f"{safe_name}.md"

        # Write with source attribution header.
        header = (
            f"---\n"
            f"source: {entry.source}\n"
            f"source_type: {entry.source_type}\n"
            f"domain: {entry.domain}\n"
            f"---\n\n"
        )
        target.write_text(header + entry.content, encoding="utf-8")
        logger.debug("knowledge_entry_stored", title=entry.title, path=str(target))
