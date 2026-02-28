"""Import and export for shared memory entries.

Enables teams to share and back up project memories via JSON files.
All file paths are validated through ``security/path_validator.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp import __version__
from tapps_mcp.memory.models import MemoryEntry

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.memory.store import MemoryStore
    from tapps_mcp.security.path_validator import PathValidator

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_IMPORT_ENTRIES = 500


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_memories(
    store: MemoryStore,
    output_path: Path,
    validator: PathValidator,
    *,
    tier: str | None = None,
    scope: str | None = None,
    min_confidence: float | None = None,
) -> dict[str, Any]:
    """Export memories to a JSON file.

    Args:
        store: The memory store to export from.
        output_path: Destination file path.
        validator: Path validator for sandbox enforcement.
        tier: Optional tier filter.
        scope: Optional scope filter.
        min_confidence: Optional minimum confidence filter.

    Returns:
        Summary dict with ``exported_count``, ``file_path``, ``exported_at``.
    """
    validated_path = validator.validate_path(output_path, must_exist=False, max_file_size=None)

    snapshot = store.snapshot()
    entries = snapshot.entries

    # Apply filters
    if tier is not None:
        entries = [e for e in entries if e.tier.value == tier]
    if scope is not None:
        entries = [e for e in entries if e.scope.value == scope]
    if min_confidence is not None:
        entries = [e for e in entries if e.confidence >= min_confidence]

    exported_at = datetime.now(tz=UTC).isoformat()

    payload: dict[str, Any] = {
        "memories": [e.model_dump(mode="json") for e in entries],
        "exported_at": exported_at,
        "source_project": snapshot.project_root,
        "entry_count": len(entries),
        "tapps_version": __version__,
    }

    validated_path.parent.mkdir(parents=True, exist_ok=True)
    validated_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    logger.info(
        "memories_exported",
        count=len(entries),
        path=str(validated_path),
    )

    return {
        "exported_count": len(entries),
        "file_path": str(validated_path),
        "exported_at": exported_at,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _validate_import_payload(data: object) -> list[dict[str, Any]]:
    """Validate the top-level structure of an import JSON payload.

    Returns the list of raw memory dicts.

    Raises:
        ValueError: If the payload is malformed.
    """
    if not isinstance(data, dict):
        msg = "Import file must contain a JSON object."
        raise ValueError(msg)

    memories = data.get("memories")
    if not isinstance(memories, list):
        msg = "Import file must contain a 'memories' list."
        raise ValueError(msg)

    if len(memories) > _MAX_IMPORT_ENTRIES:
        msg = f"Import exceeds max entries ({len(memories)} > {_MAX_IMPORT_ENTRIES})."
        raise ValueError(msg)

    return [m for m in memories if isinstance(m, dict)]


def import_memories(
    store: MemoryStore,
    input_path: Path,
    validator: PathValidator,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Import memories from a JSON file.

    Args:
        store: The memory store to import into.
        input_path: Source JSON file path.
        validator: Path validator for sandbox enforcement.
        overwrite: If True, overwrite existing keys. Default: skip.

    Returns:
        Summary dict with ``imported_count``, ``skipped_count``, ``error_count``.
    """
    validated_path = validator.validate_path(input_path, must_exist=True)

    raw = validated_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    memory_dicts = _validate_import_payload(data)

    imported = 0
    skipped = 0
    errors = 0

    for raw_entry in memory_dicts:
        try:
            entry = MemoryEntry.model_validate(raw_entry)
        except Exception:
            errors += 1
            logger.warning("memory_import_entry_invalid", entry=raw_entry)
            continue

        # Check for existing key
        existing = store.get(entry.key)
        if existing is not None and not overwrite:
            skipped += 1
            continue

        # Mark as imported
        agent_suffix = "(imported)"
        source_agent = entry.source_agent
        if not source_agent.endswith(agent_suffix):
            source_agent = f"{source_agent} {agent_suffix}"

        store.save(
            key=entry.key,
            value=entry.value,
            tier=entry.tier.value,
            source=entry.source.value,
            source_agent=source_agent,
            scope=entry.scope.value,
            tags=entry.tags,
            branch=entry.branch,
            confidence=entry.confidence,
        )
        imported += 1

    logger.info(
        "memories_imported",
        imported=imported,
        skipped=skipped,
        errors=errors,
        path=str(validated_path),
    )

    return {
        "imported_count": imported,
        "skipped_count": skipped,
        "error_count": errors,
        "file_path": str(validated_path),
    }
