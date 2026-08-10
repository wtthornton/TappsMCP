""".tapps-mcp.yaml writers used during bootstrap.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733).

Every writer here edits a consumer's own config file, so each one goes
through :func:`~tapps_mcp.common.yaml_edit.update_yaml_preserving_comments`
rather than ``yaml.safe_load`` → mutate → ``yaml.dump``.  The round-trip
form rewrites the whole document and silently deletes every comment in it,
which is where a project records *why* a setting is what it is.  Only the
top-level keys these functions actually change are re-rendered; the rest of
the file is left byte-for-byte intact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tapps_mcp.common.yaml_edit import update_yaml_preserving_comments

if TYPE_CHECKING:
    from pathlib import Path


def _read_config(yaml_path: Path, *, encoding: str = "utf-8-sig") -> tuple[str, dict[str, Any]]:
    """Return the raw text of *yaml_path* and its parsed mapping.

    Raises whatever ``yaml`` raises on a malformed document; callers decide
    whether that is fatal.  A missing file reads as an empty document.
    """
    import yaml

    if not yaml_path.exists():
        return "", {}
    raw = yaml_path.read_text(encoding=encoding)
    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        parsed = {}
    return raw, parsed


def _write_config(yaml_path: Path, raw: str, updates: dict[str, Any]) -> None:
    """Apply *updates* to *raw* and write the result, preserving comments."""
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(update_yaml_preserving_comments(raw, updates), encoding="utf-8")


def _memory_hooks_defaults_for_engagement(engagement_level: str) -> dict[str, Any]:
    """Return memory_hooks section defaults by engagement (Epic 65.6).

    high: both auto_recall and auto_capture enabled
    medium: auto_recall only
    low: both disabled
    """
    if engagement_level == "high":
        return {
            "auto_recall": {"enabled": True, "max_results": 5, "min_score": 0.3},
            "auto_capture": {"enabled": True, "max_facts": 5},
        }
    if engagement_level == "medium":
        return {
            "auto_recall": {"enabled": True, "max_results": 5, "min_score": 0.3},
            "auto_capture": {"enabled": False, "max_facts": 5},
        }
    return {
        "auto_recall": {"enabled": False, "max_results": 5, "min_score": 0.3},
        "auto_capture": {"enabled": False, "max_facts": 5},
    }


def _ensure_memory_hooks_config(
    project_root: Path,
    engagement_level: str,
    *,
    dry_run: bool = False,
    warnings: list[str] | None = None,
) -> str:
    """Merge memory_hooks section into .tapps-mcp.yaml with engagement defaults (Epic 65.6).

    Adds or updates memory_hooks only; other keys and all comments preserved.
    Returns 'created', 'updated', or 'skipped'.
    """
    yaml_path = project_root / ".tapps-mcp.yaml"
    defaults = _memory_hooks_defaults_for_engagement(engagement_level)

    if dry_run:
        return "skipped"

    try:
        raw, existing = _read_config(yaml_path)
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"Could not parse .tapps-mcp.yaml for memory_hooks wiring: {exc}")
        return "skipped"

    if "memory_hooks" not in existing:
        _write_config(yaml_path, raw, {"memory_hooks": defaults})
        return "created"

    mh = existing["memory_hooks"]
    if not isinstance(mh, dict):
        mh = {}
    updated = False
    for key in ("auto_recall", "auto_capture"):
        sub_defaults = defaults.get(key, {})
        if not isinstance(sub_defaults, dict):
            continue
        sub = mh.get(key)
        if not isinstance(sub, dict):
            mh[key] = sub_defaults.copy()
            updated = True
        else:
            for k, v in sub_defaults.items():
                if k not in sub:
                    sub[k] = v
                    updated = True
    if updated:
        _write_config(yaml_path, raw, {"memory_hooks": mh})
        return "updated"
    return "skipped"


def _ensure_cursor_stop_completion_gate_config(
    project_root: Path,
    *,
    dry_run: bool = False,
    warnings: list[str] | None = None,
) -> str:
    """Merge ``cursor_stop_completion_gate: warn`` into ``.tapps-mcp.yaml`` (TAP-3921).

    Adds the key when missing and migrates legacy ``block`` to ``warn``.
    Returns ``created``, ``updated``, or ``skipped``.
    """
    yaml_path = project_root / ".tapps-mcp.yaml"
    if dry_run:
        return "skipped"

    try:
        raw, existing = _read_config(yaml_path)
    except Exception as exc:
        if warnings is not None:
            warnings.append(
                f"Could not parse .tapps-mcp.yaml for cursor_stop_completion_gate: {exc}"
            )
        return "skipped"

    current = existing.get("cursor_stop_completion_gate")
    if current is None:
        _write_config(yaml_path, raw, {"cursor_stop_completion_gate": "warn"})
        return "created"
    if current == "block":
        _write_config(yaml_path, raw, {"cursor_stop_completion_gate": "warn"})
        return "updated"
    return "skipped"


def _persist_skill_tier(project_root: Path, skill_tier: str, *, dry_run: bool = False) -> None:
    """Merge ``skill_tier`` into ``.tapps-mcp.yaml``."""
    if dry_run or skill_tier not in {"core", "full"}:
        return

    yaml_path = project_root / ".tapps-mcp.yaml"
    try:
        raw, _existing = _read_config(yaml_path, encoding="utf-8")
    except Exception:
        # A malformed document still gets the key applied by text surgery;
        # rewriting it from a parsed {} would delete the user's whole file.
        raw = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""

    _write_config(yaml_path, raw, {"skill_tier": skill_tier})
