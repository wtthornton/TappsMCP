"""Bounded recurrence tracking for ``tapps_quick_check`` gate failures (Epic M4.2).

When ``memory.track_recurring_quick_check`` is enabled, consecutive failures on the same
resolved path and gate category trigger a procedural memory save (or reinforce if the
key already exists).
"""

# ruff: noqa: TC001, TC003 — runtime Path/settings/GateFailure used in hot path; not TYPE_CHECKING-only.

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

from tapps_core.config.settings import TappsMCPSettings
from tapps_mcp.gates.models import GateFailure

_MAX_STATE_KEYS = 4096
_recurring_lock = threading.Lock()
# (path_fingerprint, sanitized_category) -> consecutive failure count
_recurring_state: OrderedDict[tuple[str, str], int] = OrderedDict()


def _reset_recurring_quick_check_state() -> None:
    """Clear recurrence counters (for tests and process hygiene)."""
    with _recurring_lock:
        _recurring_state.clear()


def _path_fingerprint(resolved: Path, project_root: Path) -> str:
    """Stable short id for *resolved* within the project (or absolute fallback)."""
    try:
        basis = resolved.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        basis = resolved.resolve().as_posix()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _sanitize_category(category: str) -> str:
    c = (category or "unknown").strip().lower() or "unknown"
    return re.sub(r"[^a-z0-9._-]+", "-", c).strip("-")[:48] or "unknown"


def _recurring_memory_key(path_fp: str, category: str) -> str:
    return f"recurring-qc-{path_fp}-{_sanitize_category(category)}"


def _persist_recurring_procedural(  # noqa: PLR0911
    settings: TappsMCPSettings,
    *,
    key: str,
    file_path: str,
    category: str,
    gate_message: str,
) -> tuple[Literal["saved", "reinforced"] | None, str | None]:
    """Save or reinforce procedural memory; returns (action, error_hint). Never raises."""
    value = (
        f"File repeatedly failed tapps_quick_check on gate category '{category}'.\n"
        f"Path: {file_path}\n"
        f"Last failure: {gate_message[:500]}"
    )
    wr = settings.memory.write_rules
    if len(value) > wr.max_value_length:
        value = f"{value[: wr.max_value_length - 3]}..."
    if wr.enforced:
        if len(value) < wr.min_value_length:
            return None, "write_rules_length"
        lowered_v = value.lower()
        lowered_k = key.lower()
        for kw in wr.block_sensitive_keywords:
            klow = kw.lower()
            if klow in lowered_v or klow in lowered_k:
                return None, "write_rules_keyword"

    try:
        from tapps_brain.safety import check_content_safety

        safety_result = check_content_safety(value)
        if not safety_result.safe and settings.memory.safety.enforcement == "block":
            return None, "safety_blocked"
    except ImportError:
        pass

    tags = ["recurring-quick-check", "auto-captured", f"qc-{_sanitize_category(category)}"]
    try:
        from tapps_mcp.server_helpers import _get_memory_store

        store = _get_memory_store()
        existing = store.get(key)
        if existing is not None:
            store.reinforce(key, confidence_boost=0.1)
            return "reinforced", None
        save_res = store.save(
            key=key,
            value=value,
            tier="procedural",
            source="agent",
            source_agent="tapps-mcp",
            scope="project",
            tags=tags,
            confidence=-1.0,
        )
        if isinstance(save_res, dict) and save_res.get("error"):
            return None, str(save_res.get("message", "save_rejected"))[:200]
        return "saved", None
    except Exception as exc:
        import structlog

        structlog.get_logger(__name__).warning(
            "recurring_quick_check_memory_failed", key=key, error=str(exc)[:200], exc_info=True
        )
        return None, str(exc)[:200]


def _clear_path_entries(path_fp: str) -> None:
    stale = [k for k in _recurring_state if k[0] == path_fp]
    for k in stale:
        del _recurring_state[k]


def record_quick_check_recurring(
    settings: TappsMCPSettings,
    resolved: Path,
    gate_passed: bool,
    failures: list[GateFailure],
) -> dict[str, Any]:
    """Update bounded state and optionally write procedural memories.

    Returns a dict with optional ``recurring_quality_memory_events`` for merging into
    ``tapps_quick_check`` payloads.
    """
    mem = settings.memory
    if getattr(mem, "track_recurring_quick_check", False) is not True:
        return {}
    if getattr(mem, "enabled", True) is False:
        return {}

    path_fp = _path_fingerprint(resolved, settings.project_root)
    th_raw = getattr(mem, "recurring_quick_check_threshold", 3)
    threshold = th_raw if isinstance(th_raw, int) else 3
    threshold = max(2, min(50, threshold))
    events: list[dict[str, str]] = []

    with _recurring_lock:
        if gate_passed:
            _clear_path_entries(path_fp)
            return {}

        if not failures:
            return {}

        path_display = str(resolved)

        for failure in failures:
            cat = _sanitize_category(failure.category)
            st_key = (path_fp, cat)
            count = _recurring_state.pop(st_key, 0) + 1
            if count >= threshold:
                mem_key = _recurring_memory_key(path_fp, failure.category)
                action, err = _persist_recurring_procedural(
                    settings,
                    key=mem_key,
                    file_path=path_display,
                    category=failure.category,
                    gate_message=failure.message,
                )
                if action is not None:
                    events.append({"key": mem_key, "action": action})
                elif err:
                    events.append({"key": mem_key, "action": "skipped", "reason": err})
                count = 0

            if count > 0:
                _recurring_state[st_key] = count
                _recurring_state.move_to_end(st_key)
                while len(_recurring_state) > _MAX_STATE_KEYS:
                    _recurring_state.popitem(last=False)

    if not events:
        return {}
    return {"recurring_quality_memory_events": events}
