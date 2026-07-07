"""Startup diagnostics - local-only health checks for TappsMCP subsystems."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tapps_core.common.models import (
    CacheDiagnostic,
    Context7Diagnostic,
    InstallDriftDiagnostic,
    InstallDriftEntry,
    KnowledgeBaseDiagnostic,
    StartupDiagnostics,
)

if TYPE_CHECKING:
    from pydantic import SecretStr


def check_context7(api_key: SecretStr | None) -> Context7Diagnostic:
    """Cheap key-presence check (no network). Prefer :func:`probe_context7`.

    Returns ``unknown`` when a key is set because presence alone says nothing
    about whether Context7 is reachable or the key is valid — call
    :func:`probe_context7` for the live verdict.
    """
    has_key = api_key is not None and len(api_key.get_secret_value()) > 0
    return Context7Diagnostic(
        api_key_set=has_key,
        status="unknown" if has_key else "no_key",
        reachable=None,
        detail=None if has_key else "No Context7 API key configured; llms.txt fallback active.",
    )


# Live-probe machinery -------------------------------------------------------

_PROBE_MARKER_NAME = ".context7-probe-marker"
_PROBE_TTL_SECONDS = 900  # 15 min — bounds probe frequency across hot session_starts
_PROBE_LIBRARY = "python"  # cheap, always-indexed resolve target


def context7_probe_marker_path(project_root: Path) -> Path:
    """Return the throttle-marker path for the Context7 liveness probe."""
    return project_root / ".tapps-mcp" / _PROBE_MARKER_NAME


def _read_probe_marker(
    project_root: Path,
    *,
    ttl: int = _PROBE_TTL_SECONDS,
) -> Context7Diagnostic | None:
    """Return the cached probe verdict if a fresh marker exists, else ``None``."""
    path = context7_probe_marker_path(project_root)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    ts = data.get("ts", 0)
    if not isinstance(ts, (int, float)) or (time.time() - ts) > ttl:
        return None
    diag = data.get("diagnostic")
    if not isinstance(diag, dict):
        return None
    try:
        return Context7Diagnostic.model_validate(diag)
    except Exception:
        return None


def _write_probe_marker(project_root: Path, diagnostic: Context7Diagnostic) -> None:
    """Persist the probe verdict + timestamp. Best-effort; never raises."""
    path = context7_probe_marker_path(project_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": int(time.time()), "diagnostic": diagnostic.model_dump()}
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def _status_from_error_message(message: str) -> int | None:
    """Extract a trailing HTTP status code from a Context7Error message."""
    token = message.strip().rstrip(".").split()[-1] if message.strip() else ""
    if token.isdigit():
        code = int(token)
        if 100 <= code <= 599:
            return code
    return None


async def probe_context7_async(
    api_key: SecretStr | None,
    *,
    timeout: float = 3.0,
    breaker: object | None = None,
) -> Context7Diagnostic:
    """Live round-trip against Context7, returning a 4-state liveness verdict.

    Resolves a cheap, always-indexed library through the shared circuit
    breaker. Never raises: every failure mode collapses into an
    ``unreachable``/``unauthorized`` diagnostic.
    """
    has_key = api_key is not None and len(api_key.get_secret_value()) > 0
    if not has_key:
        return Context7Diagnostic(
            api_key_set=False,
            status="no_key",
            reachable=None,
            detail="No Context7 API key configured; llms.txt fallback active.",
        )

    import httpx

    from tapps_core.knowledge.circuit_breaker import (
        CircuitBreaker,
        CircuitBreakerOpenError,
        get_context7_circuit_breaker,
    )
    from tapps_core.knowledge.context7_client import Context7Client, Context7Error

    cb: CircuitBreaker = (
        breaker if isinstance(breaker, CircuitBreaker) else get_context7_circuit_breaker()
    )
    client = Context7Client(api_key=api_key, timeout=timeout)
    start = time.monotonic()
    try:
        matches = await cb.call(client.resolve_library, _PROBE_LIBRARY)
        latency = round((time.monotonic() - start) * 1000, 1)
        return Context7Diagnostic(
            api_key_set=True,
            status="available",
            reachable=True,
            http_status=200,
            latency_ms=latency,
            detail=None if matches else "Reachable, but probe query returned no matches.",
        )
    except CircuitBreakerOpenError:
        latency = round((time.monotonic() - start) * 1000, 1)
        return Context7Diagnostic(
            api_key_set=True,
            status="unreachable",
            reachable=False,
            latency_ms=latency,
            detail="Circuit breaker open after repeated Context7 failures.",
        )
    except Context7Error as exc:
        latency = round((time.monotonic() - start) * 1000, 1)
        code = _status_from_error_message(str(exc))
        if code in (401, 403):
            return Context7Diagnostic(
                api_key_set=True,
                status="unauthorized",
                reachable=True,
                http_status=code,
                latency_ms=latency,
                detail="Context7 rejected the API key (expired/revoked/invalid).",
            )
        return Context7Diagnostic(
            api_key_set=True,
            status="unreachable",
            reachable=False,
            http_status=code,
            latency_ms=latency,
            detail=str(exc),
        )
    except (TimeoutError, httpx.HTTPError) as exc:
        latency = round((time.monotonic() - start) * 1000, 1)
        return Context7Diagnostic(
            api_key_set=True,
            status="unreachable",
            reachable=False,
            latency_ms=latency,
            detail=f"Network error reaching Context7: {exc}",
        )
    finally:
        await client.close()


def _run_coroutine_sync(coro: Coroutine[Any, Any, Context7Diagnostic]) -> Context7Diagnostic:
    """Run ``coro`` to completion, tolerating a caller already inside a loop.

    ``asyncio.run()`` raises ``RuntimeError`` when invoked from within a
    running event loop (e.g. an MCP tool handler such as ``tapps_doctor``).
    In that case the coroutine is driven to completion on its own event loop
    in a dedicated worker thread instead of failing the caller.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # no loop running here — safe to own one

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def probe_context7(
    project_root: Path,
    api_key: SecretStr | None,
    *,
    force: bool = False,
    timeout: float = 3.0,
) -> Context7Diagnostic:
    """Throttled, synchronous live probe.

    Returns a cached verdict when a fresh marker (< ``_PROBE_TTL_SECONDS``)
    exists unless ``force`` is set (init/upgrade just wrote the key).
    Safe to call both from plain sync CLI paths and from within a running
    event loop (e.g. an MCP tool handler) — see :func:`_run_coroutine_sync`.
    """
    if not force:
        cached = _read_probe_marker(project_root)
        if cached is not None:
            return cached
    diagnostic = _run_coroutine_sync(probe_context7_async(api_key, timeout=timeout))
    _write_probe_marker(project_root, diagnostic)
    return diagnostic


def check_cache(cache_dir: Path) -> CacheDiagnostic:
    """Check cache directory existence, writability, and stats.

    Only instantiates ``KBCache`` if the directory already exists to avoid
    auto-creating it as a side effect.
    """
    exists = cache_dir.exists() and cache_dir.is_dir()
    writable = False
    entry_count = 0
    total_size_bytes = 0
    stale_count = 0

    if exists:
        try:
            fd, tmp = tempfile.mkstemp(dir=str(cache_dir), prefix=".diag_")
            os.close(fd)
            Path(tmp).unlink(missing_ok=True)
            writable = True
        except OSError:
            writable = False

        from tapps_core.knowledge.cache import KBCache

        cache = KBCache(cache_dir)
        stats = cache.stats
        entry_count = stats.total_entries
        total_size_bytes = stats.total_size_bytes
        stale_count = stats.stale_entries

    return CacheDiagnostic(
        cache_dir=str(cache_dir),
        exists=exists,
        writable=writable,
        entry_count=entry_count,
        total_size_bytes=total_size_bytes,
        stale_count=stale_count,
    )


def check_knowledge_base() -> KnowledgeBaseDiagnostic:
    """Expert system removed (EPIC-94). Returns empty diagnostic."""
    return KnowledgeBaseDiagnostic(
        total_domains=0,
        total_files=0,
        expected_domains=0,
        missing_domains=[],
        domains=[],
    )


def _probe_binary_at_path(binary_path: str) -> tuple[str, str]:
    """Return (path, version) for an explicit binary path."""
    try:
        result = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return binary_path, ""
    if result.returncode != 0 or not (result.stdout or result.stderr).strip():
        return binary_path, ""
    return binary_path, (result.stdout or result.stderr).strip().split()[-1]


def _probe_binary_version(binary_name: str) -> tuple[str, str]:
    """Return (resolved_path, reported_version) or ('', '') if unavailable.

    Looks up *binary_name* on PATH; runs ``<binary> --version`` with a tight
    timeout; parses the last whitespace-delimited token of stdout as the
    version. Any failure (not found, non-zero exit, timeout, parse error)
    collapses to ('', ''), signalling the caller to skip the entry.
    """
    binary_path = shutil.which(binary_name)
    if not binary_path:
        return "", ""
    try:
        result = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return binary_path, ""
    if result.returncode != 0 or not result.stdout.strip():
        return binary_path, ""
    return binary_path, result.stdout.strip().split()[-1]


def _read_uv_tool_install_source(binary_path: str) -> str:
    """Return install source from ``uv-receipt.toml`` when the global CLI is local (TAP-4099)."""
    try:
        receipt = Path(binary_path).resolve().parent.parent / "uv-receipt.toml"
        if not receipt.is_file():
            return ""
        for line in receipt.read_text(encoding="utf-8").splitlines():
            lower = line.lower()
            if "source" not in lower and "editable" not in lower and "path" not in lower:
                continue
            if "=" not in line:
                continue
            val = line.split("=", 1)[1].strip().strip("'\"")
            if val:
                return val
    except OSError:
        pass
    return ""


def _is_local_uv_tool_install(binary_path: str) -> tuple[bool, str]:
    """Return (from_local, install_source) for a global ``uv tool`` binary."""
    source = _read_uv_tool_install_source(binary_path)
    if not source:
        return False, ""
    try:
        resolved = Path(source).expanduser().resolve()
    except (OSError, ValueError):
        return False, source
    if resolved.is_dir() or resolved.is_file():
        return True, str(resolved)
    if "packages" in source.replace("\\", "/"):
        return True, source
    return False, source


def _version_tuple(ver: str) -> tuple[int, int, int]:
    """Parse ``3.12.38`` → ``(3, 12, 38)`` for drift direction checks."""
    try:
        parts = ver.strip().split(".")[:3]
        return (
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )
    except (ValueError, IndexError):
        return (0, 0, 0)


def _classify_install_drift(entries: list[InstallDriftEntry]) -> str:
    """Classify drift direction: cli_ahead, process_ahead, mixed, or unknown."""
    drifted = [e for e in entries if e.drifted and e.binary_version and e.source_version]
    if not drifted:
        return "unknown"
    cli_ahead = any(
        _version_tuple(e.binary_version) > _version_tuple(e.source_version) for e in drifted
    )
    process_ahead = any(
        _version_tuple(e.source_version) > _version_tuple(e.binary_version) for e in drifted
    )
    if cli_ahead and process_ahead:
        return "mixed"
    if cli_ahead:
        return "cli_ahead"
    if process_ahead:
        return "process_ahead"
    return "unknown"


def install_drift_remediation_hint(
    entries: list[InstallDriftEntry],
    *,
    uses_blue_green: bool,
) -> str:
    """Build context-aware remediation copy for install drift (TAP-2129)."""
    kind = _classify_install_drift(entries)
    reload = (
        "Reload MCP in Cursor (quit/reopen or Settings → MCP → restart nlt-* servers), "
        "then call tapps_session_start(force=true) to confirm drift is clear."
    )
    if kind == "cli_ahead":
        return (
            f"Global CLI is newer than this MCP server process. {reload} "
            "Do not run deploy-local on consumer projects."
        )
    if kind == "process_ahead":
        if uses_blue_green:
            return (
                "Deployed CLI is behind this MCP server. Run tapps-mcp deploy-local from "
                f"the tapps-mcp checkout, then {reload.lower()}"
            )
        return (
            "Global CLI is older than this MCP server. Reinstall: "
            "uv tool install --reinstall --from <path>/packages/tapps-mcp tapps-mcp "
            "(and docs-mcp), then reload MCP."
        )
    return (
        f"Version mismatch between MCP server and global CLI. {reload} "
        "If drift persists, reinstall global CLIs or run deploy-local (dev monorepo only)."
    )


def format_upgrade_blocked_by_drift(drift: InstallDriftDiagnostic) -> str:
    """Human-readable upgrade gate message when install drift is detected (TAP-2200)."""
    from tapps_mcp import __version__

    stale = [e.binary for e in drift.entries if e.drifted]
    kind = _classify_install_drift(drift.entries)
    base = f"Upgrade blocked: install drift detected for {stale}."
    if kind == "cli_ahead":
        return (
            f"{base} Global CLI is newer than this MCP server (running v{__version__}). "
            "Reload Cursor MCP (quit/reopen), then re-run tapps_upgrade. "
            "Alternatively run `tapps-mcp upgrade` from the shell. "
            "Preview with dry_run=True."
        )
    return (
        f"{base} All sibling tools must be at version {__version__} before upgrading. "
        f"{drift.remediation_hint} — then re-run tapps_upgrade. "
        "To preview the upgrade plan despite drift, use dry_run=True."
    )


def check_install_drift() -> InstallDriftDiagnostic:
    """TAP-2129: detect drift between in-process package versions and deployed CLIs.

    When the dev-monorepo blue/green ``~/.tapps-mcp/current`` layout is active,
    probes ``current/bin/*`` instead of the legacy ``uv tool install`` shims.
    """
    from docs_mcp import __version__ as docs_mcp_version
    from tapps_mcp import __version__ as tapps_mcp_version
    from tapps_mcp.distribution.blue_green import blue_green_enabled, resolve_blue_green_binary

    targets = [
        ("tapps-mcp", tapps_mcp_version),
        ("docsmcp", docs_mcp_version),
    ]
    entries: list[InstallDriftEntry] = []
    for binary, source_version in targets:
        blue_green_path = resolve_blue_green_binary(binary)
        if blue_green_path:
            binary_path, binary_version = _probe_binary_at_path(blue_green_path)
            install_source = str(Path(blue_green_path).resolve().parents[1])
            from_local = True
        else:
            binary_path, binary_version = _probe_binary_version(binary)
            from_local, install_source = _is_local_uv_tool_install(binary_path)
        if not binary_path:
            continue
        drifted = bool(binary_version) and binary_version != source_version
        entries.append(
            InstallDriftEntry(
                binary=binary,
                binary_path=binary_path,
                binary_version=binary_version,
                source_version=source_version,
                drifted=drifted,
                from_local_source=from_local,
                install_source=install_source,
            )
        )

    drift_detected = any(e.drifted for e in entries)
    local_install_warning = any(e.from_local_source for e in entries)
    uses_blue_green = blue_green_enabled() and resolve_blue_green_binary("tapps-mcp") is not None
    hint = ""
    if drift_detected:
        hint = install_drift_remediation_hint(entries, uses_blue_green=uses_blue_green)
    elif local_install_warning and not uses_blue_green:
        hint = (
            "Global CLIs installed from a local checkout — consumer repos share this binary. "
            "Pin fleet globals to release tags; dev monorepo deploys via "
            "tapps-mcp deploy-local (blue/green flip) then MCP reload."
        )
    return InstallDriftDiagnostic(
        drift_detected=drift_detected,
        local_install_warning=local_install_warning,
        entries=entries,
        remediation_hint=hint,
    )


def collect_diagnostics(
    api_key: SecretStr | None,
    cache_dir: Path,
    *,
    project_root: Path | None = None,
) -> StartupDiagnostics:
    """Run all diagnostic checks and return a single ``StartupDiagnostics``.

    Uses the throttled live :func:`probe_context7` so ``context7.status``
    reflects real reachability, not mere key presence. The 15-minute marker
    keeps this cheap across frequent session starts. Runs in a worker thread
    (``asyncio.to_thread``) so the inner ``asyncio.run`` is safe.
    """
    root = project_root if project_root is not None else cache_dir.parent
    return StartupDiagnostics(
        context7=probe_context7(root, api_key),
        cache=check_cache(cache_dir),
        knowledge_base=check_knowledge_base(),
        install_drift=check_install_drift(),
    )
