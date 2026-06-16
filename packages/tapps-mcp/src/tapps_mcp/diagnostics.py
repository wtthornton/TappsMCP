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


def check_install_drift() -> InstallDriftDiagnostic:
    """TAP-2129: detect drift between in-process package versions and the
    ``uv tool`` global install on PATH.

    When ``uv tool install`` ships a copy (non-editable), the global binary
    can lag the local checkout silently. This check compares each binary's
    ``--version`` against the source ``__version__`` and reports drift.

    Skipped silently when neither binary is found on PATH (e.g. dev running
    purely from the project venv). Never raises.
    """
    from docs_mcp import __version__ as docs_mcp_version
    from tapps_mcp import __version__ as tapps_mcp_version

    targets = [
        ("tapps-mcp", tapps_mcp_version),
        ("docsmcp", docs_mcp_version),
    ]
    entries: list[InstallDriftEntry] = []
    for binary, source_version in targets:
        binary_path, binary_version = _probe_binary_version(binary)
        if not binary_path:
            continue
        drifted = bool(binary_version) and binary_version != source_version
        from_local, install_source = _is_local_uv_tool_install(binary_path)
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
    hint = ""
    if drift_detected:
        hint = (
            "Refresh global tools: uv tool install -e --reinstall "
            "<path-to-tapps-mcp>/packages/tapps-mcp "
            "(and the same for packages/docs-mcp)"
        )
    elif local_install_warning:
        hint = (
            "Global CLIs installed from a local checkout — consumer repos share this binary. "
            "Pin fleet globals to release tags; dev monorepo should use uv run in MCP wrappers."
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
