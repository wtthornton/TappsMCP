"""Brain-memory coverage manifest for the audit-campaign tool.

Two record types are stored via :class:`BrainBridge`:

- Per-file coverage records at key ``audit.coverage.<encoded_path>`` — tier
  ``pattern`` (60d) — what was audited, when, and what was found.
  Paths are encoded for tapps-brain slug rules (``[a-z0-9][a-z0-9._-]{0,127}``):
  lowercase, ``/`` → ``--`` between segments, ``.`` → ``_d`` (and escapes for
  literal ``_d`` / ``--`` within a segment). Use :func:`coverage_key` /
  :func:`rel_path_from_coverage_key` — never hand-build keys.
- Campaign spec records at key ``audit.campaign.<campaign_id>`` — tier
  ``procedural`` (30d) — the planning output so dispatch can pick up
  where plan left off.
- Fix-plan specs at key ``fix.campaign.<campaign_id>`` (TAP-2718).

Reads return ``None`` for missing keys; writes return ``False`` when the
bridge is unavailable or the brain rejects the save (degraded mode — caller
decides whether to fall back or surface the degradation).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Matches tapps-brain MemoryEntry key validation (models._KEY_SLUG_PATTERN).
_BRAIN_KEY_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_MAX_BRAIN_KEY_LEN = 128

_COVERAGE_KEY_PREFIX = "audit.coverage."
_CAMPAIGN_KEY_PREFIX = "audit.campaign."
_FIX_CAMPAIGN_KEY_PREFIX = "fix.campaign."
_COVERAGE_TIER = "pattern"
_CAMPAIGN_TIER = "procedural"
_SOURCE_AGENT = "tapps-audit-campaign"


@dataclass
class FindingCounts:
    """Bucket counts for a session's findings."""

    p0: int = 0
    p1: int = 0
    p2: int = 0
    p3: int = 0


@dataclass
class CoverageEntry:
    """Per-file audit coverage record."""

    rel_path: str
    audited_sha: str
    audited_at: str  # ISO-8601 UTC
    session_ticket: str
    campaign_id: str
    findings: FindingCounts = field(default_factory=FindingCounts)
    finding_tickets: list[str] = field(default_factory=list)
    fix_tickets: list[str] = field(default_factory=list)
    # The sha a fix landed at (TAP-2799). Recorded by close_coverage for
    # traceability — distinct from audited_sha, which only ever reflects a
    # sha that was actually AUDITED (a fix is not an audit).
    fix_sha: str = ""


# Path segments are joined with ``--`` (valid in brain slugs). Within a segment,
# ``.`` → ``_d``, literal ``_d`` → ``__d__``, literal ``--`` → ``__dash__``.
_SEGMENT_SEP = "--"


def _encode_path_segment(segment: str) -> str:
    """Encode one path segment for use inside a brain slug key."""
    return segment.replace("--", "__dash__").replace("_d", "__d__").replace(".", "_d")


def _decode_path_segment(encoded: str) -> str:
    """Decode one path segment from a brain slug key suffix."""
    return encoded.replace("__dash__", "--").replace("__d__", "_d").replace("_d", ".")


def _normalize_rel_path(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/").strip("/")
    if not normalized:
        msg = "rel_path must not be empty"
        raise ValueError(msg)
    return normalized.lower()


def _assert_brain_slug(key: str) -> None:
    if len(key) > _MAX_BRAIN_KEY_LEN or not _BRAIN_KEY_SLUG_RE.match(key):
        msg = f"brain key is not a valid slug ({len(key)} chars): {key!r}"
        raise ValueError(msg)


def coverage_key(rel_path: str) -> str:
    """Return the brain slug key for a repo-relative file path."""
    normalized = _normalize_rel_path(rel_path)
    encoded = _SEGMENT_SEP.join(_encode_path_segment(part) for part in normalized.split("/"))
    key = f"{_COVERAGE_KEY_PREFIX}{encoded}"
    _assert_brain_slug(key)
    return key


def rel_path_from_coverage_key(key: str) -> str | None:
    """Decode a coverage brain key back to a repo-relative path, or ``None``."""
    if not key.startswith(_COVERAGE_KEY_PREFIX):
        return None
    suffix = key[len(_COVERAGE_KEY_PREFIX) :]
    if not suffix:
        return None
    return "/".join(_decode_path_segment(part) for part in suffix.split(_SEGMENT_SEP))


def campaign_key(campaign_id: str) -> str:
    """Return the brain slug key for an audit campaign spec."""
    if not campaign_id:
        msg = "campaign_id must not be empty"
        raise ValueError(msg)
    key = f"{_CAMPAIGN_KEY_PREFIX}{campaign_id.lower()}"
    _assert_brain_slug(key)
    return key


def fix_campaign_key(campaign_id: str) -> str:
    """Brain key for a fix-plan spec — distinct from the audit campaign key."""
    if not campaign_id:
        msg = "campaign_id must not be empty"
        raise ValueError(msg)
    key = f"{_FIX_CAMPAIGN_KEY_PREFIX}{campaign_id.lower()}"
    _assert_brain_slug(key)
    return key


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def is_fresh(
    entry: CoverageEntry,
    current_sha: str,
    *,
    max_age_days: int = 30,
) -> bool:
    """A coverage entry is fresh iff it matches the current SHA *and* is
    within the freshness window.
    """
    if not entry.audited_sha or entry.audited_sha != current_sha:
        return False
    try:
        audited_at = datetime.fromisoformat(entry.audited_at)
    except ValueError:
        return False
    return datetime.now(tz=UTC) - audited_at <= timedelta(days=max_age_days)


def _bridge_save_ok(result: Any) -> bool:
    """True when :meth:`BrainBridge.save` persisted an entry successfully."""
    if not isinstance(result, dict):
        return False
    if result.get("error"):
        return False
    if result.get("degraded"):
        return False
    if result.get("success") is False:
        return False
    if result.get("status") == "saved":
        return True
    return bool(result.get("key")) and "value" in result


async def _save_via_bridge(
    bridge: Any,
    *,
    key: str,
    value: str,
    tier: str,
    tags: list[str],
    failure_event: str,
    **log_ctx: Any,
) -> bool:
    try:
        result = await bridge.save(
            key=key,
            value=value,
            tier=tier,
            scope="project",
            source="agent",
            source_agent=_SOURCE_AGENT,
            tags=tags,
        )
    except Exception as exc:  # degraded-mode catch-all
        logger.debug(failure_event, key=key, error=str(exc), **log_ctx)
        return False
    if _bridge_save_ok(result):
        return True
    logger.warning(
        f"{failure_event}_rejected",
        key=key,
        error=result.get("error") if isinstance(result, dict) else None,
        message=result.get("message") if isinstance(result, dict) else None,
        **log_ctx,
    )
    return False


async def read_coverage_for(
    rel_paths: list[str],
) -> dict[str, CoverageEntry | None]:
    """Read coverage entries for a batch of relative paths.

    Returns a dict mapping ``rel_path -> CoverageEntry`` for found entries
    and ``None`` for misses. If the brain bridge is unavailable, returns
    all-``None`` and logs a debug-level degraded message.
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        logger.debug("audit_manifest_read_degraded", reason="bridge_unavailable")
        return dict.fromkeys(rel_paths)

    out: dict[str, CoverageEntry | None] = {}
    for rel in rel_paths:
        entry = await _read_coverage_one(bridge, rel)
        out[rel] = entry
    return out


async def write_coverage(entry: CoverageEntry) -> bool:
    """Write a single coverage entry. Returns True on success, False if
    the bridge is unavailable or the write fails for any reason
    (degraded mode — caller decides whether to fall back).
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        logger.debug(
            "audit_manifest_write_degraded",
            reason="bridge_unavailable",
            key=coverage_key(entry.rel_path),
        )
        return False
    payload = json.dumps(_serialize_coverage(entry))
    return await _save_via_bridge(
        bridge,
        key=coverage_key(entry.rel_path),
        value=payload,
        tier=_COVERAGE_TIER,
        tags=["audit", "coverage", entry.campaign_id],
        failure_event="audit_manifest_write_failed",
        rel_path=entry.rel_path,
    )


async def close_coverage(
    rel_path: str,
    new_sha: str,
    *,
    fix_ticket: str = "",
    finding_ticket: str = "",
) -> bool:
    """Update a coverage entry to record a completed fix (TAP-2722, TAP-2799).

    Records *new_sha* — the sha the fix landed at — in ``fix_sha``, and links
    *fix_ticket* (deduped into ``fix_tickets``) and *finding_ticket* (ensured
    in ``finding_tickets``), giving a traceable coverage → finding → fix chain.

    Crucially it does **not** touch ``audited_sha``: a fix is not an audit, so
    the post-fix file content has not been audited. ``audited_sha`` keeps
    pointing at the last sha that was actually audited (the pre-fix sha), so
    :func:`is_fresh` returns ``False`` at the post-fix sha and a subsequent
    campaign re-audits the fixed file (re-audit-as-changed). Setting
    ``audited_sha = new_sha`` here was the TAP-2799 contradiction: it made the
    fixed file read fresh/clean and silently skip re-review.

    Returns ``True`` on success, ``False`` if the bridge is unavailable, the
    entry does not yet exist for *rel_path*, or the write fails (degraded mode).
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        logger.debug(
            "audit_manifest_close_coverage_degraded",
            reason="bridge_unavailable",
            rel_path=rel_path,
        )
        return False
    entries = await read_coverage_for([rel_path])
    entry = entries.get(rel_path)
    if entry is None:
        logger.debug("audit_manifest_close_coverage_missing", rel_path=rel_path)
        return False
    entry.fix_sha = new_sha
    if fix_ticket and fix_ticket not in entry.fix_tickets:
        entry.fix_tickets.append(fix_ticket)
    if finding_ticket and finding_ticket not in entry.finding_tickets:
        entry.finding_tickets.append(finding_ticket)
    return await write_coverage(entry)


async def save_campaign_spec(campaign_id: str, spec_dict: dict[str, Any]) -> bool:
    """Persist a campaign spec for later dispatch lookup.

    Returns True on success, False if the bridge is unavailable or the
    write fails (degraded mode).
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        logger.debug(
            "audit_manifest_save_campaign_degraded",
            reason="bridge_unavailable",
            campaign_id=campaign_id,
        )
        return False
    return await _save_via_bridge(
        bridge,
        key=campaign_key(campaign_id),
        value=json.dumps(spec_dict),
        tier=_CAMPAIGN_TIER,
        tags=["audit", "campaign", campaign_id],
        failure_event="audit_manifest_save_campaign_failed",
        campaign_id=campaign_id,
    )


async def load_campaign_spec(campaign_id: str) -> dict[str, Any] | None:
    """Load a previously-saved campaign spec by id.

    Returns ``None`` for missing keys, bridge unavailability, or any
    failure during the read.
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        return None
    try:
        entry = await bridge.get(campaign_key(campaign_id))
    except Exception as exc:  # degraded-mode catch-all
        logger.debug(
            "audit_manifest_load_campaign_failed",
            campaign_id=campaign_id,
            error=str(exc),
        )
        return None
    if not entry:
        return None
    value = _extract_value(entry)
    if not value:
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        logger.warning(
            "audit_manifest_corrupt_campaign_spec",
            campaign_id=campaign_id,
        )
        return None
    return loaded if isinstance(loaded, dict) else None


async def save_fix_plan_spec(campaign_id: str, spec_dict: dict[str, Any]) -> bool:
    """Persist a fix-plan spec under ``fix.campaign.<campaign_id>``.

    Stored separately from the audit campaign spec (``audit.campaign.<id>``)
    so that audit coverage and fix coverage can be tracked, queried, and
    expired independently (TAP-2718).

    Returns ``True`` on success, ``False`` if the bridge is unavailable or
    the write fails (degraded mode — caller decides whether to fall back).
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        logger.debug(
            "audit_manifest_save_fix_plan_degraded",
            reason="bridge_unavailable",
            campaign_id=campaign_id,
        )
        return False
    return await _save_via_bridge(
        bridge,
        key=fix_campaign_key(campaign_id),
        value=json.dumps(spec_dict),
        tier=_CAMPAIGN_TIER,
        tags=["audit", "fix", "campaign", campaign_id],
        failure_event="audit_manifest_save_fix_plan_failed",
        campaign_id=campaign_id,
    )


async def load_fix_plan_spec(campaign_id: str) -> dict[str, Any] | None:
    """Load a previously-saved fix-plan spec by campaign id.

    Returns ``None`` for missing keys, bridge unavailability, or any
    failure during the read.
    """
    bridge = _get_bridge_or_none()
    if bridge is None:
        return None
    try:
        entry = await bridge.get(fix_campaign_key(campaign_id))
    except Exception as exc:  # degraded-mode catch-all (BLE001 not enabled in ruff)
        logger.debug(
            "audit_manifest_load_fix_plan_failed",
            campaign_id=campaign_id,
            error=str(exc),
        )
        return None
    if not entry:
        return None
    value = _extract_value(entry)
    if not value:
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        logger.warning(
            "audit_manifest_corrupt_fix_plan_spec",
            campaign_id=campaign_id,
        )
        return None
    return loaded if isinstance(loaded, dict) else None


async def _read_coverage_one(bridge: Any, rel: str) -> CoverageEntry | None:
    try:
        entry = await bridge.get(coverage_key(rel))
    except Exception as exc:  # degraded-mode catch-all
        logger.debug(
            "audit_manifest_read_one_failed",
            rel=rel,
            error=str(exc),
        )
        return None
    if not entry:
        return None
    value = _extract_value(entry)
    if not value:
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return _deserialize_coverage(rel, payload)


def _serialize_coverage(entry: CoverageEntry) -> dict[str, Any]:
    data = asdict(entry)
    data.pop("rel_path", None)
    return data


def _deserialize_coverage(rel_path: str, payload: dict[str, Any]) -> CoverageEntry | None:
    try:
        findings_raw = payload.get("findings") or {}
        findings = FindingCounts(
            p0=int(findings_raw.get("p0", 0)),
            p1=int(findings_raw.get("p1", 0)),
            p2=int(findings_raw.get("p2", 0)),
            p3=int(findings_raw.get("p3", 0)),
        )
        return CoverageEntry(
            rel_path=rel_path,
            audited_sha=str(payload.get("audited_sha", "")),
            audited_at=str(payload.get("audited_at", "")),
            session_ticket=str(payload.get("session_ticket", "")),
            campaign_id=str(payload.get("campaign_id", "")),
            findings=findings,
            finding_tickets=list(payload.get("finding_tickets", [])),
            fix_tickets=list(payload.get("fix_tickets", [])),
            fix_sha=str(payload.get("fix_sha", "")),
        )
    except (TypeError, ValueError):
        return None


def _extract_value(entry: Any) -> str:
    """Pull the ``value`` field out of a bridge entry, handling both dict
    and pydantic-model shapes.
    """
    raw = entry.get("value", "") if isinstance(entry, dict) else getattr(entry, "value", "")
    return raw if isinstance(raw, str) else ""


def _get_bridge_or_none() -> Any:
    """Return the cached BrainBridge or ``None`` if unavailable."""
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge
    except ImportError:
        return None
    try:
        return _get_brain_bridge()
    except (RuntimeError, OSError):
        return None
