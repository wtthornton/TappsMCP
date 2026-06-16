"""Startup diagnostics - local-only health checks for TappsMCP subsystems."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

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
    """Check whether a Context7 API key is configured."""
    has_key = api_key is not None and len(api_key.get_secret_value()) > 0
    return Context7Diagnostic(
        api_key_set=has_key,
        status="available" if has_key else "no_key",
    )


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
    from tapps_mcp.distribution.blue_green import resolve_blue_green_binary

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
    uses_blue_green = resolve_blue_green_binary("tapps-mcp") is not None
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
) -> StartupDiagnostics:
    """Run all diagnostic checks and return a single ``StartupDiagnostics``."""
    return StartupDiagnostics(
        context7=check_context7(api_key),
        cache=check_cache(cache_dir),
        knowledge_base=check_knowledge_base(),
        install_drift=check_install_drift(),
    )
