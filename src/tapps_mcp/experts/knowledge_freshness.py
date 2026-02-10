"""Knowledge file freshness tracking.

Tracks metadata about knowledge files (last updated, deprecation status)
and identifies stale files that may need review.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# Default staleness threshold.
_DEFAULT_MAX_AGE_DAYS = 365


class KnowledgeFileMetadata(BaseModel):
    """Metadata for a single knowledge file."""

    file_path: str = Field(description="Relative path to the knowledge file.")
    last_updated: str = Field(description="ISO-8601 UTC timestamp of last update.")
    version: str | None = Field(default=None, description="Version tag.")
    deprecated: bool = Field(default=False, description="Whether the file is deprecated.")
    deprecation_date: str | None = Field(default=None, description="ISO-8601 deprecation date.")
    replacement_file: str | None = Field(default=None, description="Path to replacement file.")
    author: str | None = Field(default=None, description="Author of the file.")
    tags: list[str] = Field(default_factory=list, description="Tags for categorisation.")
    description: str | None = Field(default=None, description="Short description.")


class KnowledgeFreshnessTracker:
    """Tracks knowledge file metadata and detects staleness.

    Metadata is persisted to a JSON file using atomic writes.
    """

    def __init__(self, metadata_file: Path | None = None) -> None:
        self._metadata_file = metadata_file or Path(".tapps-mcp") / "knowledge_metadata.json"
        self._metadata: dict[str, KnowledgeFileMetadata] = {}
        self._load_metadata()

    def update_file_metadata(
        self,
        file_path: Path,
        *,
        version: str | None = None,
        author: str | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
    ) -> None:
        """Update or create metadata for *file_path*."""
        key = str(file_path)
        now = datetime.now(tz=UTC).isoformat()

        existing = self._metadata.get(key)
        self._metadata[key] = KnowledgeFileMetadata(
            file_path=key,
            last_updated=now,
            version=version or (existing.version if existing else None),
            deprecated=existing.deprecated if existing else False,
            author=author or (existing.author if existing else None),
            tags=tags if tags is not None else (existing.tags if existing else []),
            description=description or (existing.description if existing else None),
        )
        self._save_metadata()

    def mark_deprecated(
        self,
        file_path: Path,
        *,
        replacement_file: str | None = None,
        deprecation_date: str | None = None,
    ) -> None:
        """Mark *file_path* as deprecated."""
        key = str(file_path)
        now = datetime.now(tz=UTC).isoformat()

        existing = self._metadata.get(key)
        if existing is None:
            existing = KnowledgeFileMetadata(file_path=key, last_updated=now)

        self._metadata[key] = KnowledgeFileMetadata(
            file_path=key,
            last_updated=existing.last_updated,
            version=existing.version,
            deprecated=True,
            deprecation_date=deprecation_date or now,
            replacement_file=replacement_file,
            author=existing.author,
            tags=existing.tags,
            description=existing.description,
        )
        self._save_metadata()

    def get_file_metadata(self, file_path: Path) -> KnowledgeFileMetadata | None:
        """Return metadata for *file_path*, or ``None`` if not tracked."""
        return self._metadata.get(str(file_path))

    def get_stale_files(
        self,
        knowledge_dir: Path,
        max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    ) -> list[tuple[Path, KnowledgeFileMetadata]]:
        """Return files older than *max_age_days*."""
        if not knowledge_dir.exists():
            return []

        cutoff = datetime.now(tz=UTC) - timedelta(days=max_age_days)
        stale: list[tuple[Path, KnowledgeFileMetadata]] = []

        for md_file in knowledge_dir.rglob("*.md"):
            key = str(md_file)
            meta = self._metadata.get(key)
            if meta is None:
                # Untracked file — use filesystem mtime.
                try:
                    mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        stale.append(
                            (
                                md_file,
                                KnowledgeFileMetadata(
                                    file_path=key,
                                    last_updated=mtime.isoformat(),
                                ),
                            )
                        )
                except OSError:
                    pass
            else:
                try:
                    last = datetime.fromisoformat(meta.last_updated)
                    if last < cutoff:
                        stale.append((md_file, meta))
                except (ValueError, TypeError):
                    pass

        return stale

    def get_deprecated_files(
        self,
        knowledge_dir: Path,
    ) -> list[tuple[Path, KnowledgeFileMetadata]]:
        """Return all deprecated files within *knowledge_dir*."""
        result: list[tuple[Path, KnowledgeFileMetadata]] = []
        for key, meta in self._metadata.items():
            if meta.deprecated:
                p = Path(key)
                if str(p).startswith(str(knowledge_dir)) or not knowledge_dir.exists():
                    result.append((p, meta))
        return result

    def scan_and_update(self, knowledge_dir: Path) -> dict[str, Any]:
        """Scan *knowledge_dir* and update metadata for any new files."""
        if not knowledge_dir.exists():
            return {"scanned": 0, "new": 0, "updated": 0}

        scanned = 0
        new_count = 0
        updated = 0

        for md_file in knowledge_dir.rglob("*.md"):
            scanned += 1
            key = str(md_file)
            if key not in self._metadata:
                now = datetime.now(tz=UTC).isoformat()
                self._metadata[key] = KnowledgeFileMetadata(
                    file_path=key,
                    last_updated=now,
                )
                new_count += 1

        if new_count > 0:
            self._save_metadata()
            updated = new_count

        return {"scanned": scanned, "new": new_count, "updated": updated}

    def get_summary(self, knowledge_dir: Path) -> dict[str, Any]:
        """Return a summary of knowledge file freshness."""
        total_files = sum(1 for _ in knowledge_dir.rglob("*.md")) if knowledge_dir.exists() else 0
        tracked = sum(
            1 for k in self._metadata if str(knowledge_dir) in k or not knowledge_dir.exists()
        )
        deprecated = sum(1 for m in self._metadata.values() if m.deprecated)
        stale = len(self.get_stale_files(knowledge_dir))

        return {
            "total_files": total_files,
            "tracked_files": tracked,
            "deprecated_files": deprecated,
            "stale_files": stale,
            "coverage": round(tracked / total_files, 2) if total_files > 0 else 0.0,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_metadata(self) -> None:
        """Load metadata from the JSON file."""
        if not self._metadata_file.exists():
            return

        try:
            raw = json.loads(self._metadata_file.read_text(encoding="utf-8"))
            for key, data in raw.items():
                self._metadata[key] = KnowledgeFileMetadata.model_validate(data)
        except (json.JSONDecodeError, OSError):
            logger.warning("knowledge_metadata_load_failed", exc_info=True)

    def _save_metadata(self) -> None:
        """Persist metadata atomically."""
        self._metadata_file.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.model_dump() for k, v in self._metadata.items()}

        fd, tmp_path = tempfile.mkstemp(dir=str(self._metadata_file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            Path(tmp_path).replace(self._metadata_file)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()
            raise
