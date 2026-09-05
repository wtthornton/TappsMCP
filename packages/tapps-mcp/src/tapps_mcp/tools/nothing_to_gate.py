"""The "nothing to gate" terminal state (TAP-6606).

A session that changed only non-scorable files (markdown, prompts, docs) has
no file-scoped tool target. Before this module, ``tapps_validate_changed``
computed the right verdict — *there was nothing to gate* — and then threw it
away: ``tapps_checklist`` re-derived its required tools from ``task_type``
alone and demanded ``tapps_security_scan`` against a file the session never
touched.

This module carries that verdict forward as a first-class state:

* :func:`census` classifies the session's changed files into scorable and
  non-scorable.
* :func:`record` persists the verdict to ``.tapps-mcp/.nothing-to-gate.json``
  so later steps (checklist, stop hook) can read what ``validate_changed``
  actually concluded.
* :func:`clear` removes the marker the moment a real batch is gated, so the
  state can never go stale into a session that *does* have scorable changes.
* :func:`resolve` is the read side, and it is deliberately paranoid: it
  returns a verdict only when the recorded marker is fresh **and** a
  re-derived git census still shows zero changed scorable files. A stale
  marker alone can never make the gate permissive.

The distinction this module exists to preserve, in the emitted wording:

* ``"nothing needed validating"`` — validation ran and found no scorable
  surface. Honest completion.
* ``"No quality validation was run"`` — scorable files changed and nothing
  checked them. Still a block.
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

#: Sidecar carrying the recorded nothing-to-gate verdict, relative to the
#: project root. Read by ``tapps_checklist`` and by the generated stop hook.
NOTHING_TO_GATE_MARKER = ".tapps-mcp/.nothing-to-gate.json"

#: How long a recorded verdict stays usable. Matches the stop hook's own
#: staleness window so the two agree on what "this session" means.
MARKER_MAX_AGE_S = 3600.0

#: Required tools that can only be satisfied by pointing them at a scorable
#: file. When there is no such file in the changeset, demanding these is
#: demanding a scan of something the session never touched.
FILE_SCOPED_TOOLS: frozenset[str] = frozenset(
    {
        "tapps_score_file",
        "tapps_security_scan",
        "tapps_quality_gate",
        "tapps_quick_check",
        "tapps_dead_code",
        "tapps_impact_analysis",
        "tapps_call_graph",
        "tapps_diff_impact",
    }
)


@dataclass(frozen=True)
class ChangedFileCensus:
    """Split of a session's changed files by scorability."""

    scorable: tuple[str, ...]
    non_scorable: tuple[str, ...]

    @property
    def changed_files(self) -> int:
        return len(self.scorable) + len(self.non_scorable)

    @property
    def nothing_to_gate(self) -> bool:
        """True when nothing in the changeset can be scored."""
        return not self.scorable


@dataclass(frozen=True)
class NothingToGate:
    """A recorded, re-verified nothing-to-gate verdict."""

    reason: str
    changed_files: int
    non_scorable: tuple[str, ...]
    recorded_at: float


def _is_scorable(path: str) -> bool:
    from tapps_mcp.server_helpers import _is_scorable_file

    return bool(_is_scorable_file(path))


def census(
    project_root: Path,
    *,
    file_paths: str = "",
    base_ref: str = "HEAD",
) -> ChangedFileCensus:
    """Classify the session's changed files into scorable / non-scorable.

    *file_paths* is the raw comma-separated ``file_paths=`` argument. When the
    caller supplied one, that list is the changeset — they told us what the
    session touched. Otherwise fall back to the same git detection
    ``validate_changed`` uses for auto-detect.
    """
    names = [p.strip() for p in file_paths.split(",") if p.strip()]
    if not names:
        names = _git_changed_names(project_root, base_ref)
    scorable = tuple(sorted({n for n in names if _is_scorable(n)}))
    non_scorable = tuple(sorted({n for n in names if not _is_scorable(n)}))
    return ChangedFileCensus(scorable=scorable, non_scorable=non_scorable)


def attach_verdict(
    resp_data: dict[str, object],
    project_root: Path,
    *,
    file_paths: str = "",
    base_ref: str = "HEAD",
) -> None:
    """Write the nothing-to-gate verdict into *resp_data* and persist it.

    The response half is what programmatic MCP callers read; the persisted
    half is what ``tapps_checklist`` and the stop hook read. Both come from
    the same census so the two can never disagree.
    """
    counts = census(project_root, file_paths=file_paths, base_ref=base_ref)
    resp_data["nothing_to_gate"] = counts.nothing_to_gate
    resp_data["nothing_to_gate_reason"] = build_reason(counts)
    resp_data["changed_files_seen"] = counts.changed_files
    resp_data["non_scorable_changed"] = list(counts.non_scorable)
    record(project_root, counts)


def _git_changed_names(project_root: Path, base_ref: str) -> list[str]:
    """Every changed path git knows about — scorable or not."""
    from tapps_mcp.tools.batch_validator import _git_diff_names, _git_untracked_names

    names: set[str] = set()
    with contextlib.suppress(OSError):
        names |= _git_diff_names(project_root, base_ref)
        names |= _git_diff_names(project_root, "--cached")
        names |= _git_untracked_names(project_root)
        if base_ref.strip().upper() == "HEAD":
            for branch in ("main", "master", "origin/main", "origin/master"):
                names |= _git_diff_names(project_root, f"{branch}...HEAD")
    return sorted(n for n in names if n.strip())


def build_reason(counts: ChangedFileCensus) -> str:
    """Human-readable terminal reason for a nothing-to-gate verdict."""
    if counts.changed_files == 0:
        return (
            "nothing needed validating — no changed files in this session, "
            "so no file-scoped tool has a target."
        )
    return (
        f"nothing needed validating — {counts.changed_files} changed file(s), "
        f"{len(counts.scorable)} scorable. No file-scoped tool has a target "
        "that this session touched."
    )


def marker_path(project_root: Path) -> Path:
    return project_root / NOTHING_TO_GATE_MARKER


def record(project_root: Path, counts: ChangedFileCensus) -> None:
    """Persist the nothing-to-gate verdict for later pipeline steps."""
    path = marker_path(project_root)
    payload = {
        "ts": time.time(),
        "reason": build_reason(counts),
        "changed_files": counts.changed_files,
        "scorable_changed": len(counts.scorable),
        "non_scorable_changed": list(counts.non_scorable[:32]),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logger.debug("nothing_to_gate_marker_write_failed", exc_info=True)


def clear(project_root: Path) -> None:
    """Drop a recorded verdict — called whenever real files are gated."""
    with contextlib.suppress(OSError):
        marker_path(project_root).unlink(missing_ok=True)


def read_marker(
    project_root: Path,
    *,
    max_age_s: float = MARKER_MAX_AGE_S,
    now: float | None = None,
) -> dict[str, object] | None:
    """Return the recorded verdict when present and fresh, else ``None``."""
    path = marker_path(project_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        age = (time.time() if now is None else now) - float(raw.get("ts", 0.0))
    except (TypeError, ValueError):
        return None
    if age > max_age_s or age < -max_age_s:
        return None
    return raw


def resolve(
    project_root: Path | None,
    *,
    max_age_s: float = MARKER_MAX_AGE_S,
) -> NothingToGate | None:
    """Return a usable nothing-to-gate verdict, or ``None``.

    Two independent conditions must hold, and both are load-bearing:

    1. ``validate_changed`` recorded the verdict recently. Without this the
       state would be indistinguishable from "no validation ran".
    2. A freshly derived git census *still* shows zero changed scorable
       files. Without this a stale marker could silently make a session with
       real code changes complete — the exact bypass this issue forbids.
    """
    if project_root is None:
        return None
    marker = read_marker(project_root, max_age_s=max_age_s)
    if marker is None:
        return None
    from tapps_mcp.tools.batch_validator import detect_changed_scorable_files

    try:
        if detect_changed_scorable_files(project_root, "HEAD"):
            return None
    except (OSError, ValueError):
        return None
    non_scorable = marker.get("non_scorable_changed")
    reason = marker.get("reason")
    if not isinstance(reason, str) or not reason:
        reason = build_reason(ChangedFileCensus(scorable=(), non_scorable=()))
    changed_files = marker.get("changed_files")
    recorded_at = marker.get("ts")
    return NothingToGate(
        reason=reason,
        changed_files=changed_files if isinstance(changed_files, int) else 0,
        non_scorable=tuple(str(p) for p in non_scorable) if isinstance(non_scorable, list) else (),
        recorded_at=float(recorded_at) if isinstance(recorded_at, (int, float)) else 0.0,
    )


def attach_nothing_to_gate(data: dict[str, object], result: object) -> None:
    """Promote the terminal state into a checklist json/compact envelope.

    Emitted only when it applies, so its presence is itself the signal: an
    envelope without these keys either gated something or gated nothing
    because nothing ran. The compact/json ``full`` block always carries the
    same fields; this is the top-level convenience copy.
    """
    if not getattr(result, "nothing_to_gate", False):
        return
    data["nothing_to_gate"] = True
    data["nothing_to_gate_reason"] = getattr(result, "nothing_to_gate_reason", "")
    data["not_applicable"] = list(getattr(result, "not_applicable_tools", []))


def partition_file_scoped(tools: list[str]) -> tuple[list[str], list[str]]:
    """Split *tools* into (still_required, not_applicable)."""
    still: list[str] = []
    not_applicable: list[str] = []
    for tool in tools:
        (not_applicable if tool in FILE_SCOPED_TOOLS else still).append(tool)
    return still, not_applicable


__all__ = [
    "FILE_SCOPED_TOOLS",
    "MARKER_MAX_AGE_S",
    "NOTHING_TO_GATE_MARKER",
    "ChangedFileCensus",
    "NothingToGate",
    "attach_nothing_to_gate",
    "attach_verdict",
    "build_reason",
    "census",
    "clear",
    "marker_path",
    "partition_file_scoped",
    "read_marker",
    "record",
    "resolve",
]
