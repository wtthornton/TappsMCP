"""Hive promotion safety gate for TappsMCP (TAP-2014).

Provides a mandatory approval workflow before any memory can be promoted to the
shared brain hive. Brain defaults ``agent_scope="private"`` correctly, but a direct
``hive_push`` would still publish to shared memory without this guard.

Workflow
--------
1. Agent calls ``brain_propose_hive_elevation(memory_key, justification)``
   → records an approval-pending proposal; returns ``proposal_id``.
2. Operator (or a second agent) calls
   ``brain_approve_hive_elevation(proposal_id)``
   → marks the proposal approved; records a brain KG event.
3. Any call to ``bridge.hive_propagate(entries, ...)`` checks each entry's key
   against the approval store before propagating — refused if missing or stale.

The approval store is a local JSON file at
``{cache_dir}/hive-elevation-proposals.json``. Approvals expire after 7 days.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

# Approval expiry window: 7 days in seconds.
_APPROVAL_MAX_AGE_SECONDS: int = 7 * 24 * 3600

_PROPOSALS_FILENAME = "hive-elevation-proposals.json"


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


def _now_ts() -> float:
    """Return the current UTC timestamp as a Unix float."""
    return time.time()


class HiveElevationStore:
    """File-backed approval store for hive elevation proposals.

    Thread-safety: all public methods are synchronous and designed to be
    called from a single asyncio thread (the MCP server event loop). Concurrent
    access from separate processes is not supported; last-write-wins applies for
    the rare edge case of two simultaneous approvals.

    Args:
        store_path: Absolute path to the JSON proposals file.
            The parent directory must exist; the file is created on first write.
    """

    def __init__(self, store_path: Path) -> None:
        self._path = store_path

    # -------------------------------------------------------------------------
    # Internal I/O
    # -------------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Load the proposals dict from disk; return {} on missing/corrupt file."""
        if not self._path.exists():
            return {}
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            _logger.warning("hive_elevation_store.load_failed", path=str(self._path))
            return {}

    def _save(self, proposals: dict[str, Any]) -> None:
        """Write the proposals dict to disk (atomic-ish via write-then-rename)."""
        import contextlib

        tmp = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(proposals, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            _logger.warning(
                "hive_elevation_store.save_failed",
                path=str(self._path),
                error=str(exc),
            )
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def propose(self, memory_key: str, justification: str) -> str:
        """Record a new elevation proposal and return its ``proposal_id``.

        The proposal is written to the local store and must be approved via
        :meth:`approve` before the matching key can be propagated via
        ``bridge.hive_propagate``.

        Args:
            memory_key: The brain memory key being proposed for hive elevation.
            justification: Human-readable rationale for the elevation request.

        Returns:
            ``proposal_id`` — a short deterministic hex string derived from
            ``memory_key`` + proposal timestamp.
        """
        ts = _now_iso()
        raw = f"{memory_key}:{ts}".encode()
        proposal_id = hashlib.sha256(raw).hexdigest()[:16]

        proposals = self._load()
        proposals[proposal_id] = {
            "memory_key": memory_key,
            "justification": justification,
            "proposed_at": ts,
            "proposed_at_ts": _now_ts(),
            "status": "pending",
        }
        self._save(proposals)

        _logger.info(
            "hive_elevation.proposed",
            proposal_id=proposal_id,
            memory_key=memory_key,
        )
        return proposal_id

    def approve(self, proposal_id: str) -> dict[str, Any]:
        """Mark an existing proposal as approved.

        Args:
            proposal_id: The ID returned by :meth:`propose`.

        Returns:
            Dict with ``approved``, ``proposal_id``, and ``memory_key`` fields.
            On error, returns ``{"approved": False, "error": "<reason>"}``.
        """
        proposals = self._load()
        if proposal_id not in proposals:
            return {
                "approved": False,
                "proposal_id": proposal_id,
                "error": "proposal_not_found",
            }

        entry = proposals[proposal_id]
        if entry.get("status") == "approved":
            return {
                "approved": True,
                "proposal_id": proposal_id,
                "memory_key": entry["memory_key"],
                "already_approved": True,
            }

        entry["status"] = "approved"
        entry["approved_at"] = _now_iso()
        entry["approved_at_ts"] = _now_ts()
        proposals[proposal_id] = entry
        self._save(proposals)

        _logger.info(
            "hive_elevation.approved",
            proposal_id=proposal_id,
            memory_key=entry["memory_key"],
        )
        return {
            "approved": True,
            "proposal_id": proposal_id,
            "memory_key": entry["memory_key"],
        }

    def check_approved(self, memory_key: str) -> bool:
        """Return True if ``memory_key`` has a valid (non-expired) approval.

        This is the callable injected into
        :attr:`~tapps_core.brain_bridge.BrainBridge.elevation_guard`.

        Args:
            memory_key: The brain memory key to check.

        Returns:
            ``True`` when an approved proposal for the key exists and was
            approved within the last 7 days.  ``False`` otherwise.
        """
        proposals = self._load()
        cutoff_ts = _now_ts() - _APPROVAL_MAX_AGE_SECONDS

        for entry in proposals.values():
            if entry.get("memory_key") != memory_key:
                continue
            if entry.get("status") != "approved":
                continue
            approved_at_ts: float = float(entry.get("approved_at_ts", 0))
            if approved_at_ts >= cutoff_ts:
                return True

        return False

    def list_proposals(self) -> list[dict[str, Any]]:
        """Return all proposals (for diagnostics / MCP tool output)."""
        proposals = self._load()
        result: list[dict[str, Any]] = []
        cutoff_ts = _now_ts() - _APPROVAL_MAX_AGE_SECONDS
        for pid, entry in proposals.items():
            row: dict[str, Any] = {
                "proposal_id": pid,
                **entry,
            }
            if entry.get("status") == "approved":
                approved_at_ts = float(entry.get("approved_at_ts", 0))
                row["expired"] = approved_at_ts < cutoff_ts
            else:
                row["expired"] = False
            result.append(row)
        return result


# ---------------------------------------------------------------------------
# Module-level singleton factory (used by server_helpers to wire bridge guard)
# ---------------------------------------------------------------------------

_store: HiveElevationStore | None = None


def get_elevation_store(cache_dir: Path) -> HiveElevationStore:
    """Return (or create) the module-level :class:`HiveElevationStore` singleton.

    Args:
        cache_dir: The project's ``.tapps-mcp-cache`` directory path.

    Returns:
        A :class:`HiveElevationStore` backed by
        ``{cache_dir}/hive-elevation-proposals.json``.
    """
    global _store
    if _store is None:
        _store = HiveElevationStore(cache_dir / _PROPOSALS_FILENAME)
    return _store


def reset_elevation_store() -> None:
    """Reset the singleton (for testing)."""
    global _store
    _store = None
