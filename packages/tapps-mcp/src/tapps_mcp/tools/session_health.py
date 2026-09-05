"""Session-start freshness and build-skew probes for ``tapps_doctor``.

Two questions an agent cannot currently answer from a successful
``tapps_session_start`` response:

1. **Did it actually run?** (TAP-6900) ``tapps_session_start`` memoizes on
   ``(server-process _SESSION_ID, quick, project_root)`` and returns from the
   cache branch *before* ``CallTracker.begin_session()``. In the HTTP fleet
   deployment one long-lived server process serves many agent sessions against
   the same root, so every session after the first receives ``success: true``
   with a full payload, a ``checklist_session_id`` belonging to an earlier
   session, and no bootstrap side effects at all.

2. **Which build answered?** (TAP-6901) ``tapps_mcp.__version__`` is bound at
   process import, so a server can outlive several ``uv tool install`` upgrades
   of the package it was launched from and never say so.

Both probes are read-only. ``read_marker_epoch`` rejects non-finite and
out-of-range marker content rather than raising on it, and
``attach_session_health`` catches any residual failure from either probe and
reports it as an ``error`` field instead of propagating it: a diagnostic that
can break the doctor is worse than no diagnostic.

Two surfaces consume these blocks — the ``tapps_doctor`` MCP tool and the
``tapps-mcp doctor`` CLI — and they run in *different kinds of process*. The
uptime fields therefore name the process that ran the probe
(``probe_process_*``) rather than asserting it is a server, and
``probe_process_role`` says which kind it was. Under the CLI the uptime is a
few milliseconds and means "this CLI invocation"; calling that
``server_process_uptime_s`` would be true as arithmetic and false as a
sentence. For the same reason ``memo_hit_pending`` is ``None`` — not
``False`` — when the caller holds no memo cache to inspect: the CLI cannot see
the server's memo, and reporting ``False`` would assert that the next
``tapps_session_start`` would really run.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: A memo hit older than this means the bootstrap it stands for belongs to a
#: session that has almost certainly ended. Override with
#: ``TAPPS_MCP_SESSION_STALE_S``.
DEFAULT_STALE_MEMO_S = 3600

_MARKER_RELPATH = (".tapps-mcp", ".session-start-marker")

#: The long-lived MCP server process that answers ``tapps_doctor``.
PROBE_ROLE_SERVER = "mcp_server"

#: A short-lived process that exits when the command does — ``tapps-mcp
#: doctor`` and any in-process library caller. Chosen as the default because it
#: under-claims: mislabelling a CLI as a server is the defect, not the reverse.
PROBE_ROLE_CLI = "cli"

#: The blocks :func:`attach_session_health` writes. Both doctor surfaces render
#: from this tuple, so a third block reaches both of them at once and the
#: CLI/MCP parity test has something to assert against.
SESSION_HEALTH_BLOCK_KEYS = ("session_start", "build_skew")


def stale_memo_threshold_s() -> int:
    """Resolve the stale-memo threshold, honouring the env override."""
    raw = os.environ.get("TAPPS_MCP_SESSION_STALE_S", "").strip()
    if raw:
        try:
            parsed = int(raw)
        except ValueError:
            return DEFAULT_STALE_MEMO_S
        if parsed > 0:
            return parsed
    return DEFAULT_STALE_MEMO_S


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")


#: Upper bound for an accepted marker epoch: a few decades past "now" is far
#: beyond any plausible clock skew or clock-format bug, while still rejecting
#: overflow-inducing values like ``1e20`` before they reach
#: ``datetime.fromtimestamp`` (which raises OverflowError/OSError/ValueError
#: for those, depending on platform).
_MARKER_EPOCH_MAX_S = 4_102_444_800.0  # 2100-01-01T00:00:00Z


def read_marker_epoch(project_root: Path | str) -> float | None:
    """Return the epoch recorded in the TAP-975 session-start marker.

    Prefers the file's *content* (an epoch written by
    ``write_session_start_marker``) over its mtime, so a copy or a touch cannot
    silently age the reading. Falls back to mtime when the content is unusable
    or out of a sane epoch range (rejects non-finite values and anything
    outside ``[0, _MARKER_EPOCH_MAX_S]``).
    """
    marker = Path(project_root).joinpath(*_MARKER_RELPATH)
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        parsed = None
    if parsed is not None and math.isfinite(parsed) and 0.0 <= parsed <= _MARKER_EPOCH_MAX_S:
        return parsed
    try:
        return marker.stat().st_mtime
    except OSError:
        return None


def process_start_epoch() -> float | None:
    """Best-effort start time of the process that is running this probe.

    Deliberately not "the server process": under ``tapps-mcp doctor`` this is
    the CLI invocation, which started milliseconds ago. Callers label it with
    ``probe_process_role`` rather than assuming.

    Linux exposes it as the ctime of ``/proc/self``. Elsewhere we return
    ``None`` rather than guess — an invented uptime would be worse than an
    absent one, since the whole point is to date a bootstrap against it.
    """
    try:
        return Path("/proc/self").stat().st_ctime
    except OSError:
        return None


def collect_build_skew() -> dict[str, Any]:
    """Compare the build this process is running against the one on disk.

    ``tapps_mcp.__version__`` is ``importlib.metadata.version()`` evaluated once
    at import, so it names the build the server actually loaded. Re-reading the
    distribution metadata now names what a fresh process would load.
    """
    import importlib
    import importlib.metadata

    from tapps_mcp import __version__ as running_version

    installed_version: str | None
    try:
        # The metadata finder caches per (path, mtime); invalidating first makes
        # an upgrade that replaced site-packages visible without a restart.
        importlib.invalidate_caches()
        installed_version = importlib.metadata.version("tapps-mcp")
    except Exception:
        # A missing or unreadable distribution must not break the doctor; the
        # caller reports it as "unknown" via the note below rather than raising.
        installed_version = None

    block: dict[str, Any] = {
        "running_version": running_version,
        "installed_version": installed_version,
        "skew": False,
    }
    if installed_version is None:
        block["note"] = (
            "Installed distribution metadata for tapps-mcp could not be read; "
            "skew cannot be determined."
        )
        return block

    if installed_version != running_version:
        block["skew"] = True
        block["warning"] = (
            f"Server process is running tapps-mcp {running_version} but "
            f"{installed_version} is installed on disk. Every answer from this "
            "server reflects the older build. Restart the MCP server process "
            "to pick up the installed version."
        )
    return block


def collect_session_start_health(
    project_root: Path | str,
    *,
    memo_present: bool | None,
    probe_role: str = PROBE_ROLE_CLI,
    now: float | None = None,
) -> dict[str, Any]:
    """Report whether a real ``tapps_session_start`` bootstrap backs this session.

    Args:
        project_root: Root whose marker is read.
        memo_present: Whether ``_SESSION_START_CACHE`` already holds an entry
            for this root, i.e. whether the next ``tapps_session_start`` call
            would be served from memo without running. ``None`` when the caller
            has no memo cache to inspect (the CLI cannot see the server's), in
            which case no memo verdict is reachable and the marker's age alone
            decides between ``fresh`` and ``stale_marker``.
        probe_role: Which kind of process is running this probe —
            :data:`PROBE_ROLE_SERVER` or :data:`PROBE_ROLE_CLI`. Reported as
            ``probe_process_role`` so a reader knows whose uptime the
            ``probe_process_*`` fields describe.
        now: Injected clock for tests.
    """
    now = time.time() if now is None else now
    threshold = stale_memo_threshold_s()

    marker_epoch = read_marker_epoch(project_root)
    proc_start = process_start_epoch()

    block: dict[str, Any] = {
        "memo_hit_pending": memo_present,
        "stale_after_s": threshold,
        "marker_recorded_at": _iso(marker_epoch) if marker_epoch is not None else None,
        "marker_age_s": int(now - marker_epoch) if marker_epoch is not None else None,
        "probe_process_role": probe_role,
        "probe_process_started": _iso(proc_start) if proc_start is not None else None,
        "probe_process_uptime_s": int(now - proc_start) if proc_start is not None else None,
    }

    if marker_epoch is None:
        block["bootstrap_within_this_process"] = False
        block["verdict"] = "never_bootstrapped"
        block["warning"] = (
            "No tapps_session_start marker for this project root. Nothing has "
            "bootstrapped it, so the checklist ledger and pipeline state are "
            "empty. Call tapps_session_start(force=True)."
        )
        return block

    within = proc_start is not None and marker_epoch >= proc_start
    block["bootstrap_within_this_process"] = within

    age = int(now - marker_epoch)
    # An unobservable memo (``memo_present is None``) is falsy here on purpose:
    # neither memo verdict can be claimed, so the marker's age decides alone.
    if memo_present and age > threshold:
        block["verdict"] = "stale_memo"
        block["warning"] = (
            f"tapps_session_start is memoized for this root from a bootstrap "
            f"{age}s ago (threshold {threshold}s). Further calls return "
            "cached: true without running, and checklist_session_id belongs to "
            "that earlier session. Pass force=True to bootstrap this session."
        )
    elif memo_present:
        block["verdict"] = "memoized"
    elif age > threshold:
        block["verdict"] = "stale_marker"
        block["warning"] = (
            f"Session-start marker for this project root is {age}s old "
            f"(threshold {threshold}s) with no bootstrap memoized. The marker "
            "predates any live memo for this root, so the last recorded "
            "bootstrap is almost certainly stale. Call tapps_session_start() "
            "to record a current one."
        )
    else:
        block["verdict"] = "fresh"
    return block


def attach_session_health(
    result: dict[str, Any],
    project_root: Path | str,
    memo_cache: dict[Any, Any] | None,
    *,
    probe_role: str,
) -> None:
    """Add the ``session_start`` and ``build_skew`` blocks to a doctor result.

    Kept here rather than inline in ``tapps_doctor`` so the probe's complexity
    lands in a module that can carry it: ``server_pipeline_tools`` is already a
    1800-line module scoring below the gate threshold, and every line added
    there makes an existing failure worse.

    This is the single seam both doctor surfaces wire through, so ``probe_role``
    is required with no default: adding a third surface has to state what kind
    of process it is rather than inherit a claim that happens to be wrong.

    Args:
        result: Doctor payload to populate; gains exactly
            :data:`SESSION_HEALTH_BLOCK_KEYS`.
        project_root: Root whose marker is read.
        memo_cache: The server's ``_SESSION_START_CACHE``, or ``None`` when the
            caller has no such cache to inspect — the CLI runs in a different
            process from the server and cannot observe its memo.
        probe_role: :data:`PROBE_ROLE_SERVER` or :data:`PROBE_ROLE_CLI`.

    Neither block raises. A probe that dies is recorded as an ``error`` field —
    never omitted, since an absent block would read as a clean bill of health.
    """
    root_key = str(Path(project_root).resolve())
    try:
        memo_present: bool | None = None
        if memo_cache is not None:
            memo_present = any(
                isinstance(key, tuple) and len(key) >= 3 and key[2] == root_key
                for key in memo_cache
            )
        result["session_start"] = collect_session_start_health(
            project_root, memo_present=memo_present, probe_role=probe_role
        )
    except Exception as exc:
        result["session_start"] = {"error": f"session_start_probe_unavailable: {exc}"}

    try:
        result["build_skew"] = collect_build_skew()
    except Exception as exc:
        result["build_skew"] = {"error": f"build_skew_probe_unavailable: {exc}"}


def session_health_warnings(result: dict[str, Any]) -> list[str]:
    """Warnings from both blocks, most invalidating first.

    A build skew invalidates every other reading in the report, so it leads.
    """
    warnings: list[str] = []
    for key in ("build_skew", "session_start"):
        block = result.get(key)
        if isinstance(block, dict) and block.get("warning"):
            warnings.append(block["warning"])
    return warnings


def prepend_session_health_warnings(
    resp: dict[str, Any],
    result: dict[str, Any],
    prepend: Callable[[dict[str, Any], str], Any],
) -> None:
    """Push both blocks' warnings onto ``resp``'s next steps, skew first.

    Takes the caller's ``_prepend_next_step`` rather than importing it, so the
    loop and its branch stay out of ``server_pipeline_tools`` — that module is
    ratcheted at its current score, and added complexity there fails CI.

    Prepends in reverse because each call goes to the front: the last one
    prepended ends up first, and a build skew invalidates every other reading.
    """
    for warning in reversed(session_health_warnings(result)):
        prepend(resp, warning)


__all__ = [
    "DEFAULT_STALE_MEMO_S",
    "PROBE_ROLE_CLI",
    "PROBE_ROLE_SERVER",
    "SESSION_HEALTH_BLOCK_KEYS",
    "attach_session_health",
    "collect_build_skew",
    "collect_session_start_health",
    "prepend_session_health_warnings",
    "process_start_epoch",
    "read_marker_epoch",
    "session_health_warnings",
    "stale_memo_threshold_s",
]
